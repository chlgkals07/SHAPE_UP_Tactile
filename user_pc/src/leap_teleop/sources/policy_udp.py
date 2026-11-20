from __future__ import annotations

import json
import math
import socket
import time
from collections.abc import Callable

import numpy as np

from leap_teleop.sources.base import Source
from leap_teleop.types import HAND_DOF, Reading

PACKET_VERSION = 1


def parse_policy_packet(raw: bytes) -> list[float]:
    try:
        packet = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"not JSON: {error}") from error
    if not isinstance(packet, dict) or packet.get("v") != PACKET_VERSION:
        raise ValueError(f"expected a v{PACKET_VERSION} policy packet")
    hand = packet.get("hand_deg")
    if not isinstance(hand, list) or len(hand) != HAND_DOF:
        raise ValueError(f"hand_deg must be a list of {HAND_DOF} numbers")
    try:
        values = [float(v) for v in hand]
    except (TypeError, ValueError) as error:
        raise ValueError(f"hand_deg has a non-number: {error}") from error
    if not all(math.isfinite(v) for v in values):
        raise ValueError("hand_deg has NaN or infinity")
    return values


class PolicyUdpSource(Source):
    def __init__(self, host: str, port: int, clock: Callable[[], float] = time.monotonic):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        self.sock.setblocking(False)
        self.port = self.sock.getsockname()[1]
        self.clock = clock
        self.latest: Reading | None = None
        self.bad_packets = 0

    def poll(self, now: float) -> Reading | None:
        while True:
            try:
                raw = self.sock.recv(65535)
            except BlockingIOError:
                return self.latest
            try:
                hand = parse_policy_packet(raw)
            except ValueError:
                self.bad_packets += 1
                continue
            self.latest = Reading(timestamp=self.clock(), hand=np.array(hand))

    def close(self) -> None:
        self.sock.close()
