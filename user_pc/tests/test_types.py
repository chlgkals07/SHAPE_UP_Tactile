import numpy as np
import pytest

from leap_teleop.hand.joints import ANGLE_NAMES
from leap_teleop.types import HAND_DOF, HUMAN_ANGLE_NAMES, KEYPOINT_NAMES, HumanHand, Reading


def test_hand_dof_matches_joint_names():
    assert HAND_DOF == 16
    assert len(ANGLE_NAMES) == HAND_DOF


def test_reading_accepts_grasp():
    reading = Reading(timestamp=1.0, grasp=0.5)
    assert reading.grasp == 0.5
    assert reading.hand is None


def test_reading_accepts_hand_and_copies_it():
    source = np.zeros(16)
    reading = Reading(timestamp=1.0, hand=source)
    source[0] = 99.0
    assert reading.hand[0] == 0.0
    assert reading.grasp is None


def test_reading_requires_exactly_one_input():
    human = HumanHand(np.zeros(20))
    with pytest.raises(ValueError):
        Reading(timestamp=1.0)
    with pytest.raises(ValueError):
        Reading(timestamp=1.0, grasp=0.5, hand=np.zeros(16))
    with pytest.raises(ValueError):
        Reading(timestamp=1.0, grasp=0.5, human=human)


@pytest.mark.parametrize("grasp", [-0.01, 1.01, float("nan")])
def test_reading_rejects_grasp_outside_unit_interval(grasp):
    with pytest.raises(ValueError):
        Reading(timestamp=1.0, grasp=grasp)


def test_reading_rejects_wrong_hand_shape_and_nan():
    with pytest.raises(ValueError):
        Reading(timestamp=1.0, hand=np.zeros(15))
    bad = np.zeros(16)
    bad[3] = float("nan")
    with pytest.raises(ValueError):
        Reading(timestamp=1.0, hand=bad)


def test_human_names_cover_twenty_angles_and_the_thumb_ik_points():
    assert len(HUMAN_ANGLE_NAMES) == 20
    assert HUMAN_ANGLE_NAMES[0] == "ThumbMCPSpread"
    assert {"wrist", "thumb_tip", "index_tip"} <= set(KEYPOINT_NAMES)


def test_reading_accepts_human_hand():
    human = HumanHand(np.arange(20.0), np.ones((7, 3)))
    reading = Reading(timestamp=1.0, human=human)
    assert reading.human.angle("IndexMCPStretch") == 5.0
    assert reading.human.point("thumb_tip").tolist() == [1.0, 1.0, 1.0]


def test_human_hand_without_keypoints_refuses_point_lookup():
    with pytest.raises(ValueError):
        HumanHand(np.zeros(20)).point("wrist")


def test_human_hand_rejects_bad_shapes_and_nan():
    with pytest.raises(ValueError):
        HumanHand(np.zeros(19))
    with pytest.raises(ValueError):
        HumanHand(np.zeros(20), np.zeros((6, 3)))
    bad = np.zeros(20)
    bad[4] = float("nan")
    with pytest.raises(ValueError):
        HumanHand(bad)
