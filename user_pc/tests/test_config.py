from pathlib import Path

import numpy as np
import pytest

from leap_teleop.config import (
    LeaderGripperConfig,
    load_leader_gripper,
    load_postures,
    make_posture,
)
from leap_teleop.hand.joints import ANGLE_NAMES

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def test_make_posture_places_values_by_joint_name():
    posture = make_posture({"index_mcp_flex": 55.0})
    assert posture.shape == (16,)
    assert posture[ANGLE_NAMES.index("index_mcp_flex")] == 55.0
    assert np.count_nonzero(posture) == 1


def test_make_posture_rejects_unknown_joint():
    with pytest.raises(ValueError, match="bogus"):
        make_posture({"bogus": 1.0})


def test_load_postures_reads_open_and_fist(tmp_path):
    path = tmp_path / "postures.yaml"
    path.write_text("open: {}\nfist:\n  index_mcp_flex: 10\n")
    open_pose, fist_pose = load_postures(path)
    assert not open_pose.any()
    assert fist_pose[ANGLE_NAMES.index("index_mcp_flex")] == 10.0


def test_load_postures_requires_both_keys(tmp_path):
    path = tmp_path / "postures.yaml"
    path.write_text("open: {}\n")
    with pytest.raises(ValueError, match="fist"):
        load_postures(path)


def test_default_postures_are_the_full_fist_values():
    open_pose, fist_pose = load_postures(CONFIG_DIR / "postures.yaml")
    assert not open_pose.any()
    expected = {
        "index_mcp_flex": 90.0, "index_pip_flex": 100.0, "index_dip_flex": 80.0,
        "middle_mcp_flex": 90.0, "middle_pip_flex": 100.0, "middle_dip_flex": 80.0,
        "ring_mcp_flex": 90.0, "ring_pip_flex": 100.0, "ring_dip_flex": 80.0,
        "thumb_cmc_flex": 60.0, "thumb_mcp_flex": 75.0, "thumb_ip_flex": 70.0,
    }
    np.testing.assert_array_equal(fist_pose, make_posture(expected))
    for side in ("index_mcp_side", "middle_mcp_side", "ring_mcp_side", "thumb_cmc_side"):
        assert fist_pose[ANGLE_NAMES.index(side)] == 0.0


def test_load_leader_gripper(tmp_path):
    path = tmp_path / "leader.yaml"
    path.write_text(
        "topic: /t\njoint_name: rh_r1_joint\nopen_value: 0.2\nclosed_value: 1.1\n"
    )
    assert load_leader_gripper(path) == LeaderGripperConfig("/t", "rh_r1_joint", 0.2, 1.1)


def test_leader_gripper_rejects_equal_open_and_closed(tmp_path):
    path = tmp_path / "leader.yaml"
    path.write_text("topic: /t\njoint_name: j\nopen_value: 1.0\nclosed_value: 1.0\n")
    with pytest.raises(ValueError, match="differ"):
        load_leader_gripper(path)


def test_default_leader_gripper_file_loads():
    cfg = load_leader_gripper(CONFIG_DIR / "leader_gripper.yaml")
    assert cfg.topic == "/leader/joint_trajectory"
    assert cfg.joint_name == "rh_r1_joint"
