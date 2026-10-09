"""Loaders for the tracked YAML configuration files."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from leap_teleop.hand.joints import ANGLE_NAMES
from leap_teleop.types import HAND_DOF


def make_posture(changes: Mapping[str, float]) -> np.ndarray:
    """Build a HandCommand (degrees, ANGLE_NAMES order) from named joint values."""
    unknown = sorted(set(changes) - set(ANGLE_NAMES))
    if unknown:
        raise ValueError(f"Unknown LEAP Hand joint names: {unknown}")
    posture = np.zeros(HAND_DOF, dtype=np.float64)
    for name, value in changes.items():
        posture[ANGLE_NAMES.index(name)] = float(value)
    return posture


def _load_mapping(path: str | Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_postures(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (open_pose, fist_pose) as HandCommands."""
    data = _load_mapping(path)
    poses = []
    for key in ("open", "fist"):
        if key not in data:
            raise ValueError(f"{path} is missing the '{key}' posture")
        poses.append(make_posture(data[key] or {}))
    return poses[0], poses[1]


@dataclass(frozen=True)
class LeaderGripperConfig:
    topic: str
    joint_name: str
    open_value: float
    closed_value: float


def load_leader_gripper(path: str | Path) -> LeaderGripperConfig:
    data = _load_mapping(path)
    try:
        cfg = LeaderGripperConfig(
            topic=str(data["topic"]),
            joint_name=str(data["joint_name"]),
            open_value=float(data["open_value"]),
            closed_value=float(data["closed_value"]),
        )
    except KeyError as missing:
        raise ValueError(f"{path} is missing {missing}") from None
    if cfg.open_value == cfg.closed_value:
        raise ValueError("open_value and closed_value must differ")
    return cfg
