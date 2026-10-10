"""Check the HX5 left bridge against ROBOTIS Gazebo with synthetic pressure.

Run through run_hx5_gazebo_probe.sh. This never opens a serial device and does
not measure tactile contact or physical force.
"""

from __future__ import annotations

import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from robotis_interfaces.msg import HandPressures, TactileSensor
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from hx5_teleop.core import Hx5CoreConfig, Hx5GraspCore
from hx5_teleop.ros_bridge import Hx5RosBridge
from leap_teleop.config import LeaderGripperConfig


def main() -> None:
    rclpy.init()
    core = Hx5GraspCore(Hx5CoreConfig(hand_side="left", baseline_frames=8))
    bridge = Hx5RosBridge(
        core,
        LeaderGripperConfig("/leader/joint_trajectory", "rh_r1_joint", 0.0, 1.0),
        side="left",
    )
    fake = rclpy.create_node("hx5_official_gazebo_bridge_probe")
    leader_pub = fake.create_publisher(JointTrajectory, "/leader/joint_trajectory", 10)
    pressure_pub = fake.create_publisher(HandPressures, "/left_hand/finger_pressures", 10)
    states: list[float] = []
    commands: list[JointTrajectory] = []

    def on_joint(message: JointState) -> None:
        if "finger_l_joint6" in message.name:
            states.append(message.position[message.name.index("finger_l_joint6")])

    fake.create_subscription(JointState, "/joint_states", on_joint, 10)
    fake.create_subscription(JointTrajectory, bridge.topic, commands.append, 10)
    executor = SingleThreadedExecutor()
    executor.add_node(fake)
    executor.add_node(bridge.node)

    def send(grasp: float, duration: float) -> float:
        end = time.monotonic() + duration
        while time.monotonic() < end:
            leader = JointTrajectory()
            leader.joint_names = ["rh_r1_joint"]
            point = JointTrajectoryPoint()
            point.positions = [grasp]
            leader.points = [point]
            leader_pub.publish(leader)

            pressure = HandPressures()
            pressure.header.stamp = fake.get_clock().now().to_msg()
            pressure.hand_name = "left"
            for finger in range(1, 6):
                sensor = TactileSensor()
                sensor.sensor_name = f"finger_l_sensor{finger}"
                sensor.pressure_names = [f"Present Pressure {cell}" for cell in range(1, 10)]
                sensor.pressure_values = [0] * 9
                pressure.sensors.append(sensor)
            pressure_pub.publish(pressure)
            executor.spin_once(timeout_sec=0.02)

        assert states, "Gazebo did not publish left-hand joint states"
        measured = states[-1]
        print(
            f"trigger={grasp:.1f} j6_measured={measured:.6f} "
            f"j6_command={core.command[5]:.6f} commands={len(commands)}",
            flush=True,
        )
        return measured

    try:
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.1)
            if states and bridge.node.count_subscribers(bridge.topic) >= 2:
                break
        else:
            raise RuntimeError("Gazebo joint states or trajectory subscriber unavailable")

        opened = send(0.0, 1.5)
        half = send(0.5, 1.5)
        closed = send(1.0, 1.5)
        released = send(0.0, 1.5)
        assert core.baseline_ready and bridge._active
        assert commands and all(len(command.joint_names) == 20 for command in commands)
        assert all(len(command.points[0].positions) == 20 for command in commands)
        assert all(command.header.stamp.sec == command.header.stamp.nanosec == 0 for command in commands)
        assert abs(opened) < 0.03, opened
        assert 0.06 < half < 0.14, half
        assert 0.15 < closed < 0.23, closed
        assert abs(released) < 0.04, released
        print("PASS: official Gazebo tracked the HX5 bridge trigger cycle", flush=True)
    finally:
        executor.shutdown()
        fake.destroy_node()
        bridge.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
