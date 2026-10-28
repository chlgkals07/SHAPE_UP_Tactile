"""Manus glove (HumanHand) -> LEAP Hand command: affine fingers, affine or IK thumb.

Affine: range joints (*_flex and thumb_cmc_side) = clip((h - h_open) / (h_closed - h_open), 0, 1)
        * fist target; finger *_side = side_gain * (h - h_open), then flex-side coupling.
Thumb IK, BiDex style (leap-hand/Bidex_Manus_Teleop matches the last two points of each finger).
Radians, URDF frame, positions in cm:
    min |tip(q) - tip*|^2 + w_ip |ip(q) - ip*|^2 + w_p |q - q_aff|^2 + w_s |q - q_prev|^2
Four joints for one 3D tip leave a family of solutions; the IP joint point picks the one that
follows the operator's own thumb. Design rationale:
docs/superpowers/specs/2026-10-28-manus-leap-thumb-ik-rationale.md
"""

from __future__ import annotations

import numpy as np

from leap_teleop.config import ManusCalibration, ManusLeapConfig
from leap_teleop.filters import OneEuroFilter
from leap_teleop.hand.joints import ANGLE_NAMES
from leap_teleop.kinematics import Chain, least_squares
from leap_teleop.types import HAND_DOF, HumanHand, Reading

THUMB_MODES = ("ik", "affine")
THUMB = slice(12, 16)
THUMB_JOINTS = ("12", "13", "14", "15")
RANGE_GROUPS = ((1, 2, 3), (5, 6, 7), (9, 10, 11), (12, 13, 14, 15))
SIDE_FLEX_PAIRS = ((0, 1), (4, 5), (8, 9))  # index, middle, ring
MIN_SPAN_DEG = 10.0
IS_RANGE = np.array([n.endswith("_flex") or n == "thumb_cmc_side" for n in ANGLE_NAMES])
CM = 100.0
RESET_GAP_S = 0.5  # input gap after which IK warm start and filter history are stale


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / max(float(np.linalg.norm(vector)), 1e-9)


def _palm_basis(across: np.ndarray, along: np.ndarray, flip_normal: bool = False) -> np.ndarray:
    """Columns: across (toward the index side), along (toward the fingers), palm normal."""
    across = _unit(across)
    along = _unit(along - (along @ across) * across)
    normal = np.cross(across, along)
    return np.column_stack((across, along, -normal if flip_normal else normal))


def human_palm_basis(human: HumanHand, flip_normal: bool = False) -> np.ndarray:
    return _palm_basis(
        human.point("index_mcp") - human.point("pinky_mcp"),
        human.point("middle_mcp") - human.point("wrist"),
        flip_normal,
    )


class ManusLeapRetargeter:
    def __init__(
        self,
        cfg: ManusLeapConfig,
        calibration: ManusCalibration,
        fist_pose: np.ndarray,
        chain: Chain,
        thumb_mode: str = "ik",
    ) -> None:
        if thumb_mode not in THUMB_MODES:
            raise ValueError(f"thumb_mode must be one of {THUMB_MODES}")
        self._cfg = cfg
        self._chain = chain
        self._thumb_mode = thumb_mode
        sources = list(cfg.sources)
        self._h_open = calibration.open_angles[sources]
        self._span = calibration.closed_angles[sources] - self._h_open
        self._scale = calibration.scale
        self._fist = np.array(fist_pose, dtype=np.float64)
        if self._fist.shape != (HAND_DOF,):
            raise ValueError(f"fist_pose must have shape ({HAND_DOF},)")
        for name, value in cfg.fist_override_deg.items():
            self._fist[ANGLE_NAMES.index(name)] = value
        self._lower, self._upper = chain.limits(THUMB_JOINTS)
        # LEAP reference frame at q = 0: thumb base and palm axes (ring stands in for pinky).
        self._thumb_base = chain.link_position("thumb_temp_base", {})
        self._leap_basis = _palm_basis(
            chain.link_position("mcp_joint", {}) - chain.link_position("mcp_joint_3", {}),
            np.array([0.0, 0.0, 1.0]),
        )
        self._q_prev: np.ndarray | None = None
        self._filter = OneEuroFilter(cfg.one_euro_min_cutoff, cfg.one_euro_beta)
        self._last: tuple[float, np.ndarray] | None = None

    def __call__(self, reading: Reading) -> np.ndarray:
        if reading.human is None:
            raise ValueError("ManusLeapRetargeter needs a human-hand reading")
        # Sources repeat the latest reading every tick; the filter needs increasing time.
        if self._last is not None and reading.timestamp <= self._last[0]:
            return self._last[1].copy()
        if self._last is not None and reading.timestamp - self._last[0] > RESET_GAP_S:
            self._q_prev = None
            self._filter.reset()
        command = self.affine(reading.human)
        if self._thumb_mode == "ik" and reading.human.keypoints is not None:
            command[THUMB] = self.thumb_ik(reading.human, command)
        else:
            self._q_prev = None  # when keypoints return, restart IK from the affine thumb
        output = self._filter.filter(command, reading.timestamp)
        self._last = (reading.timestamp, output)
        return output.copy()

    def affine(self, human: HumanHand) -> np.ndarray:
        """All 16 joints from the glove angles (degrees), coupling applied."""
        delta = human.angles[list(self._cfg.sources)] - self._h_open
        command = np.where(IS_RANGE, 0.0, self._cfg.side_gain * delta)
        for group in RANGE_GROUPS:
            group = np.array(group)
            usable = np.abs(self._span[group]) >= MIN_SPAN_DEG
            ratios = np.zeros(group.size)
            ratios[usable] = np.clip(delta[group[usable]] / self._span[group[usable]], 0.0, 1.0)
            # A joint the glove barely moved borrows its finger's median ratio.
            if usable.any():
                ratios[~usable] = float(np.median(ratios[usable]))
            command[group] = ratios * self._fist[group]
        for side, flex in SIDE_FLEX_PAIRS:
            bend = np.clip(command[flex] / self._cfg.flex_max_deg, 0.0, 1.0)
            limit = self._cfg.side_max_deg * (1.0 - bend) + self._cfg.side_floor_deg
            command[side] = np.clip(command[side], -limit, limit)
        return command

    def thumb_ik(self, human: HumanHand, command: np.ndarray) -> np.ndarray:
        """Thumb joints (degrees) matching the operator's thumb tip and IP joint."""
        offset = self._cfg.urdf_offset_deg[THUMB]
        tip_target, ip_target = self.thumb_targets(human)
        prior = np.radians(command[THUMB] + offset)
        previous = prior if self._q_prev is None else self._q_prev
        w_ip, w_p, w_s = (np.sqrt(w) for w in (
            self._cfg.ip_weight, self._cfg.prior_weight, self._cfg.smooth_weight))

        def residual(q: np.ndarray) -> np.ndarray:
            tip, ip = self.thumb_points(q)
            return np.concatenate((
                (tip - tip_target) * CM,
                w_ip * (ip - ip_target) * CM,
                w_p * (q - prior),
                w_s * (q - previous),
            ))

        # ponytail: 10 iterations per tick (~3 ms worst case); warm start keeps converging
        # next tick. Unreachable targets would otherwise burn all iterations every tick.
        solved = least_squares(residual, previous, self._lower, self._upper, iterations=10)
        self._q_prev = solved
        return np.degrees(solved) - offset

    @property
    def thumb_base(self) -> np.ndarray:
        return self._thumb_base.copy()

    @property
    def palm_normal(self) -> np.ndarray:
        return self._leap_basis[:, 2].copy()

    def thumb_targets(self, human: HumanHand) -> tuple[np.ndarray, np.ndarray]:
        """Operator thumb tip and IP joint moved into the LEAP palm frame (metres, URDF root)."""
        rotation = self._leap_basis @ human_palm_basis(human, self._cfg.flip_normal).T
        base = human.point("thumb_cmc")
        return tuple(
            self._thumb_base + self._scale * rotation @ (human.point(name) - base)
            for name in ("thumb_tip", "thumb_ip")
        )

    def thumb_points(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """LEAP thumb tip and IP joint (joint 15) positions for thumb joints q (radians, URDF)."""
        joints = dict(zip(THUMB_JOINTS, q))
        return (
            self._chain.link_position("thumb_tip_head", joints),
            self._chain.link_position("thumb_fingertip", joints),
        )
