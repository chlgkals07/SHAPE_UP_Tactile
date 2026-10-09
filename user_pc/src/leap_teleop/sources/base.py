"""Input boundary: anything that can say what the hand should do right now."""

from __future__ import annotations

from abc import ABC, abstractmethod

from leap_teleop.types import Reading


class Source(ABC):
    @abstractmethod
    def poll(self, now: float) -> Reading | None:
        """Return the latest reading, or None if nothing has arrived yet."""

    @property
    def stop_requested(self) -> bool:
        return False

    def close(self) -> None:
        """Release any resources (terminal, ROS node). Default: nothing to do."""
