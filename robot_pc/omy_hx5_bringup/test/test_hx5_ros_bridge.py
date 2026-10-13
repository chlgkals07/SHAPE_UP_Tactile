"""Message and startup safety checks without needing a ROS installation."""

import math
import sys
import types
from types import SimpleNamespace as Obj

import pytest

from hx5_teleop.core import Hx5CoreConfig, Hx5GraspCore, TactileFrame
from hx5_teleop.ros_bridge import Hx5RosBridge
from hx5_teleop.ros_bridge import joint_positions, pressure_frame
from hx5_teleop.leader import LeaderGripperConfig


def pressures(*, side="left", names=None, stamp_ns=2_000_000_000, value=8):
    if names is None:
        names = [f"finger_{side[0]}_sensor{i}" for i in range(1, 6)]
    sensors = [
        Obj(sensor_name=name, pressure_names=[f"p{i}" for i in range(9)],
            pressure_values=[value] * 9)
        for name in names
    ]
    return Obj(
        hand_name=side,
        header=Obj(stamp=Obj(sec=stamp_ns // 1_000_000_000,
                             nanosec=stamp_ns % 1_000_000_000)),
        sensors=sensors,
    )


def test_pressure_frame_uses_names_not_array_order():
    msg = pressures()
    msg.sensors.reverse()
    msg.sensors[0].pressure_values[0] = 31  # little finger after reversing
    frame = pressure_frame(msg, side="left", received_at=1.0,
                           ros_now_ns=2_050_000_000)
    assert frame is not None
    assert frame.values[4][0] == 31
    assert frame.values[0][0] == 8


def test_pressure_frame_preserves_sample_age_and_clamps_small_future_skew():
    msg = pressures(stamp_ns=2_000_000_000)
    aged = pressure_frame(msg, side="left", received_at=10.0,
                          ros_now_ns=2_200_000_000)
    assert aged is not None
    assert aged.timestamp == pytest.approx(9.8)

    future = pressure_frame(msg, side="left", received_at=10.0,
                            ros_now_ns=1_950_000_000)
    assert future is not None
    assert future.timestamp == pytest.approx(10.0)


def test_pressure_frame_rejects_wrong_hand_old_stamp_and_bad_arrays():
    msg = pressures()
    assert pressure_frame(msg, side="right", received_at=1.0,
                          ros_now_ns=2_000_000_000) is None
    assert pressure_frame(msg, side="left", received_at=1.0,
                          ros_now_ns=3_000_000_000) is None
    msg.sensors[0].pressure_values = [8] * 8
    assert pressure_frame(msg, side="left", received_at=1.0,
                          ros_now_ns=2_000_000_000) is None
    msg.sensors[0].pressure_values = [256] * 9
    assert pressure_frame(msg, side="left", received_at=1.0,
                          ros_now_ns=2_000_000_000) is None
    msg.sensors[0].pressure_values = [1.5] * 9
    assert pressure_frame(msg, side="left", received_at=1.0,
                          ros_now_ns=2_000_000_000) is None


def test_joint_positions_are_reordered_and_complete():
    names = [f"finger_l_joint{i}" for i in range(20, 0, -1)]
    msg = Obj(name=names + ["omy_joint"], position=list(range(20, 0, -1)) + [99.0])
    assert joint_positions(msg, "left") == tuple(float(i) for i in range(1, 21))
    msg.name.remove("finger_l_joint12")
    msg.position.pop(8)
    assert joint_positions(msg, "left") is None


def test_bridge_rejects_core_with_opposite_hand_side_before_loading_ros():
    core = Hx5GraspCore(Hx5CoreConfig(hand_side="left"))
    leader = LeaderGripperConfig("/leader/joint_trajectory", "rh_r1_joint", 0.0, 1.0)
    with pytest.raises(ValueError, match="hand_side"):
        Hx5RosBridge(core, leader, side="right")


def test_first_published_command_is_bounded_from_measured_pose(monkeypatch):
    """Baseline collection must not accumulate an unissued opening command."""
    clock = [0.0]
    monkeypatch.setattr("hx5_teleop.ros_bridge.time.monotonic", lambda: clock[0])
    ros_msgs = types.ModuleType("trajectory_msgs.msg")

    class Point:
        def __init__(self):
            self.positions = []
            self.time_from_start = Obj(nanosec=0)

    class Trajectory:
        def __init__(self):
            self.header = Obj(stamp=None)
            self.joint_names = []
            self.points = []

    ros_msgs.JointTrajectoryPoint = Point
    monkeypatch.setitem(sys.modules, "trajectory_msgs", types.ModuleType("trajectory_msgs"))
    monkeypatch.setitem(sys.modules, "trajectory_msgs.msg", ros_msgs)

    measured = [0.0] * 20
    measured[6] = 0.09  # Within baseline tolerance but > one 20 Hz speed step.
    measured = tuple(measured)
    core = Hx5GraspCore(Hx5CoreConfig(baseline_frames=2))
    core.initialize(measured, 0.0)
    published = []
    bridge = Hx5RosBridge.__new__(Hx5RosBridge)
    bridge._core = core
    bridge.names = core.joint_names
    bridge.topic = "/hx5-test-command"
    bridge._JointTrajectory = Trajectory
    bridge._publisher = Obj(publish=published.append)
    bridge._dry_run = False
    bridge._leader = (0.0, 0.0)
    bridge._leader_timeout = 0.5
    bridge._joint_timeout = 0.5
    bridge._tracking_error_limit = 0.5
    bridge._startup_delta_limit = 0.025
    bridge._startup_motion_fault = False
    bridge._used_tactile_time = -math.inf
    bridge._last_command = measured
    bridge._active = False
    bridge._mode = "waiting"
    bridge._last_log = 0.0
    bridge.node = Obj(
        count_publishers=lambda _topic: 1,
        get_clock=lambda: Obj(now=lambda: Obj(to_msg=lambda: Obj())),
        get_logger=lambda: Obj(info=lambda _message: None),
    )

    zero_pressure = ((0.0,) * 9,) * 5
    for index in (1, 2):
        clock[0] = index * 0.05
        bridge._joint = (measured, clock[0])
        bridge._tactile = TactileFrame(clock[0], zero_pressure)
        bridge._tick()
        assert core.command == measured
    assert core.baseline_ready
    assert bridge._active
    assert len(published) == 1
    assert tuple(published[0].points[0].positions) == measured

    clock[0] = 0.15
    bridge._leader = (1.0, clock[0])
    bridge._joint = (measured, clock[0])
    bridge._tactile = TactileFrame(clock[0], zero_pressure)
    bridge._tick()
    assert len(published) == 2
    assert published[1].points[0].positions[6] - measured[6] <= 0.025 + 1e-12
