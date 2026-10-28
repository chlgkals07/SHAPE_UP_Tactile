from pathlib import Path

import numpy as np
import pytest

from leap_teleop.hand.leap_v1 import SIM_MAX_RADIANS, SIM_MIN_RADIANS
from leap_teleop.kinematics import least_squares, load_chain

URDF = Path(__file__).resolve().parents[1] / "assets" / "leap_hand_right.urdf"
THUMB = ("12", "13", "14", "15")


@pytest.fixture(scope="module")
def chain():
    return load_chain(URDF)


def test_open_hand_tip_positions_match_the_urdf(chain):
    # Reference values computed independently from the same URDF.
    mm = lambda link: chain.link_position(link, {}) * 1000.0  # noqa: E731
    assert mm("index_tip_head") == pytest.approx([19.5, 45.6, 228.2], abs=0.2)
    assert mm("thumb_tip_head") == pytest.approx([21.9, 174.7, 15.7], abs=0.2)
    assert mm("thumb_temp_base") == pytest.approx([21.6, 36.8, 28.7], abs=0.2)


def test_urdf_limits_match_the_driver_limits(chain):
    lower, upper = chain.limits([str(i) for i in range(16)])
    assert lower == pytest.approx(SIM_MIN_RADIANS, abs=1e-3)
    assert upper == pytest.approx(SIM_MAX_RADIANS, abs=1e-3)


def test_ik_recovers_a_reachable_thumb_tip(chain):
    truth = {"12": 0.9, "13": 0.4, "14": 0.6, "15": 0.5}
    target = chain.link_position("thumb_tip_head", truth)
    lower, upper = chain.limits(THUMB)

    def residual(x):
        return chain.link_position("thumb_tip_head", dict(zip(THUMB, x))) - target

    solved = least_squares(residual, np.zeros(4), lower, upper)
    assert np.linalg.norm(residual(solved)) < 1e-3


def test_ik_stays_inside_the_joint_limits_for_an_unreachable_target(chain):
    lower, upper = chain.limits(THUMB)

    def residual(x):
        tip = chain.link_position("thumb_tip_head", dict(zip(THUMB, x)))
        return tip - np.array([0.0, 0.0, 1.0])

    solved = least_squares(residual, np.zeros(4), lower, upper)
    assert np.all(solved >= lower) and np.all(solved <= upper)
