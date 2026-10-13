"""Route only the six OMY arm joints from the seven-joint leader topic."""

from __future__ import annotations

import math

ARM_JOINTS = tuple(f"joint{i}" for i in range(1, 7))


def arm_positions(joint_names: list[str], positions: list[float]) -> tuple[float, ...] | None:
    if len(joint_names) != len(positions) or len(set(joint_names)) != len(joint_names):
        return None
    index = {name: i for i, name in enumerate(joint_names)}
    if not set(ARM_JOINTS).issubset(index):
        return None
    try:
        result = tuple(float(positions[index[name]]) for name in ARM_JOINTS)
    except (TypeError, ValueError):
        return None
    return result if all(math.isfinite(value) for value in result) else None


def main() -> None:
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

    rclpy.init()
    node = rclpy.create_node("omy_hx5_arm_bridge")
    publisher = node.create_publisher(JointTrajectory, "/arm_controller/joint_trajectory", 10)

    def on_leader(message: JointTrajectory) -> None:
        if len(message.points) != 1:
            return
        values = arm_positions(message.joint_names, message.points[0].positions)
        if values is None:
            return
        command = JointTrajectory()
        command.joint_names = list(ARM_JOINTS)
        point = JointTrajectoryPoint()
        point.positions = list(values)
        point.time_from_start = message.points[0].time_from_start
        command.points = [point]
        # A zero header stamp keeps the official broadcaster's immediate semantics.
        publisher.publish(command)

    node.create_subscription(
        JointTrajectory, "/leader/joint_trajectory", on_leader, qos_profile_sensor_data
    )
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
