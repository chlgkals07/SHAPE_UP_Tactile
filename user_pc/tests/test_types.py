import numpy as np
import pytest

from leap_teleop.hand.joints import ANGLE_NAMES
from leap_teleop.types import HAND_DOF, Reading


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


def test_reading_requires_exactly_one_of_grasp_or_hand():
    with pytest.raises(ValueError):
        Reading(timestamp=1.0)
    with pytest.raises(ValueError):
        Reading(timestamp=1.0, grasp=0.5, hand=np.zeros(16))


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
