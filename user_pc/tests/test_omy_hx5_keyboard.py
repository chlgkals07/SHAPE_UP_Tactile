"""Check the remote keyboard's scalar hand-only command mapping."""

import pytest

from user_pc.omy_hx5_keyboard import DEFAULT_TOPIC, JOINT_NAME, KeyboardGrasp


def test_keyboard_uses_a_dedicated_hand_topic_and_one_grasp_joint():
    assert DEFAULT_TOPIC == "/hx5/keyboard_grasp_trajectory"
    assert JOINT_NAME == "rh_r1_joint"
    assert "joint1" not in JOINT_NAME


def test_official_open_close_keys_and_bounded_incremental_keys():
    grasp = KeyboardGrasp(step=0.2)
    assert grasp.value == 0.0
    assert grasp.update("x") and grasp.value == 1.0
    assert grasp.update("[") and grasp.value == pytest.approx(0.8)
    assert grasp.update("z") and grasp.value == 0.0
    for _ in range(8):
        grasp.update("]")
    assert grasp.value == 1.0
    assert not grasp.update("not-a-key")
    for _ in range(8):
        grasp.update("[")
    assert grasp.value == 0.0


def test_invalid_keyboard_start_values_are_rejected():
    with pytest.raises(ValueError):
        KeyboardGrasp(value=1.1)
    with pytest.raises(ValueError):
        KeyboardGrasp(step=0.0)
