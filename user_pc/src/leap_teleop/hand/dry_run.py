"""HandDriver that only logs, for checking the pipeline without hardware."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


class LogDriver:
    def __init__(self, every: int = 25, out: Callable[[str], None] = print) -> None:
        if every < 1:
            raise ValueError("every must be at least 1")
        self._every = every
        self._out = out
        self._count = 0

    def start(self) -> None:
        self._out("[dry-run] start (no hardware)")

    def command(self, angles_degrees: np.ndarray) -> None:
        if self._count % self._every == 0:
            self._out(f"[dry-run] cmd max={float(np.max(angles_degrees)):.1f} deg")
        self._count += 1

    def close(self) -> None:
        self._out("[dry-run] close")
