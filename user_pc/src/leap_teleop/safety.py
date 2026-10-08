"""Keep the hand safe when the input goes quiet."""

from __future__ import annotations

import numpy as np


class StaleGuard:
    """live -> hold last output -> release to open, based on the age of the input."""

    def __init__(
        self,
        open_command: np.ndarray,
        stale_timeout: float = 0.5,
        release_timeout: float = 3.0,
    ) -> None:
        if not 0.0 < stale_timeout <= release_timeout:
            raise ValueError("need 0 < stale_timeout <= release_timeout")
        self._open = np.array(open_command, dtype=np.float64)
        self._stale = float(stale_timeout)
        self._release = float(release_timeout)
        self._last: np.ndarray | None = None
        self.mode = "waiting"

    def resolve(
        self, now: float, command: np.ndarray | None, command_time: float | None
    ) -> np.ndarray:
        if command is None or command_time is None:
            self.mode = "waiting"
            return self._open.copy()
        age = now - command_time
        if age <= self._stale:
            self.mode = "live"
            self._last = np.array(command, dtype=np.float64)
            return self._last.copy()
        if age <= self._release and self._last is not None:
            self.mode = "hold"
            return self._last.copy()
        self.mode = "release"
        self._last = self._open.copy()
        return self._open.copy()
