"""Shared data contract between sources, retargeters and hand drivers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from leap_teleop.hand.joints import ANGLE_NAMES

HAND_DOF = len(ANGLE_NAMES)


@dataclass(frozen=True)
class Reading:
    """One input sample: either a scalar grasp (0 open .. 1 closed) or a full hand."""

    timestamp: float
    grasp: float | None = None
    hand: np.ndarray | None = None

    def __post_init__(self) -> None:
        if (self.grasp is None) == (self.hand is None):
            raise ValueError("Reading needs exactly one of grasp or hand")
        if self.grasp is not None and not 0.0 <= self.grasp <= 1.0:
            raise ValueError(f"grasp must be in [0, 1], got {self.grasp}")
        if self.hand is not None:
            hand = np.array(self.hand, dtype=np.float64)
            if hand.shape != (HAND_DOF,):
                raise ValueError(f"hand must have shape ({HAND_DOF},), got {hand.shape}")
            if not np.all(np.isfinite(hand)):
                raise ValueError("hand contains NaN or infinity")
            object.__setattr__(self, "hand", hand)


Retargeter = Callable[[Reading], np.ndarray]
