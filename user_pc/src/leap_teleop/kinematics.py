"""Forward kinematics from a URDF and a small bounded least-squares solver (numpy only).

Joint values are radians keyed by URDF joint name. For the LEAP Hand those names are
"0".."15", the same order as ``ANGLE_NAMES``, and 0 rad is the open hand.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Editable install / PYTHONPATH=src layout: user_pc/assets next to user_pc/src.
LEAP_URDF = Path(__file__).resolve().parents[2] / "assets" / "leap_hand_right.urdf"


def _rpy_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr, cp, sp, cy, sy = (np.cos(roll), np.sin(roll), np.cos(pitch), np.sin(pitch),
                              np.cos(yaw), np.sin(yaw))
    rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]])
    return rz @ ry @ rx


def _axis_angle(axis: np.ndarray, angle: float) -> np.ndarray:
    k = np.array([[0.0, -axis[2], axis[1]], [axis[2], 0.0, -axis[0]], [-axis[1], axis[0], 0.0]])
    return np.eye(3) + np.sin(angle) * k + (1.0 - np.cos(angle)) * (k @ k)


@dataclass(frozen=True)
class _Joint:
    name: str
    parent: str
    origin_rotation: np.ndarray
    origin_xyz: np.ndarray
    axis: np.ndarray | None  # None for fixed joints
    lower: float
    upper: float


class Chain:
    """Tree of URDF joints, indexed by child link."""

    def __init__(self, joints_by_child: Mapping[str, _Joint]) -> None:
        self._by_child = dict(joints_by_child)
        self._by_name = {joint.name: joint for joint in self._by_child.values()}

    def link_pose(self, link: str, q: Mapping[str, float]) -> tuple[np.ndarray, np.ndarray]:
        """Rotation and position of ``link`` in the root frame. Missing joints count as 0."""
        joint = self._by_child.get(link)
        if joint is None:
            return np.eye(3), np.zeros(3)
        parent_rotation, parent_position = self.link_pose(joint.parent, q)
        rotation = parent_rotation @ joint.origin_rotation
        position = parent_rotation @ joint.origin_xyz + parent_position
        if joint.axis is not None:
            rotation = rotation @ _axis_angle(joint.axis, float(q.get(joint.name, 0.0)))
        return rotation, position

    def link_position(self, link: str, q: Mapping[str, float]) -> np.ndarray:
        return self.link_pose(link, q)[1]

    def limits(self, names: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
        joints = [self._by_name[name] for name in names]
        return (np.array([j.lower for j in joints]), np.array([j.upper for j in joints]))


def load_chain(urdf_path: str | Path) -> Chain:
    root = ET.parse(urdf_path).getroot()
    joints: dict[str, _Joint] = {}
    for element in root.findall("joint"):
        origin = element.find("origin")
        xyz = origin.get("xyz", "0 0 0") if origin is not None else "0 0 0"
        rpy = origin.get("rpy", "0 0 0") if origin is not None else "0 0 0"
        axis = None
        lower = upper = 0.0
        if element.get("type") != "fixed":
            axis_element = element.find("axis")
            axis = np.array((axis_element.get("xyz") if axis_element is not None else "1 0 0")
                            .split(), dtype=np.float64)
            axis = axis / np.linalg.norm(axis)
            limit = element.find("limit")
            if limit is not None:
                lower, upper = float(limit.get("lower", 0.0)), float(limit.get("upper", 0.0))
        child = element.find("child").get("link")
        joints[child] = _Joint(
            name=element.get("name"),
            parent=element.find("parent").get("link"),
            origin_rotation=_rpy_matrix(*np.array(rpy.split(), dtype=np.float64)),
            origin_xyz=np.array(xyz.split(), dtype=np.float64),
            axis=axis,
            lower=lower,
            upper=upper,
        )
    return Chain(joints)


def least_squares(
    residual: Callable[[np.ndarray], np.ndarray],
    x0: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    *,
    iterations: int = 40,
    damping: float = 2e-2,
    tolerance: float = 1e-5,
) -> np.ndarray:
    """Minimise ||residual(x)||^2 inside [lower, upper] with Levenberg-Marquardt.

    The Jacobian is a forward difference, so ``residual`` only needs to be evaluable.
    A step that does not lower the cost is rejected and the damping raised.
    """
    x = np.clip(np.array(x0, dtype=np.float64), lower, upper)
    r = residual(x)
    cost = float(r @ r)
    mu = damping
    eps = 1e-6
    for _ in range(iterations):
        jacobian = np.empty((r.size, x.size))
        for i in range(x.size):
            step = np.zeros_like(x)
            step[i] = eps
            jacobian[:, i] = (residual(x + step) - r) / eps
        delta = np.linalg.solve(
            jacobian.T @ jacobian + mu**2 * np.eye(x.size), -jacobian.T @ r
        )
        candidate = np.clip(x + delta, lower, upper)
        r_candidate = residual(candidate)
        cost_candidate = float(r_candidate @ r_candidate)
        if cost_candidate < cost:
            moved = float(np.linalg.norm(candidate - x))
            x, r, cost = candidate, r_candidate, cost_candidate
            mu = max(mu / 2.0, 1e-6)
            if moved < tolerance:
                break
        else:
            mu *= 4.0
    return x
