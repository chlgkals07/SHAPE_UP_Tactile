"""Output boundary: anything that can move a hand from a 16-angle command."""

from __future__ import annotations

from typing import Protocol

import numpy as np


class HandDriver(Protocol):
    def start(self) -> None:
        """Connect and energize. Must not move the hand away from its current pose."""

    def command(self, angles_degrees: np.ndarray) -> None:
        """Apply a HandCommand (16 degrees, ANGLE_NAMES order, 0 = open)."""

    def close(self) -> None:
        """De-energize and release the device. Safe to call after a failed start."""
