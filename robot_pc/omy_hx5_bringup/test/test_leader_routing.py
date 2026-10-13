"""The seventh leader joint must never enter the six-joint arm controller."""

import pytest

from hx5_teleop.leader import LeaderGripperConfig, grasp_from_trajectory
from omy_hx5_bringup.arm_bridge import ARM_JOINTS, arm_positions


def test_reordered_leader_routes_arm_and_trigger_independently():
    names = ["rh_r1_joint", "joint6", "joint5", "joint4", "joint3", "joint2", "joint1"]
    values = [0.5, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    cfg = LeaderGripperConfig("/leader/joint_trajectory", "rh_r1_joint", 0.2, 0.8)
    assert ARM_JOINTS == ("joint1", "joint2", "joint3", "joint4", "joint5", "joint6")
    assert arm_positions(names, values) == (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    assert grasp_from_trajectory(names, [values], cfg) == pytest.approx(0.5)


def test_missing_or_malformed_leader_command_is_dropped():
    cfg = LeaderGripperConfig("/leader/joint_trajectory", "rh_r1_joint", 0.2, 0.8)
    assert arm_positions(["joint1", "rh_r1_joint"], [0.0, 0.5]) is None
    assert arm_positions(list(ARM_JOINTS), [0.0] * 5 + [float("nan")]) is None
    assert grasp_from_trajectory(["rh_r1_joint", "rh_r1_joint"], [[0.5, 0.5]], cfg) is None
    assert grasp_from_trajectory(["rh_r1_joint"], [[float("nan")]], cfg) is None
