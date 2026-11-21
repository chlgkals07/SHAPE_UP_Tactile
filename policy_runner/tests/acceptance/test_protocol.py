from __future__ import annotations

import http.client
import time

import numpy as np
import pytest

from policy_runner import fake_server, wire
from policy_runner.chunk import check_reply
from policy_runner.inference import (
    Disconnected,
    InferTimeout,
    ManifestMismatch,
    PolicyClient,
    ServerError,
)
from policy_runner.manifest import Manifest

from conftest import manifest_dict


def request(value: float) -> dict:
    return {
        "state": np.full(22, value, dtype=np.float32),
        "images": {"cam_wrist": np.zeros((64, 48, 3), dtype=np.uint8)},
        "prompt": "p",
    }


@pytest.fixture
def serve():
    servers = []

    def start(**kwargs):
        server = fake_server.start(port=0, **kwargs)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.stop()


def client_for(server, timeout_s=2.0) -> PolicyClient:
    return PolicyClient(f"ws://127.0.0.1:{server.port}", connect_timeout_s=timeout_s)


def test_wire_roundtrip_preserves_dtype_shape_and_values():
    data = {"a": np.arange(6, dtype=np.float32).reshape(2, 3), "b": np.uint8(7),
            "c": {"d": np.zeros((2, 2, 3), dtype=np.uint8)}, "s": "text"}
    back = wire.unpackb(wire.packb(data))
    assert back["a"].dtype == np.float32 and back["a"].shape == (2, 3)
    assert np.array_equal(back["a"], data["a"])
    assert back["b"] == 7 and back["c"]["d"].shape == (2, 2, 3) and back["s"] == "text"


def test_metadata_comes_first_and_healthz_answers(serve):
    server = serve(metadata={"manifest": {"fps": 30}})
    client = client_for(server)
    client.connect()
    assert client.metadata["manifest"] == {"fps": 30}
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=2)
    conn.request("GET", "/healthz")
    assert conn.getresponse().status == 200


def test_hold_reply_repeats_the_state(serve):
    reply = client_for(serve()).infer(request(0.25), timeout_s=2.0)
    assert reply["actions"].shape == (50, 22)
    assert np.allclose(reply["actions"], 0.25)


def test_reconnecting_to_another_manifest_raises(serve):
    first = serve(metadata={"manifest": manifest_dict()})
    other = serve(metadata={"manifest": manifest_dict(fps=15)})
    client = PolicyClient(f"ws://127.0.0.1:{first.port}", 2.0, Manifest(**manifest_dict()))
    client.infer(request(0.0), timeout_s=2.0)
    client.close()
    client.endpoint = f"ws://127.0.0.1:{other.port}"
    with pytest.raises(ManifestMismatch, match="fps"):
        client.infer(request(0.0), timeout_s=2.0)
    assert not client.connected


def test_string_reply_raises_server_error(serve):
    client = client_for(serve(error_every=1))
    with pytest.raises(ServerError):
        client.infer(request(0.0), timeout_s=2.0)


def test_late_reply_after_timeout_is_never_used(serve):
    client = client_for(serve(stall_first_ms=400))
    with pytest.raises(InferTimeout):
        client.infer(request(1.0), timeout_s=0.1)
    time.sleep(0.5)
    reply = client.infer(request(2.0), timeout_s=2.0)
    assert np.allclose(reply["actions"], 2.0)


def test_stall_times_out(serve):
    with pytest.raises(InferTimeout):
        client_for(serve(stall_every=1)).infer(request(0.0), timeout_s=0.2)


def test_dropped_connection_is_reported_and_reconnects(serve):
    client = client_for(serve(drop_every=2))
    client.infer(request(0.0), timeout_s=2.0)
    with pytest.raises(Disconnected):
        client.infer(request(0.0), timeout_s=2.0)
    assert np.allclose(client.infer(request(3.0), timeout_s=2.0)["actions"], 3.0)


def test_delay_is_applied(serve):
    client = client_for(serve(delay_ms=150))
    client.infer(request(0.0), timeout_s=2.0)
    start = time.monotonic()
    client.infer(request(0.0), timeout_s=2.0)
    assert time.monotonic() - start >= 0.14


@pytest.mark.parametrize("fault", ["nan_every", "bad_shape_every"])
def test_injected_bad_replies_fail_the_check(serve, fault):
    reply = client_for(serve(**{fault: 1})).infer(request(0.0), timeout_s=2.0)
    assert check_reply(reply, 50, 22)


def test_good_reply_passes_the_check(serve):
    assert check_reply(client_for(serve()).infer(request(0.0), timeout_s=2.0), 50, 22) == []


@pytest.mark.parametrize("reply", [
    {},
    {"actions": np.zeros((50, 21), dtype=np.float32)},
    {"actions": np.zeros((49, 22), dtype=np.float32)},
    {"actions": np.zeros(22, dtype=np.float32)},
    {"actions": np.full((50, 22), np.inf, dtype=np.float32)},
    {"actions": np.zeros((50, 22), dtype=np.int64)},
], ids=["missing", "dim", "horizon", "rank", "inf", "int"])
def test_check_reply_rejects(reply):
    assert check_reply(reply, 50, 22)
