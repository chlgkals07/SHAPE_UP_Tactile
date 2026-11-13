"""Record-only UDP output for the tactile-rec hub (recorder/src/tactile_rec/streams/hand_udp.py).

Same interface as RosPublisher / CsvLogger (publish / close), so the control loop treats it as
one more record-only sink. Never on the control path: publish() swallows every error, and UDP
to localhost does not block when nobody listens.

One JSON datagram per control tick. `t_ns` is CLOCK_MONOTONIC, the clock the hub also uses, so
no clock synchronisation is needed between the two processes. Packet layout: see hand_udp.py.
"""

from __future__ import annotations

import json
import socket
import time
from collections.abc import Callable

import numpy as np

from leap_teleop.types import Reading

PACKET_VERSION = 1
DEFAULT_PORT = 47800


def _list(values) -> list[float] | None:
    if values is None:
        return None
    return [round(float(v), 4) for v in np.asarray(values, dtype=float)]


def build_packet(
    seq: int,
    t_ns: int,
    command_degrees,
    sent_degrees,
    feedback,
    mode: str,
    glove: dict | None,
) -> dict:
    return {
        "v": PACKET_VERSION,
        "seq": seq,
        "t_ns": t_ns,
        "mode": mode,
        "cmd": _list(command_degrees),
        "sent": _list(sent_degrees),
        "pos": _list(feedback.positions_degrees) if feedback is not None else None,
        "vel": _list(feedback.velocities_degrees_per_second) if feedback is not None else None,
        "cur": _list(feedback.currents_milliamps) if feedback is not None else None,
        "glove": glove,
    }


def glove_block(reading: Reading) -> dict | None:
    """The glove part of a packet: ergonomics plus every raw skeleton node the SDK sent."""
    human = reading.human
    if human is None:
        return None
    names, poses = [], []
    for name, pose in human.nodes or ():
        names.append(name)
        poses.append([round(float(v), 5) for v in pose])
    return {
        "t_ns": int(round(reading.timestamp * 1e9)),
        "ergo": _list(human.angles),
        "nodes": poses,
        "node_names": names,
    }


class UdpRecordSink:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        driver=None,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._address = (host, port)
        self._driver = driver
        self._clock_ns = clock_ns
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._seq = 0
        self._last_human_time: float | None = None
        self.send_errors = 0

    def publish(self, command_degrees, feedback, mode: str, reading: Reading | None) -> None:
        try:
            self._publish(command_degrees, feedback, mode, reading)
        except Exception:  # noqa: BLE001 - recording must never stop the hand
            self.send_errors += 1

    def _publish(self, command_degrees, feedback, mode, reading) -> None:
        t_ns = self._clock_ns()
        glove = None
        if reading is not None and reading.human is not None:
            if reading.timestamp != self._last_human_time:  # only a new glove sample
                self._last_human_time = reading.timestamp
                glove = glove_block(reading)
        sent_fn = getattr(self._driver, "last_sent_degrees", None)
        packet = build_packet(
            self._seq, t_ns, command_degrees, sent_fn() if sent_fn is not None else None,
            feedback, mode, glove,
        )
        self._seq += 1
        self._socket.sendto(json.dumps(packet, separators=(",", ":")).encode(), self._address)

    def close(self) -> None:
        self._socket.close()
