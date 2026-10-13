"""A successful action must also settle in measured posture; faults latch."""

from concurrent.futures import Future
from types import SimpleNamespace

import pytest

rclpy = pytest.importorskip("rclpy")
from action_msgs.msg import GoalStatus
from omy_hx5_bringup import unpack
from hx5_teleop.core import Hx5CoreConfig, Hx5GraspCore, TactileFrame
from hx5_teleop.leader import LeaderGripperConfig
from hx5_teleop.ros_bridge import Hx5RosBridge
from rclpy.parameter import Parameter


@pytest.fixture
def coordinator(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(unpack.time, "monotonic", lambda: now[0])
    rclpy.init()
    node = unpack.create_coordinator()
    yield node, now
    node.destroy_node()
    rclpy.shutdown()


def result(status, error_code=0):
    future = Future()
    future.set_result(SimpleNamespace(status=status, result=SimpleNamespace(
        error_code=error_code, error_string="test action failure")))
    return future


def test_action_success_requires_fresh_settled_measurements_and_hold_fault_latches(coordinator):
    node, now = coordinator
    node.phase = "moving"
    node.goal_result(result(GoalStatus.STATUS_SUCCEEDED))
    assert node.phase == "verifying"
    node.joint = ((0.0,) * 6, now[0])
    node.advance()
    assert node.phase == "verifying"
    now[0] += 0.51
    node.joint = ((0.0,) * 6, now[0])
    node.advance()
    assert node.phase == "ready"
    node.joint = ((0.2,) * 6, now[0])
    node.advance()
    assert node.phase == "fault"
    node.joint = ((0.0,) * 6, now[0])
    node.advance()
    assert node.phase == "fault"


def test_aborted_action_cannot_unlock_hand(coordinator):
    node, _ = coordinator
    node.phase = "moving"
    node.goal_result(result(GoalStatus.STATUS_ABORTED, -1))
    assert node.phase == "fault"


def test_stale_joint_states_after_action_success_cannot_unlock_hand(coordinator):
    node, now = coordinator
    node.phase = "moving"
    node.goal_result(result(GoalStatus.STATUS_SUCCEEDED))
    node.joint = ((0.0,) * 6, now[0] - 1.0)
    node.advance()
    assert node.phase == "fault"


def test_arbitrary_start_is_blocked_before_any_goal(coordinator):
    node, now = coordinator
    node.client = SimpleNamespace(server_is_ready=lambda: True)
    node.joint = ((1.0,) * 6, now[0])
    node.advance()
    assert node.phase == "fault"


def test_live_transition_rejects_unready_arm_and_discards_hidden_dry_run_targets(coordinator):
    _, now = coordinator
    core = Hx5GraspCore(Hx5CoreConfig(baseline_frames=2))
    bridge = Hx5RosBridge(core, LeaderGripperConfig("/test_keyboard", "rh_r1_joint", 0, 1),
                         dry_run=True, arm_ready_topic="/test_ready")
    try:
        bridge._on_joint(SimpleNamespace(name=list(core.joint_names), position=[0.0] * 20))
        bridge._leader = (0.0, now[0])
        enabled = Parameter("command_enabled", value=True)
        assert not bridge.node.set_parameters([enabled])[0].successful
        for _ in range(2):
            now[0] += 0.05
            core.step(0.0, TactileFrame(now[0], ((0.0,) * 9,) * 5), now[0])
        for _ in range(10):
            now[0] += 0.05
            core.step(1.0, TactileFrame(now[0], ((0.0,) * 9,) * 5), now[0])
        assert max(abs(x) for x in core.command) > 0.1
        bridge._on_arm_ready(SimpleNamespace(data=True))
        bridge._on_joint(SimpleNamespace(name=list(core.joint_names), position=[0.0] * 20))
        bridge._leader = (0.0, now[0])
        assert bridge.node.set_parameters([enabled])[0].successful
        assert bridge._last_command == (0.0,) * 20
        assert not bridge._core.baseline_ready
        assert not bridge._dry_run
    finally:
        bridge.node.destroy_node()
