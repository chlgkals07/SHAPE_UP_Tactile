"""Hub: owns every stream of the rig and one event log.

The recorder, the UI and (later) a policy all read from the same Hub object, so they see the
same samples with the same timestamps.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

from tactile_rec.clock import Clock
from tactile_rec.config import Config
from tactile_rec.stream import Stream
from tactile_rec.types import Health

MAX_EVENTS = 2000


def build_streams(config: Config, clock: Clock) -> dict[str, Stream]:
    """Create the streams named in the config. Device libraries are imported only by the
    adapters that need them, and only when they connect."""
    streams: dict[str, Stream] = {}
    for name, cfg in config.streams.items():
        kind = cfg["type"]
        if kind == "fake":
            from tactile_rec.streams.fake import FakeStream

            streams[name] = FakeStream(name, cfg, clock)
        elif kind == "arm_zenoh":
            from tactile_rec.streams.arm_zenoh import ArmZenohStream

            streams[name] = ArmZenohStream(name, cfg, clock)
        elif kind == "hand_udp":
            from tactile_rec.streams.hand_udp import HandUdpStream

            hand = HandUdpStream(name, cfg, clock)
            streams[name] = hand
            if hand.glove is not None:
                streams[hand.glove.name] = hand.glove
        elif kind == "paxini":
            from tactile_rec.streams.paxini import PaxiniStream

            streams[name] = PaxiniStream(name, cfg, clock)
        elif kind == "realsense":
            from tactile_rec.streams.realsense import RealSenseStream

            streams[name] = RealSenseStream(name, cfg, clock)
        else:  # config.py rejects unknown types; this guards a new type added there only
            raise ValueError(f"no adapter for stream type {kind!r}")
    return streams


class Hub:
    def __init__(
        self, config: Config, clock: Clock | None = None, streams: dict[str, Stream] | None = None
    ):
        self.config = config
        self.clock = clock or Clock()
        self.streams = streams if streams is not None else build_streams(config, self.clock)
        self._events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        self._lock = threading.Lock()
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        for stream in self.streams.values():
            stream.start()
        self.add_event("hub_start")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for stream in self.streams.values():
            stream.stop()

    def health(self) -> dict[str, Health]:
        now_ns = self.clock.now_ns()
        return {name: stream.health(now_ns) for name, stream in self.streams.items()}

    def add_event(self, kind: str, **detail: Any) -> dict[str, Any]:
        event = {"t_ns": self.clock.now_ns(), "type": kind, **detail}
        with self._lock:
            self._events.append(event)
        return event

    def events_since(self, t_ns: int) -> list[dict[str, Any]]:
        with self._lock:
            return [e for e in self._events if e["t_ns"] >= t_ns]

    def tactile_streams(self) -> dict[str, Stream]:
        return {n: s for n, s in self.streams.items() if "payload" in s.spec.fields}

    def zero_tactile(self) -> list[str]:
        """Zero every tactile board at its current load. Returns the boards asked."""
        names = []
        for name, stream in self.tactile_streams().items():
            zero = getattr(stream, "zero", None)
            if zero is not None:
                zero()
                names.append(name)
        self.add_event("tactile_zero", streams=names)
        return names
