"""Loaders for the tracked YAML configuration files."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from leap_teleop.hand.joints import ANGLE_NAMES
from leap_teleop.types import HAND_DOF, HUMAN_ANGLE_NAMES


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


@dataclass(frozen=True)
class ManusLeapConfig:
    """Tracked tuning for the Manus -> LEAP retargeter (config/manus_leap.yaml)."""

    topic: str
    sources: tuple[int, ...]  # per LEAP joint: index into HUMAN_ANGLE_NAMES
    side_gain: np.ndarray  # per LEAP joint, used by *_side joints
    side_max_deg: float
    side_floor_deg: float
    flex_max_deg: float
    flip_normal: bool
    ip_weight: float
    prior_weight: float
    smooth_weight: float
    one_euro_min_cutoff: float
    one_euro_beta: float
    urdf_offset_deg: np.ndarray
    fist_override_deg: Mapping[str, float]  # replaces postures.yaml fist targets for Manus


@dataclass(frozen=True)
class ManusCalibration:
    """Per-operator glove calibration (config/manus_calibration.yaml, gitignored)."""

    open_angles: np.ndarray  # HUMAN_ANGLE_NAMES order, degrees
    closed_angles: np.ndarray
    scale: float  # LEAP length / human length


def _human_vector(values: Mapping[str, float], name: str) -> np.ndarray:
    missing = sorted(set(HUMAN_ANGLE_NAMES) - set(values))
    unknown = sorted(set(values) - set(HUMAN_ANGLE_NAMES))
    if missing or unknown:
        raise ValueError(f"{name}: missing {missing}, unknown {unknown}")
    return np.array([float(values[n]) for n in HUMAN_ANGLE_NAMES], dtype=np.float64)


def load_manus_leap(path: str | Path) -> ManusLeapConfig:
    data = _load_mapping(path)
    try:
        joint_map = data["joint_map"]
        missing = sorted(set(ANGLE_NAMES) - set(joint_map))
        if missing:
            raise ValueError(f"{path}: joint_map is missing {missing}")
        unknown = sorted(set(joint_map.values()) - set(HUMAN_ANGLE_NAMES))
        if unknown:
            raise ValueError(f"{path}: joint_map uses unknown glove angles {unknown}")
        coupling, weights, one_euro = data["coupling"], data["thumb_ik"], data["one_euro"]
        gains = data.get("side_gain") or {}
        side_gain = make_posture({n: gains.get(n, 1.0) for n in ANGLE_NAMES})
        make_posture(gains)  # rejects unknown joint names
        fist_override = {str(k): float(v) for k, v in (data.get("fist_override_deg") or {}).items()}
        make_posture(fist_override)
        cfg = ManusLeapConfig(
            topic=str(data["topic"]),
            sources=tuple(HUMAN_ANGLE_NAMES.index(joint_map[n]) for n in ANGLE_NAMES),
            side_gain=side_gain,
            side_max_deg=float(coupling["side_max_deg"]),
            side_floor_deg=float(coupling["side_floor_deg"]),
            flex_max_deg=float(coupling["flex_max_deg"]),
            flip_normal=bool(weights.get("flip_normal", False)),
            ip_weight=float(weights["ip_weight"]),
            prior_weight=float(weights["prior_weight"]),
            smooth_weight=float(weights["smooth_weight"]),
            one_euro_min_cutoff=float(one_euro["min_cutoff"]),
            one_euro_beta=float(one_euro["beta"]),
            urdf_offset_deg=make_posture(data.get("urdf_offset_deg") or {}),
            fist_override_deg=fist_override,
        )
    except KeyError as missing_key:
        raise ValueError(f"{path} is missing {missing_key}") from None
    if cfg.flex_max_deg <= 0.0 or cfg.side_max_deg < 0.0 or cfg.side_floor_deg < 0.0:
        raise ValueError(f"{path}: coupling limits must be non-negative (flex_max_deg > 0)")
    return cfg


def load_manus_calibration(path: str | Path) -> ManusCalibration:
    data = _load_mapping(path)
    try:
        calibration = ManusCalibration(
            open_angles=_human_vector(data["open"], "open"),
            closed_angles=_human_vector(data["closed"], "closed"),
            scale=float(data["scale"]),
        )
    except KeyError as missing_key:
        raise ValueError(f"{path} is missing {missing_key}") from None
    if not np.isfinite(calibration.scale) or calibration.scale <= 0.0:
        raise ValueError(f"{path}: scale must be positive")
    return calibration


def save_manus_calibration(calibration: ManusCalibration, path: str | Path) -> None:
    payload = {
        "open": dict(zip(HUMAN_ANGLE_NAMES, calibration.open_angles.round(2).tolist())),
        "closed": dict(zip(HUMAN_ANGLE_NAMES, calibration.closed_angles.round(2).tolist())),
        "scale": round(float(calibration.scale), 4),
    }
    header = "# Manus 글러브 사용자 캘리브레이션 (tools/calibrate_manus.py가 생성). 단위: 도.\n"
    Path(path).write_text(header + yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
