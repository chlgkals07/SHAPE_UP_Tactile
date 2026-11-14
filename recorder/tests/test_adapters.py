"""Adapter logic that can be tested without the devices."""

from __future__ import annotations

import json
import socket
import time
from types import SimpleNamespace

import numpy as np
import pytest
from conftest import PLACES_A, fake_config_dict

from tactile_rec.config import ConfigError, parse_config
from tactile_rec.streams import specs
from tactile_rec.streams.arm_zenoh import joint_state_data, joint_trajectory_data, stamp_ns
from tactile_rec.streams.hand_udp import HandUdpStream, parse_packet
from tactile_rec.streams.paxini import layout_from_board
from tactile_rec.streams.realsense import frame_src_ns
from tactile_rec.types import NO_TIME, STATUS_OK

# ---- arm ---------------------------------------------------------------------------------------

JOINTS = [f"joint{i}" for i in range(1, 7)]


def test_joint_state_is_reordered_by_name():
    names = ["rh_r1_joint", "joint6", "joint5", "joint4", "joint3", "joint2", "joint1"]
    msg = SimpleNamespace(
        name=names, position=[9, 6, 5, 4, 3, 2, 1], velocity=[0.9, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
        effort=[],
    )
    data = joint_state_data(msg, JOINTS)
    assert data["pos"].tolist() == [1, 2, 3, 4, 5, 6]
    assert data["vel"].tolist() == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    assert np.isnan(data["eff"]).all()  # the message carried no effort


def test_joint_state_missing_a_configured_joint_is_an_error_not_a_nan():
    msg = SimpleNamespace(name=["joint1", "joint2"], position=[1, 2], velocity=[], effort=[])
    with pytest.raises(ValueError, match="joint3"):
        joint_state_data(msg, JOINTS)


def test_joint_trajectory_uses_the_first_point():
    point = SimpleNamespace(positions=[1, 2, 3, 4, 5, 6, 0.5])
    msg = SimpleNamespace(joint_names=JOINTS + ["rh_r1_joint"], points=[point])
    assert joint_trajectory_data(msg, JOINTS)["pos"].tolist() == [1, 2, 3, 4, 5, 6]
    with pytest.raises(ValueError, match="no points"):
        joint_trajectory_data(SimpleNamespace(joint_names=JOINTS, points=[]), JOINTS)


def test_zero_stamp_means_no_source_time():
    assert stamp_ns(SimpleNamespace(sec=0, nanosec=0)) == NO_TIME
    assert stamp_ns(SimpleNamespace(sec=12, nanosec=5)) == 12_000_000_005


# ---- hand + glove over UDP ---------------------------------------------------------------------


def test_hand_joint_names_match_leap_teleop():
    from leap_teleop.hand.joints import ANGLE_NAMES
    from leap_teleop.types import HUMAN_ANGLE_NAMES

    assert tuple(ANGLE_NAMES) == specs.HAND_JOINTS
    assert len(HUMAN_ANGLE_NAMES) == specs.GLOVE_ANGLES


def test_packets_from_the_real_teleop_sink_arrive_as_hand_and_glove_samples():
    """The sink in leap_teleop and the stream here are two ends of one wire: test them joined."""
    from leap_teleop.record_sink import UdpRecordSink
    from leap_teleop.types import HumanHand, Reading

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    cfg = {"hz": 50, "host": "127.0.0.1", "port": port, "glove": True, "required": True}
    stream = HandUdpStream("hand", cfg)
    stream.start()
    time.sleep(0.2)
    driver = SimpleNamespace(last_sent_degrees=lambda: np.full(16, 11.0))
    sink = UdpRecordSink("127.0.0.1", port, driver)  # stamps with the real monotonic clock
    feedback = SimpleNamespace(
        positions_degrees=np.full(16, 10.0),
        velocities_degrees_per_second=np.full(16, 3.0),
        currents_milliamps=np.full(16, 80.0),
    )
    nodes = (("Hand/Invalid", (0, 0, 0, 0, 0, 0, 1)), ("Index/TIP", (0.1, 0.2, 0.3, 0, 0, 0, 1)))
    glove_time = time.monotonic()
    reading = Reading(timestamp=glove_time, human=HumanHand(np.arange(20.0), None, nodes))
    sink.publish(np.full(16, 12.0), feedback, "live", reading)
    sink.publish(np.full(16, 13.0), None, "hold", reading)  # same glove sample, no feedback
    deadline = time.monotonic() + 2.0
    while stream.health().count < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    stream.stop()
    sink.close()

    samples = stream.recent(0)
    assert len(samples) == 2
    first, second = samples
    # The sender is on this PC, so its stamp is kept and is a little before the receive time.
    assert 0 <= first.t_recv_ns - first.t_src_ns < 500_000_000
    assert (first.src_seq, second.src_seq) == (0, 1)
    assert first.data["cmd"][0] == 12 and first.data["sent"][0] == 11 and first.data["cur"][0] == 80
    assert int(first.data["mode"]) == 0 and int(second.data["mode"]) == 1
    assert np.isnan(second.data["pos"]).all()  # feedback read failed on that tick
    glove = stream.glove.recent(0)
    assert len(glove) == 1  # the unchanged glove sample is not repeated
    assert glove[0].t_src_ns == int(round(glove_time * 1e9))
    assert glove[0].data["ergo"].tolist() == list(range(20))
    assert int(glove[0].data["n_nodes"]) == 2
    assert glove[0].data["nodes"][1, :3].tolist() == pytest.approx([0.1, 0.2, 0.3])
    assert stream.glove.spec.meta["node_names"] == ["Hand/Invalid", "Index/TIP"]


def test_malformed_packets_are_rejected():
    good = {"v": 1, "seq": 0, "t_ns": 1, "mode": "live", "cmd": [0.0] * 16}
    assert parse_packet(json.dumps(good).encode()).glove is None
    for bad in (
        b"not json",
        json.dumps({**good, "v": 2}).encode(),
        json.dumps({**good, "cmd": [0.0] * 15}).encode(),
        json.dumps({k: v for k, v in good.items() if k != "mode"}).encode(),
        json.dumps({**good, "cmd": None}).encode(),
        json.dumps({**good, "seq": None}).encode(),  # wrong type, not a missing key
        json.dumps({**good, "cmd": "abc"}).encode(),
    ):
        with pytest.raises(ValueError):
            parse_packet(bad)


def test_a_bad_glove_block_does_not_cost_the_hand_sample():
    good = {"v": 1, "seq": 3, "t_ns": 1, "mode": "live", "cmd": [0.0] * 16}
    for glove in ({"ergo": [0.0] * 20}, {"t_ns": 5}, "nonsense", {"t_ns": 5, "ergo": [0.0] * 3}):
        packet = parse_packet(json.dumps({**good, "glove": glove}).encode())
        assert packet.seq == 3 and packet.glove is None and "bad glove" in packet.glove_error


def test_a_stamp_from_another_clock_is_dropped_not_trusted():
    from tactile_rec.clock import FakeClock

    cfg = {"hz": 50, "host": "127.0.0.1", "port": 0, "glove": False, "required": True}
    stream = HandUdpStream("hand", cfg, FakeClock())
    now = 10_000_000_000
    assert stream._sender_time(now - 2_000_000, now) == now - 2_000_000  # 2 ms old: same PC
    assert stream._sender_time(now + 5_000_000_000, now) == NO_TIME  # from the future
    assert stream._sender_time(now - 90_000_000_000, now) == NO_TIME  # another machine's uptime
    assert stream.clock_mismatch == 2 and stream.spec.meta["clock_mismatch"] == 2


def test_bad_packets_are_counted_and_do_not_stop_the_stream():
    cfg = {"hz": 50, "host": "127.0.0.1", "port": 0, "glove": False, "required": True}
    stream = HandUdpStream("hand", cfg)
    stream.start()
    deadline = time.monotonic() + 2.0
    while stream._socket is None and time.monotonic() < deadline:
        time.sleep(0.01)
    address = stream._socket.getsockname()
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    out.sendto(b"garbage", address)
    good = {"v": 1, "seq": 5, "t_ns": 9, "mode": "live", "cmd": [1.0] * 16}
    out.sendto(json.dumps(good).encode(), address)
    while stream.health().count < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    stream.stop()
    out.close()
    assert stream.bad_packets == 1 and stream.health().count == 1


# ---- paxini layout -----------------------------------------------------------------------------


def test_layout_follows_board_order_and_config_places():
    layout = layout_from_board(
        ["Thumb-Middle", "Thumb-Tip", "Index-Middle", "Index-Tip"], [25, 52, 25, 52],
        True, True, PLACES_A,
    )
    assert [m.place for m in layout.modules] == ["thumb_pad", "thumb_tip", "index_pad", "index_tip"]
    assert layout.payload_size == 2 * (6 + 75) + 2 * (6 + 156)


def test_a_sensor_on_an_unexpected_connector_stops_the_stream():
    with pytest.raises(ValueError, match="Ring-Tip"):
        layout_from_board(["Thumb-Tip", "Ring-Tip"], [52, 52], True, True, PLACES_A)
    with pytest.raises(ValueError, match="configured but not active"):
        layout_from_board(["Thumb-Tip"], [52], True, True, PLACES_A)


# ---- camera ------------------------------------------------------------------------------------


def test_only_host_clock_camera_timestamps_are_kept_as_source_time():
    assert frame_src_ns(1_700_000_000_123.5, 2) == 1_700_000_000_123_500_000  # global time
    assert frame_src_ns(1_700_000_000_123.5, 1) == 1_700_000_000_123_500_000  # system time
    assert frame_src_ns(5_123.0, 0) == NO_TIME  # the camera's private hardware counter


# ---- config ------------------------------------------------------------------------------------


def test_example_configs_are_valid():
    from pathlib import Path

    from tactile_rec.config import load_config

    folder = Path(__file__).parents[1] / "config"
    names = sorted(p.name for p in folder.glob("*.yaml"))
    assert names == ["rig.example.yaml", "rig.fake.yaml"]
    for name in names:
        config = load_config(folder / name)
        assert set(config.dataset.tactile) <= set(config.streams)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda raw: raw["streams"]["hand"].update(hzz=50), "unknown keys"),
        (lambda raw: raw["streams"].update(cam={"type": "webcam"}), "unknown type"),
        (lambda raw: raw["streams"]["cam_wrist"].update(rotation_deg=45), "rotation_deg"),
        (lambda raw: raw["dataset"].update(cameras=["cam_missing"]), "cam_missing"),
        (lambda raw: raw["dataset"].update(time={"hand": "nearest"}), "dataset.time.hand"),
        (lambda raw: raw["session"].update(task="pick cup"), "folder name"),
        (lambda raw: raw.update(recrod={}), "unknown top-level"),
        (lambda raw: raw["record"].update(preroll_s=5), "preroll_s"),
        (lambda raw: raw["streams"]["tactile_a"].pop("places"), "places"),
    ],
)
def test_config_mistakes_stop_at_load_time(tmp_path, change, message):
    raw = fake_config_dict(tmp_path)
    change(raw)
    with pytest.raises(ConfigError, match=message):
        parse_config(raw)


def test_hub_health_of_running_fake_streams(tmp_path):
    from tactile_rec.hub import Hub

    raw = fake_config_dict(tmp_path)
    hub = Hub(parse_config(raw))
    hub.start()
    time.sleep(1.2)
    health = hub.health()
    hub.stop()
    assert all(h.status == STATUS_OK for h in health.values()), {
        n: h.to_json() for n, h in health.items()
    }
    assert abs(health["tactile_a"].hz - 90) < 6 and abs(health["cam_ext"].hz - 30) < 3
