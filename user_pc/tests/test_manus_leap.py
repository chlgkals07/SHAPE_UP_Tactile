from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from leap_teleop.config import (
    ManusCalibration,
    load_manus_calibration,
    load_manus_leap,
    load_postures,
)
from leap_teleop.hand.joints import ANGLE_NAMES
from leap_teleop.kinematics import load_chain
from leap_teleop.retarget.manus_leap import THUMB, THUMB_JOINTS, ManusLeapRetargeter
from leap_teleop.types import HUMAN_ANGLE_NAMES, KEYPOINT_NAMES, HumanHand, Reading

ROOT = Path(__file__).resolve().parents[1]
CHAIN = load_chain(ROOT / "assets" / "leap_hand_right.urdf")
CFG = load_manus_leap(ROOT / "config" / "manus_leap.yaml")
CAL = load_manus_calibration(ROOT / "config" / "manus_calibration.example.yaml")
FIST = load_postures(ROOT / "config" / "postures.yaml")[1]
J = ANGLE_NAMES.index


def make(thumb_mode="affine", cfg=CFG, cal=CAL):
    return ManusLeapRetargeter(cfg, cal, FIST, CHAIN, thumb_mode)


def glove(**angles):
    values = np.zeros(len(HUMAN_ANGLE_NAMES))
    for name, value in angles.items():
        values[HUMAN_ANGLE_NAMES.index(name)] = value
    return values


def leap_keypoints(thumb_q, index_q=None):
    """A 'human' hand that is exactly the LEAP hand (scale 1), for IK round trips."""
    q = dict(zip(THUMB_JOINTS, thumb_q))
    q.update(index_q or {})
    links = {
        "wrist": "palm_lower",
        "thumb_cmc": "thumb_temp_base",
        "thumb_ip": "thumb_fingertip",
        "thumb_tip": "thumb_tip_head",
        "index_mcp": "mcp_joint",
        "index_tip": "index_tip_head",
        "middle_mcp": "mcp_joint_2",
        "pinky_mcp": "mcp_joint_3",
    }
    points = np.array([CHAIN.link_position(links[name], q) for name in KEYPOINT_NAMES])
    # The LEAP palm 'along' axis is +z; make wrist -> middle_mcp point along it.
    points[KEYPOINT_NAMES.index("wrist")] = points[KEYPOINT_NAMES.index("middle_mcp")] - [0, 0, 0.1]
    return points


def test_open_glove_gives_open_hand():
    assert make().affine(HumanHand(CAL.open_angles)) == pytest.approx(np.zeros(16))


def test_closed_glove_gives_the_fist_posture():
    assert make().affine(HumanHand(CAL.closed_angles)) == pytest.approx(FIST)


def test_flexion_is_clipped_to_the_open_fist_range():
    over = make().affine(HumanHand(CAL.closed_angles * 1.5))
    assert over == pytest.approx(FIST)


def test_pinky_is_ignored():
    angles = CAL.closed_angles.copy()
    angles[HUMAN_ANGLE_NAMES.index("PinkyMCPStretch")] = 0.0
    assert make().affine(HumanHand(angles)) == pytest.approx(FIST)


def test_barely_moving_joint_borrows_its_finger_median():
    closed = CAL.closed_angles.copy()
    closed[HUMAN_ANGLE_NAMES.index("IndexDIPStretch")] = 0.0  # span 0 -> unusable
    retarget = make(cal=replace(CAL, closed_angles=closed))
    half = HumanHand(closed * 0.5)
    out = retarget.affine(half)
    assert out[J("index_dip_flex")] == pytest.approx(0.5 * FIST[J("index_dip_flex")])


def test_side_spread_is_free_when_open_and_limited_in_a_fist():
    spread = glove(IndexMCPSpread=18.0)
    assert make().affine(HumanHand(spread))[J("index_mcp_side")] == pytest.approx(18.0)
    fist_spread = CAL.closed_angles + spread
    limited = make().affine(HumanHand(fist_spread))[J("index_mcp_side")]
    assert limited == pytest.approx(CFG.side_floor_deg)


def test_ik_mode_without_keypoints_falls_back_to_affine():
    reading = Reading(timestamp=1.0, human=HumanHand(CAL.closed_angles))
    assert make("ik")(reading) == pytest.approx(FIST)


def test_repeated_reading_returns_the_same_command():
    retarget = make()
    reading = Reading(timestamp=1.0, human=HumanHand(CAL.open_angles))
    assert retarget(reading) == pytest.approx(retarget(reading))


def test_thumb_ik_reaches_a_leap_generated_thumb_tip():
    cal = replace(CAL, scale=1.0)
    truth = np.radians([40.0, 50.0, 30.0, 20.0])
    human = HumanHand(CAL.open_angles, leap_keypoints(truth))
    retarget = make("ik", cfg=replace(CFG, prior_weight=0.0, smooth_weight=0.0), cal=cal)
    thumb = retarget.thumb_ik(human, retarget.affine(human))
    tip, _ = retarget.thumb_points(np.radians(thumb))
    assert np.linalg.norm(tip - human.point("thumb_tip")) < 2e-3


def test_strong_prior_keeps_the_affine_thumb():
    human = HumanHand(CAL.closed_angles, leap_keypoints(np.radians([60.0, 10.0, 0.0, 90.0])))
    retarget = make("ik", cfg=replace(CFG, prior_weight=1e6))
    affine = retarget.affine(human)
    assert retarget.thumb_ik(human, affine) == pytest.approx(affine[THUMB], abs=0.5)


def test_ip_point_keeps_the_operator_thumb_posture_while_tracking():
    # The thumb moves smoothly from open to a pose, as a real hand does (IK warm-starts each
    # tick). Tip alone stays on target but the redundant posture drifts; tip + IP follows it.
    truth = np.radians([26.0, 58.0, 56.0, 23.0])
    cal = replace(CAL, scale=1.0)
    worst = {}
    for w_ip in (0.0, 0.3):
        retarget = make("ik", cfg=replace(CFG, ip_weight=w_ip, prior_weight=0.0), cal=cal)
        command = retarget.affine(HumanHand(CAL.open_angles))
        errors = []
        for k in range(1, 61):
            q = truth * min(k / 40, 1.0)
            human = HumanHand(CAL.open_angles, leap_keypoints(q))
            thumb = np.radians(retarget.thumb_ik(human, command))
            errors.append(np.degrees(np.abs(thumb - q)).max())
            tip, _ = retarget.thumb_points(thumb)
        assert np.linalg.norm(tip - human.point("thumb_tip")) < 2e-3
        worst[w_ip] = max(errors)
    assert worst[0.3] < 5.0
    assert worst[0.0] > 20.0


def test_keypoint_dropout_restarts_ik_from_the_affine_thumb():
    retarget = make("ik")
    with_points = HumanHand(CAL.closed_angles, leap_keypoints(np.radians([60.0, 10.0, 0.0, 90.0])))
    retarget(Reading(timestamp=1.0, human=with_points))
    assert retarget._q_prev is not None
    retarget(Reading(timestamp=1.02, human=HumanHand(CAL.closed_angles)))
    assert retarget._q_prev is None


def test_long_input_gap_resets_the_filter():
    retarget = make()
    retarget(Reading(timestamp=1.0, human=HumanHand(CAL.open_angles)))
    after_gap = retarget(Reading(timestamp=5.0, human=HumanHand(CAL.closed_angles)))
    assert after_gap == pytest.approx(FIST)  # no smoothing toward the old open hand


def test_thumb_cmc_side_follows_the_fist_override():
    cfg = replace(CFG, fist_override_deg={"thumb_cmc_side": 40.0})
    out = make(cfg=cfg).affine(HumanHand(CAL.closed_angles))
    assert out[J("thumb_cmc_side")] == pytest.approx(40.0)


def test_thumb_mode_is_validated():
    with pytest.raises(ValueError):
        make("snap")
