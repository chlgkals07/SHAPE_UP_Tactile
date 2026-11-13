import json
import socket
from types import SimpleNamespace

import numpy as np

from leap_teleop.record_sink import UdpRecordSink, build_packet, glove_block
from leap_teleop.types import HumanHand, Reading


def receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(1.0)
    return sock, sock.getsockname()[1]


def test_packet_carries_command_sent_feedback_and_mode():
    feedback = SimpleNamespace(
        positions_degrees=np.full(16, 10.0),
        velocities_degrees_per_second=np.full(16, 2.0),
        currents_milliamps=np.full(16, 75.0),
    )
    packet = build_packet(7, 123, np.full(16, 12.0), np.full(16, 11.0), feedback, "hold", None)
    assert (packet["v"], packet["seq"], packet["t_ns"], packet["mode"]) == (1, 7, 123, "hold")
    assert packet["cmd"] == [12.0] * 16 and packet["sent"] == [11.0] * 16
    assert packet["pos"] == [10.0] * 16 and packet["cur"] == [75.0] * 16
    bare = build_packet(0, 1, np.zeros(16), None, None, "live", None)
    assert bare["sent"] is None and bare["pos"] is None  # dry run / failed feedback read


def test_glove_block_keeps_every_raw_node():
    nodes = (("Hand/Invalid", (0, 0, 0, 0, 0, 0, 1)), ("Thumb/TIP", (0.01, 0.02, 0.03, 0, 0, 0, 1)))
    reading = Reading(timestamp=1.25, human=HumanHand(np.arange(20.0), None, nodes))
    block = glove_block(reading)
    assert block["t_ns"] == 1_250_000_000 and block["ergo"] == list(np.arange(20.0))
    assert block["node_names"] == ["Hand/Invalid", "Thumb/TIP"]
    assert block["nodes"][1][:3] == [0.01, 0.02, 0.03]
    assert glove_block(Reading(timestamp=0.0, grasp=0.5)) is None


def test_sink_sends_one_datagram_per_tick_and_a_glove_sample_only_when_new():
    sock, port = receiver()
    sink = UdpRecordSink("127.0.0.1", port, clock_ns=lambda: 42)
    reading = Reading(timestamp=3.0, human=HumanHand(np.zeros(20)))
    sink.publish(np.zeros(16), None, "live", reading)
    sink.publish(np.zeros(16), None, "live", reading)
    first, second = (json.loads(sock.recv(65535)) for _ in range(2))
    sink.close()
    sock.close()
    assert (first["seq"], second["seq"]) == (0, 1) and first["t_ns"] == 42
    assert first["glove"] is not None and second["glove"] is None


def test_sink_never_raises_into_the_control_loop():
    sink = UdpRecordSink("127.0.0.1", 9)  # nobody listens; UDP send still succeeds
    sink.publish(np.zeros(16), None, "live", None)
    sink.close()
    sink.publish(np.zeros(16), None, "live", None)  # closed socket: swallowed and counted
    assert sink.send_errors == 1
