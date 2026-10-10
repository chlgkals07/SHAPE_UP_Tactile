"""Exercise the real ROBOTIS ROS message types without any hand hardware."""

import time

import pytest

rclpy = pytest.importorskip("rclpy")
robotis = pytest.importorskip("robotis_interfaces.msg")
sensor_msgs = pytest.importorskip("sensor_msgs.msg")
trajectory_msgs = pytest.importorskip("trajectory_msgs.msg")

from rclpy.executors import SingleThreadedExecutor

from hx5_teleop.core import Hx5CoreConfig, Hx5GraspCore
from hx5_teleop.ros_bridge import Hx5RosBridge, joint_names
from leap_teleop.config import LeaderGripperConfig


def _leader(value):
    msg = trajectory_msgs.JointTrajectory()
    msg.joint_names = ["rh_r1_joint"]
    point = trajectory_msgs.JointTrajectoryPoint()
    point.positions = [value]
    msg.points = [point]
    return msg


def _pressure(stamp, value):
    msg = robotis.HandPressures()
    msg.header.stamp = stamp
    msg.hand_name = "left"
    for finger in range(1, 6):
        sensor = robotis.TactileSensor()
        sensor.sensor_name = f"finger_l_sensor{finger}"
        sensor.pressure_names = [f"Present Pressure {i}" for i in range(1, 10)]
        sensor.pressure_values = [value] * 9
        msg.sensors.append(sensor)
    return msg


def test_left_bridge_receives_official_messages_and_tracks_trigger_without_publishing():
    core = Hx5GraspCore(Hx5CoreConfig(hand_side="left", baseline_frames=8))
    bridge = Hx5RosBridge(
        core,
        LeaderGripperConfig("/leader/joint_trajectory", "rh_r1_joint", 0.0, 1.0),
        side="left",
        dry_run=True,
    )
    fake = rclpy.create_node("hx5_fake_publishers")
    leader_pub = fake.create_publisher(
        trajectory_msgs.JointTrajectory, "/leader/joint_trajectory", 10
    )
    joint_pub = fake.create_publisher(sensor_msgs.JointState, "/joint_states", 10)
    pressure_pub = fake.create_publisher(
        robotis.HandPressures, "/left_hand/finger_pressures", 10
    )
    executor = SingleThreadedExecutor()
    executor.add_node(bridge.node)
    executor.add_node(fake)

    def send(value, pressure, duration):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            leader_pub.publish(_leader(value))
            joints = sensor_msgs.JointState()
            joints.name = list(joint_names("left"))
            joints.position = list(core.command if core.baseline_ready else (0.0,) * 20)
            joint_pub.publish(joints)
            pressure_pub.publish(_pressure(fake.get_clock().now().to_msg(), pressure))
            executor.spin_once(timeout_sec=0.02)

    try:
        send(0.0, 0, 0.8)
        assert core.baseline_ready
        assert bridge._active  # dry-run calculation only; no command publisher
        opened = core.command
        send(0.6, 0, 0.5)
        assert core.command[5] > opened[5]
        assert 0.0 < core.command[5] <= 0.2
        send(0.0, 0, 0.5)
        assert core.command[5] < 0.05
        assert bridge._publisher is None
    finally:
        executor.shutdown()
        fake.destroy_node()
        bridge.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def test_left_bridge_publishes_one_ordered_twenty_joint_trajectory():
    core = Hx5GraspCore(Hx5CoreConfig(hand_side="left", baseline_frames=3))
    bridge = Hx5RosBridge(
        core,
        LeaderGripperConfig("/leader/joint_trajectory", "rh_r1_joint", 0.0, 1.0),
        side="left",
        dry_run=False,
    )
    fake = rclpy.create_node("hx5_trajectory_observer")
    leader_pub = fake.create_publisher(
        trajectory_msgs.JointTrajectory, "/leader/joint_trajectory", 10
    )
    joint_pub = fake.create_publisher(sensor_msgs.JointState, "/joint_states", 10)
    pressure_pub = fake.create_publisher(
        robotis.HandPressures, "/left_hand/finger_pressures", 10
    )
    observed = []
    fake.create_subscription(
        trajectory_msgs.JointTrajectory,
        bridge.topic,
        observed.append,
        10,
    )
    executor = SingleThreadedExecutor()
    executor.add_node(bridge.node)
    executor.add_node(fake)

    def send(value, duration):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            leader_pub.publish(_leader(value))
            joints = sensor_msgs.JointState()
            joints.name = list(joint_names("left"))
            joints.position = list(core.command if core.baseline_ready else (0.0,) * 20)
            joint_pub.publish(joints)
            pressure_pub.publish(_pressure(fake.get_clock().now().to_msg(), 0))
            executor.spin_once(timeout_sec=0.02)

    try:
        send(0.0, 0.5)
        assert core.baseline_ready
        send(0.5, 0.35)
        assert observed
        latest = observed[-1]
        assert tuple(latest.joint_names) == joint_names("left")
        assert latest.header.stamp.sec == 0
        assert latest.header.stamp.nanosec == 0
        assert len(latest.points) == 1
        assert len(latest.points[0].positions) == 20
        assert latest.points[0].time_from_start.nanosec == 50_000_000
        assert latest.points[0].positions[5] > 0.0
    finally:
        executor.shutdown()
        fake.destroy_node()
        bridge.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
