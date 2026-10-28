"""Manus glove (HumanHand) -> LEAP Hand command: affine fingers, affine or IK thumb.

Fingers: *_flex = clip((h - h_open) / (h_closed - h_open), 0, 1) * fist target,
         *_side = side_gain * (h - h_open), then flex-side coupling.
Thumb IK (radians, URDF frame, position in cm):
    min |f(q) - p*|^2 + w_o |pad(q) - dir(q)|^2 + w_p |q - q_aff|^2 + w_s |q - q_prev|^2
pad(q) is the thumb pad normal (where IP flexion moves the tip) and dir(q) points from the
thumb tip to the middle of the LEAP index distal segment, so the pad faces the finger.
Four joints for a 3D target leave a family of solutions; the pad and prior terms pick one.
Design rationale: docs/superpowers/specs/2026-10-28-manus-leap-thumb-ik-rationale.md
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
INDEX_JOINTS = ("0", "1", "2", "3")
FLEX_GROUPS = ((1, 2, 3), (5, 6, 7), (9, 10, 11), (13, 14, 15))
SIDE_FLEX_PAIRS = ((0, 1), (4, 5), (8, 9))  # index, middle, ring
MIN_SPAN_DEG = 10.0
IS_FLEX = np.array([name.endswith("_flex") for name in ANGLE_NAMES])
CM = 100.0


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
        command = self.affine(reading.human)
        if self._thumb_mode == "ik" and reading.human.keypoints is not None:
            command[THUMB] = self.thumb_ik(reading.human, command)
        output = self._filter.filter(command, reading.timestamp)
        self._last = (reading.timestamp, output)
        return output.copy()

    def affine(self, human: HumanHand) -> np.ndarray:
        """All 16 joints from the glove angles (degrees), coupling applied."""
        delta = human.angles[list(self._cfg.sources)] - self._h_open
        command = np.where(IS_FLEX, 0.0, self._cfg.side_gain * delta)
        for group in FLEX_GROUPS:
            group = np.array(group)
            usable = np.abs(self._span[group]) >= MIN_SPAN_DEG
            ratios = np.zeros(group.size)
            ratios[usable] = np.clip(delta[group[usable]] / self._span[group[usable]], 0.0, 1.0)
            # A joint the glove barely moved borrows its finger's median bend.
            if usable.any():
                ratios[~usable] = float(np.median(ratios[usable]))
            command[group] = ratios * self._fist[group]
        for side, flex in SIDE_FLEX_PAIRS:
            bend = np.clip(command[flex] / self._cfg.flex_max_deg, 0.0, 1.0)
            limit = self._cfg.side_max_deg * (1.0 - bend) + self._cfg.side_floor_deg
            command[side] = np.clip(command[side], -limit, limit)
        return command

    def thumb_ik(self, human: HumanHand, command: np.ndarray) -> np.ndarray:
        """Thumb joints (degrees) for the human thumb tip, starting from the affine thumb."""
        offset = self._cfg.urdf_offset_deg
        urdf = np.radians(command + offset)
        rotation = self._leap_basis @ human_palm_basis(human, self._cfg.flip_normal).T
        target = self._thumb_base + self._scale * rotation @ (
            human.point("thumb_tip") - human.point("thumb_cmc")
        )
        index_q = dict(zip(INDEX_JOINTS, urdf[0:4]))
        index_pad = 0.5 * (
            self._chain.link_position("fingertip", index_q)
            + self._chain.link_position("index_tip_head", index_q)
        )
        prior = urdf[THUMB]
        previous = prior if self._q_prev is None else self._q_prev
        w_o, w_p, w_s = (np.sqrt(w) for w in (
            self._cfg.opposition_weight, self._cfg.prior_weight, self._cfg.smooth_weight))

        def residual(q: np.ndarray) -> np.ndarray:
            tip, pad = self.thumb_tip_and_pad(q)
            return np.concatenate((
                (tip - target) * CM,
                w_o * (pad - _unit(index_pad - tip)),
                w_p * (q - prior),
                w_s * (q - previous),
            ))

        # ponytail: 10 iterations per tick (~3 ms worst case); warm start keeps converging
        # next tick. Unreachable targets would otherwise burn all iterations every tick.
        solved = least_squares(residual, previous, self._lower, self._upper, iterations=10)
        self._q_prev = solved
        return np.degrees(solved) - offset[THUMB]

    def thumb_tip_and_pad(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Thumb tip position and pad normal (unit) for thumb joints q (radians, URDF)."""
        tip = self._chain.link_position("thumb_tip_head", dict(zip(THUMB_JOINTS, q)))
        flexed = np.array(q, dtype=np.float64)
        flexed[3] += 1e-4  # a little more IP flexion moves the tip toward the pad side
        nudged = self._chain.link_position("thumb_tip_head", dict(zip(THUMB_JOINTS, flexed)))
        return tip, _unit(nudged - tip)
