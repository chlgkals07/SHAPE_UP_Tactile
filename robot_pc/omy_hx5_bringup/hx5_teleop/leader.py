"""Extract the OMY-L100 trigger from its seven-joint leader trajectory."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class LeaderGripperConfig:
    topic: str
    joint_name: str
    open_value: float
    closed_value: float

    def __post_init__(self) -> None:
        if not self.topic or not self.joint_name:
            raise ValueError("leader topic and joint name are required")
        if not all(math.isfinite(v) for v in (self.open_value, self.closed_value)):
            raise ValueError("leader endpoints must be finite")
        if self.open_value == self.closed_value:
            raise ValueError("leader endpoints must differ")


def grasp_from_trajectory(
    joint_names: Sequence[str],
    points_positions: Sequence[Sequence[float]],
    cfg: LeaderGripperConfig,
) -> float | None:
    """Return 0 for open and 1 for closed, independent of joint ordering."""
    if len(set(joint_names)) != len(joint_names) or cfg.joint_name not in joint_names:
        return None
    if not points_positions:
        return None
    index = list(joint_names).index(cfg.joint_name)
    positions = points_positions[0]
    if len(positions) != len(joint_names):
        return None
    try:
        value = float(positions[index])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    grasp = (value - cfg.open_value) / (cfg.closed_value - cfg.open_value)
    return min(1.0, max(0.0, grasp))
