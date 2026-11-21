from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from tactile_rec.streams.specs import HAND_JOINTS

from policy_runner import config as runner_config
from policy_runner import fake_server
from policy_runner.commands.hand_udp import HandUdpCommand
from policy_runner.runner import Runner, StartError
from policy_runner.ui import make_app

from conftest import manifest_dict, read_trace, runner_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "audit"))
from audit_trace import audit  # noqa: E402


@pytest.fixture
def server():
    started = fake_server.start(port=0, delay_ms=60, metadata={"manifest": manifest_dict()})
    yield started
    started.stop()


def runner_for(files, server, **overrides) -> Runner:
    raw = runner_dict(policy={"endpoint": f"ws://127.0.0.1:{server.port}"}, **overrides)
    return Runner(runner_config.load(files(runner=raw)))


def test_dry_run_end_to_end_with_fake_server(files, server):
    runner = runner_for(files, server)
    runner.start()
    try:
        assert runner.status()["state"] == "READY"
        runner.arm()
        time.sleep(3.0)
        status = runner.status()
    finally:
        runner.stop()
    events = read_trace(runner.trace_path)
    assert audit(events) == []
    assert sum(e["ev"] == "chunk" for e in events) >= 1
    assert sum(e["ev"] == "send" for e in events) >= 10
    assert status["chunk"]["id"] >= 1


def test_start_refuses_a_server_with_another_manifest(files):
    other = fake_server.start(port=0, metadata={"manifest": manifest_dict(fps=15)})
    try:
        runner = runner_for(files, other)
        with pytest.raises(StartError) as caught:
            runner.start()
        assert "fps" in str(caught.value)
    finally:
        runner.stop()
        other.stop()


def test_ui_state_and_buttons(files, server):
    runner = runner_for(files, server)
    runner.start()
    try:
        client = TestClient(make_app(runner))
        state = client.get("/api/state").json()
        for key in ("state", "endpoint", "checkpoint", "streams", "infer", "chunk", "problems",
                    "mode", "ticks", "hand"):
            assert key in state
        assert state["state"] == "READY"
        assert client.post("/api/arm").status_code == 200
        time.sleep(1.0)
        running = client.get("/api/state").json()
        assert running["state"] in ("RUNNING", "HOLD")
        assert running["ticks"]["send"] + running["ticks"]["hold"] > 0
        assert running["hand"]["mode"] == "live"
        assert running["hand"]["lag_deg"] is not None
        assert client.post("/api/disarm").status_code == 200
        assert client.get("/api/state").json()["state"] == "READY"
        assert "<html" in client.get("/").text.lower()
    finally:
        runner.stop()


def test_hand_udp_sends_degrees_in_hand_joint_order():
    sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sink.bind(("127.0.0.1", 0))
    sink.settimeout(2)
    command = HandUdpCommand("127.0.0.1", sink.getsockname()[1], arm_dof=6)
    row = np.concatenate([np.zeros(6), np.deg2rad(np.arange(16, dtype=np.float64))])
    command.send(row.astype(np.float32), 123)
    command.send(row.astype(np.float32), 456)
    first = json.loads(sink.recv(65535))
    second = json.loads(sink.recv(65535))
    command.close()
    sink.close()
    assert first["v"] == 1 and first["t_ns"] == 123
    assert second["seq"] == first["seq"] + 1
    assert len(first["hand_deg"]) == len(HAND_JOINTS)
    assert np.allclose(first["hand_deg"], np.arange(16), atol=1e-3)
