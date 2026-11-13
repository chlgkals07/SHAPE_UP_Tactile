"""The one place time is read.

Every sample is stamped with CLOCK_MONOTONIC nanoseconds. On Linux that clock is shared by all
processes on the PC, so a stamp taken inside `leap_teleop` is directly comparable with one
taken in the hub. Wall-clock time is only kept as an anchor pair per episode.
"""

from __future__ import annotations

import time


class Clock:
    def now_ns(self) -> int:
        return time.monotonic_ns()

    def wall_ns(self) -> int:
        return time.time_ns()

    def anchor(self) -> dict[str, int]:
        """A (monotonic, wall) pair read back to back, to map one clock onto the other."""
        return {"mono_ns": self.now_ns(), "wall_ns": self.wall_ns()}


class FakeClock(Clock):
    """Manually advanced clock for tests."""

    def __init__(self, start_ns: int = 1_000_000_000, wall_offset_ns: int = 1_700_000_000 * 10**9):
        self._now = start_ns
        self._wall_offset = wall_offset_ns

    def now_ns(self) -> int:
        return self._now

    def wall_ns(self) -> int:
        return self._now + self._wall_offset

    def advance(self, seconds: float) -> int:
        self._now += int(round(seconds * 1e9))
        return self._now

    def set_ns(self, now_ns: int) -> None:
        self._now = now_ns
