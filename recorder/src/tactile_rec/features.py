"""How raw readings become model inputs. Used by the converter AND by the live observation.

Keeping these in one place is what makes training data and run-time observations identical:
units, joint order, image rotation and tactile ordering are decided here and nowhere else.
"""

from __future__ import annotations

import cv2
import numpy as np

from tactile_rec.streams.specs import HAND_JOINTS
from tactile_rec.tactile import to_newtons

KEY_STATE = "observation.state"
KEY_ACTION = "action"
KEY_TACTILE = "observation.tactile.resultant"
KEY_TACTILE_DIST = "observation.tactile.distributed"
KEY_TACTILE_HR = "observation.tactile.resultant_hr"
KEY_TACTILE_DIST_HR = "observation.tactile.distributed_hr"
KEY_CURRENT = "observation.hand_current"
KEY_IMAGE = "observation.images."

_ROTATIONS = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def joint_vector(arm_rad: np.ndarray, hand_deg: np.ndarray, arm_dof: int) -> np.ndarray:
    """[arm joints (rad), 16 hand joints (rad)] as float32. Works on (D,) or (T, D) inputs.

    The arm values are used as recorded. In the wrist-flip mount joint6 sits near pi/2 in both
    the follower state and the leader command, so state and action stay consistent.
    """
    arm = np.asarray(arm_rad, dtype=np.float64)[..., :arm_dof]
    hand = np.deg2rad(np.asarray(hand_deg, dtype=np.float64))
    return np.concatenate([arm, hand], axis=-1).astype(np.float32)


def joint_names(arm_joints: list[str], arm_dof: int) -> list[str]:
    return list(arm_joints[:arm_dof]) + [f"leap_{name}" for name in HAND_JOINTS]


def tactile_vectors(
    decoded: dict[str, dict[str, np.ndarray]], order: tuple[str, ...]
) -> tuple[np.ndarray, np.ndarray]:
    """Decoded counts -> (resultant, distributed) in newtons, flattened in `order`.

    resultant: (T, len(order) * 3), distributed: (T, total_points * 3).
    Raises KeyError naming the missing place if the hand does not have a sensor in `order`.
    """
    missing = [place for place in order if place not in decoded]
    if missing:
        raise KeyError(f"no tactile sensor recorded for {missing}; recorded: {sorted(decoded)}")
    frames = decoded[order[0]]["resultant"].shape[0]
    resultant = np.concatenate([decoded[p]["resultant"] for p in order], axis=1)
    distributed = np.concatenate(
        [decoded[p]["distributed"].reshape(frames, -1) for p in order], axis=1
    )
    return to_newtons(resultant), to_newtons(distributed)


def tactile_names(order: tuple[str, ...], points: dict[str, int]) -> tuple[list[str], list[str]]:
    axes = ("fx", "fy", "fz")
    resultant = [f"{place}.{axis}" for place in order for axis in axes]
    distributed = [
        f"{place}.{index}.{axis}" for place in order for index in range(points[place])
        for axis in axes
    ]
    return resultant, distributed


def rotate_bgr(image_bgr: np.ndarray, rotation_deg: int) -> np.ndarray:
    """Stored camera frame (BGR, as captured) -> upright BGR. The only place rotation happens:
    the dataset, the live observation and the UI preview all go through here.

    rotation_deg is the clockwise rotation that makes the stored frame upright.
    """
    if rotation_deg in _ROTATIONS:
        return cv2.rotate(image_bgr, _ROTATIONS[rotation_deg])
    if rotation_deg != 0:
        raise ValueError(f"rotation_deg must be 0, 90, 180 or 270, got {rotation_deg}")
    return image_bgr


def orient_image(image_bgr: np.ndarray, rotation_deg: int) -> np.ndarray:
    """Stored camera frame (BGR, as captured) -> upright RGB."""
    return cv2.cvtColor(rotate_bgr(image_bgr, rotation_deg), cv2.COLOR_BGR2RGB)


def oriented_shape(height: int, width: int, rotation_deg: int) -> tuple[int, int, int]:
    return (width, height, 3) if rotation_deg in (90, 270) else (height, width, 3)
