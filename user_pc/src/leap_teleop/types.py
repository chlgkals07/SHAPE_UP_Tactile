"""Shared data contract between sources, retargeters and hand drivers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from leap_teleop.hand.joints import ANGLE_NAMES

HAND_DOF = len(ANGLE_NAMES)

# Manus ergonomics order (thumb, index, middle, ring, pinky x 4). For the thumb Manus calls
# the CMC "MCP", the MCP "PIP" and the IP "DIP". Names unverified against the Linux SDK.
HUMAN_ANGLE_NAMES = tuple(
    f"{finger}{joint}"
    for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky")
    for joint in ("MCPSpread", "MCPStretch", "PIPStretch", "DIPStretch")
)
# The few glove skeleton points the thumb IK and calibration need (metres, glove frame).
KEYPOINT_NAMES = (
    "wrist", "thumb_cmc", "thumb_tip", "index_mcp", "index_tip", "middle_mcp", "pinky_mcp",
)


def _finite_array(values, shape: tuple[int, ...], name: str) -> np.ndarray:
    array = np.array(values, dtype=np.float64)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains NaN or infinity")
    return array


@dataclass(frozen=True)
class HumanHand:
    """One glove sample: joint angles in degrees and optional skeleton keypoints."""

    angles: np.ndarray
    keypoints: np.ndarray | None = None

    def __post_init__(self) -> None:
        angles = _finite_array(self.angles, (len(HUMAN_ANGLE_NAMES),), "angles")
        object.__setattr__(self, "angles", angles)
        if self.keypoints is not None:
            points = _finite_array(self.keypoints, (len(KEYPOINT_NAMES), 3), "keypoints")
            object.__setattr__(self, "keypoints", points)

    def angle(self, name: str) -> float:
        return float(self.angles[HUMAN_ANGLE_NAMES.index(name)])

    def point(self, name: str) -> np.ndarray:
        if self.keypoints is None:
            raise ValueError("this HumanHand has no keypoints")
        return self.keypoints[KEYPOINT_NAMES.index(name)]


@dataclass(frozen=True)
class Reading:
    """One input sample: a scalar grasp (0 open .. 1 closed), a full LEAP hand, or a human hand."""

    timestamp: float
    grasp: float | None = None
    hand: np.ndarray | None = None
    human: HumanHand | None = None

    def __post_init__(self) -> None:
        given = sum(value is not None for value in (self.grasp, self.hand, self.human))
        if given != 1:
            raise ValueError("Reading needs exactly one of grasp, hand or human")
        if self.grasp is not None and not 0.0 <= self.grasp <= 1.0:
            raise ValueError(f"grasp must be in [0, 1], got {self.grasp}")
        if self.hand is not None:
            object.__setattr__(self, "hand", _finite_array(self.hand, (HAND_DOF,), "hand"))
        if self.human is not None and not isinstance(self.human, HumanHand):
            raise ValueError("human must be a HumanHand")


Retargeter = Callable[[Reading], np.ndarray]
