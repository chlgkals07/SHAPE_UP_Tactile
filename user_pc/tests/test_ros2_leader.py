import pytest

from leap_teleop.config import LeaderGripperConfig
from leap_teleop.sources.ros2_leader import grasp_from_trajectory

CFG = LeaderGripperConfig("/leader/joint_trajectory", "rh_r1_joint", 0.0, 1.0)
NAMES = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "rh_r1_joint"]


def test_reads_the_gripper_joint_by_name():
    positions = [[9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 0.25]]
    assert grasp_from_trajectory(NAMES, positions, CFG) == pytest.approx(0.25)


def test_does_not_depend_on_joint_order():
    names = ["rh_r1_joint", "joint1"]
    assert grasp_from_trajectory(names, [[0.75, 9.0]], CFG) == pytest.approx(0.75)


def test_values_outside_the_measured_range_are_clipped():
    assert grasp_from_trajectory(["rh_r1_joint"], [[1.4]], CFG) == 1.0
    assert grasp_from_trajectory(["rh_r1_joint"], [[-0.3]], CFG) == 0.0


def test_inverted_open_and_closed_values_still_work():
    inverted = LeaderGripperConfig("/t", "rh_r1_joint", 1.0, 0.0)
    assert grasp_from_trajectory(["rh_r1_joint"], [[0.25]], inverted) == pytest.approx(0.75)


def test_offset_range_is_normalised():
    cfg = LeaderGripperConfig("/t", "rh_r1_joint", 0.2, 1.2)
    assert grasp_from_trajectory(["rh_r1_joint"], [[0.7]], cfg) == pytest.approx(0.5)


def test_missing_joint_returns_none():
    assert grasp_from_trajectory(["joint1"], [[0.5]], CFG) is None


def test_empty_points_returns_none():
    assert grasp_from_trajectory(NAMES, [], CFG) is None


def test_too_short_positions_returns_none():
    assert grasp_from_trajectory(NAMES, [[0.1, 0.2]], CFG) is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_value_returns_none(bad):
    assert grasp_from_trajectory(["rh_r1_joint"], [[bad]], CFG) is None
