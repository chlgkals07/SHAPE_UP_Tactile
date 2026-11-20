import json
import socket
import time

import numpy as np
import pytest

from leap_teleop.cli import build_parser, build_retargeter, build_source
from leap_teleop.retarget.passthrough import passthrough
from leap_teleop.safety import StaleGuard
from leap_teleop.sources.policy_udp import PolicyUdpSource, parse_policy_packet
from leap_teleop.types import Reading


def packet(hand, seq=1, version=1):
    return json.dumps({"v": version, "seq": seq, "t_ns": 5, "hand_deg": hand}).encode()


@pytest.fixture
def source():
    created = PolicyUdpSource("127.0.0.1", 0, clock=lambda: 42.0)
    yield created
    created.close()


def send(source, raw):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(raw, ("127.0.0.1", source.port))
    sock.close()


def wait_reading(source):
    for _ in range(200):
        reading = source.poll(0.0)
        if reading is not None:
            return reading
        time.sleep(0.01)
    return None


def test_parse_accepts_sixteen_finite_degrees():
    assert parse_policy_packet(packet(list(range(16)))) == [float(v) for v in range(16)]


@pytest.mark.parametrize("raw", [
    b"not json",
    packet(list(range(15))),
    packet([float("nan")] * 16),
    packet(list(range(16)), version=2),
    json.dumps({"v": 1, "seq": 1, "t_ns": 5}).encode(),
], ids=["json", "length", "nan", "version", "missing"])
def test_parse_rejects_bad_packets(raw):
    with pytest.raises(ValueError):
        parse_policy_packet(raw)


def test_source_turns_a_packet_into_a_hand_reading(source):
    send(source, packet(list(range(16))))
    reading = wait_reading(source)
    assert reading is not None
    assert reading.timestamp == 42.0
    assert np.allclose(reading.hand, np.arange(16))


def test_source_counts_and_drops_bad_packets(source):
    send(source, b"garbage")
    send(source, packet([1.0] * 16))
    reading = wait_reading(source)
    assert np.allclose(reading.hand, 1.0)
    assert source.bad_packets == 1


def test_passthrough_returns_a_copy_of_the_hand():
    reading = Reading(timestamp=0.0, hand=np.arange(16, dtype=np.float64))
    out = passthrough(reading)
    assert np.array_equal(out, reading.hand) and out is not reading.hand


def test_quiet_policy_goes_through_hold_then_release():
    guard = StaleGuard(np.zeros(16), stale_timeout=0.5, release_timeout=3.0)
    target = np.full(16, 20.0)
    assert np.allclose(guard.resolve(1.0, target, 1.0), 20.0) and guard.mode == "live"
    assert np.allclose(guard.resolve(2.0, target, 1.0), 20.0) and guard.mode == "hold"
    assert np.allclose(guard.resolve(5.0, target, 1.0), 0.0) and guard.mode == "release"


def test_cli_builds_the_policy_source_and_passthrough():
    args = build_parser().parse_args(["--source", "policy", "--policy-udp", "127.0.0.1:0",
                                      "--dry-run"])
    source = build_source(args)
    try:
        assert isinstance(source, PolicyUdpSource)
        assert build_retargeter(args, np.zeros(16), np.ones(16)) is passthrough
    finally:
        source.close()
