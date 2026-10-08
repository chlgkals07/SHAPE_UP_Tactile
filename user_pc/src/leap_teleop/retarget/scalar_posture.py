"""Map a scalar grasp (0 open .. 1 fist) onto a HandCommand by linear interpolation."""

from __future__ import annotations

import numpy as np

from leap_teleop.types import HAND_DOF, Reading


class ScalarPostureRetargeter:
    def __init__(self, open_pose: np.ndarray, fist_pose: np.ndarray) -> None:
        self._open = np.array(open_pose, dtype=np.float64)
        self._fist = np.array(fist_pose, dtype=np.float64)
        for name, pose in (("open_pose", self._open), ("fist_pose", self._fist)):
            if pose.shape != (HAND_DOF,):
                raise ValueError(f"{name} must have shape ({HAND_DOF},), got {pose.shape}")

    def __call__(self, reading: Reading) -> np.ndarray:
        if reading.grasp is None:
            raise ValueError("ScalarPostureRetargeter needs a grasp reading")
        return self._open + reading.grasp * (self._fist - self._open)
