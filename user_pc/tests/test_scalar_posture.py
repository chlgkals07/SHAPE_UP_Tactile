import numpy as np
import pytest

from leap_teleop.config import make_posture
from leap_teleop.retarget.scalar_posture import ScalarPostureRetargeter
from leap_teleop.types import Reading


def make_retargeter():
    open_pose = np.zeros(16)
    fist_pose = make_posture({"index_mcp_flex": 60.0, "thumb_ip_flex": 30.0})
    return ScalarPostureRetargeter(open_pose, fist_pose), open_pose, fist_pose


def test_grasp_zero_is_open_and_one_is_fist():
    retargeter, open_pose, fist_pose = make_retargeter()
    np.testing.assert_array_equal(retargeter(Reading(0.0, grasp=0.0)), open_pose)
    np.testing.assert_array_equal(retargeter(Reading(0.0, grasp=1.0)), fist_pose)


def test_grasp_half_is_halfway():
    retargeter, _, fist_pose = make_retargeter()
    np.testing.assert_allclose(retargeter(Reading(0.0, grasp=0.5)), fist_pose / 2.0)


def test_returned_array_is_a_copy():
    retargeter, open_pose, _ = make_retargeter()
    out = retargeter(Reading(0.0, grasp=0.0))
    out[0] = 99.0
    np.testing.assert_array_equal(retargeter(Reading(0.0, grasp=0.0)), open_pose)


def test_hand_reading_is_rejected():
    retargeter, _, _ = make_retargeter()
    with pytest.raises(ValueError, match="grasp"):
        retargeter(Reading(0.0, hand=np.zeros(16)))


def test_constructor_rejects_wrong_shapes():
    with pytest.raises(ValueError):
        ScalarPostureRetargeter(np.zeros(15), np.zeros(16))
    with pytest.raises(ValueError):
        ScalarPostureRetargeter(np.zeros(16), np.zeros(17))
