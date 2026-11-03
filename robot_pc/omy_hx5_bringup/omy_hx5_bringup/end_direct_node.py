"""ROS 2 bridge: ROBOTIS left-hand keyboard topics over OMY END ID 210.

This is a ROS interface compatible with the official keyboard and initial
position action, not a ros2_control hand controller. The arm's real
ros2_control hardware remains in its own controller_manager.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from threading import Lock

from .direct_trajectory import (
    JOINT_NAMES, Segment, make_jog_segment, make_trajectory_segment,
    validate_currents,
)
from .end_direct_core import EndDirect, load_vendor_motor_settings
from .end_proxy import EndProxyError, acquire_end_bus_lock, make_fresh_rx_port


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyAMA4")
    parser.add_argument("--baud", type=int, default=4_000_000)
    parser.add_argument("--allow-active-status32", choices=("true", "false"),
                        default="false")
    parser.add_argument("--read-only", choices=("true", "false"), default="false")
    args, ros_args = parser.parse_known_args(argv)
    if ros_args and ros_args[0] != "--ros-args":
        parser.error(f"unrecognized arguments: {' '.join(ros_args)}")
    try:
        import rclpy
        from ament_index_python.packages import get_package_share_directory
        from control_msgs.action import FollowJointTrajectory
        from dynamixel_sdk import PacketHandler
        from rclpy.action import ActionServer, CancelResponse, GoalResponse
        from rclpy.callback_groups import ReentrantCallbackGroup
        from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
        from rclpy.node import Node
        from robotis_interfaces.msg import HandPressures, TactileSensor
        from sensor_msgs.msg import JointState
        from std_msgs.msg import Float64MultiArray
        from trajectory_msgs.msg import JointTrajectory
    except ModuleNotFoundError as exc:
        parser.exit(1, f"Missing Robot PC ROS dependency: {exc.name}\n")

    class DirectNode(Node):
        def __init__(self, direct: EndDirect, first, *, read_only: bool):
            super().__init__("omy_hx5_end_direct")
            self.direct = direct
            self.read_only = read_only
            self.lock = Lock()
            self.positions = first.positions
            self.segment: Segment | None = None
            self.currents = (100,) * 20
            self.last_tick = first.tick
            self.tick_changed = time.monotonic()
            self.active_action = False
            self.fault = None
            self.joints_pub = self.create_publisher(JointState, "/joint_states", 10)
            self.pressure_pub = self.create_publisher(
                HandPressures, "/left_hand/finger_pressures", 10)
            self.command_topic = (
                "/leader/joint_trajectory_command_broadcaster_left_hand/joint_trajectory")
            group = ReentrantCallbackGroup()
            self.create_subscription(
                JointTrajectory,
                self.command_topic,
                self.on_keyboard, 10, callback_group=group)
            self.create_subscription(Float64MultiArray,
                                     "/effort_l_controller/commands",
                                     self.on_current, 10, callback_group=group)
            self.create_subscription(Float64MultiArray, "/omy_hx5/jog",
                                     self.on_jog, 10, callback_group=group)
            self.action = ActionServer(
                self, FollowJointTrajectory, "/hand_l_controller/follow_joint_trajectory",
                execute_callback=self.execute_goal, goal_callback=self.accept_goal,
                cancel_callback=self.cancel_goal, callback_group=group)
            self.create_timer(0.05, self.poll, callback_group=group)

        @staticmethod
        def segment_from_message(msg, measured):
            return make_trajectory_segment(msg.joint_names, msg.points,
                                           measured, time.monotonic())

        def on_keyboard(self, msg):
            if self.read_only:
                self.get_logger().warn("Read-only Direct bridge ignored hand trajectory")
                return
            if self.count_publishers(self.command_topic) > 1:
                with self.lock:
                    self.segment = None
                self.get_logger().error("Multiple hand command publishers; trajectory ignored")
                return
            with self.lock:
                if self.active_action:
                    self.get_logger().warn("Action is active; keyboard command ignored")
                    return
                try:
                    self.segment = self.segment_from_message(msg, self.positions)
                except ValueError as exc:
                    self.get_logger().error(f"Rejected hand trajectory: {exc}")

        def on_current(self, msg):
            if self.read_only:
                return
            try:
                currents = validate_currents(msg.data)
            except ValueError as exc:
                self.get_logger().error(f"Rejected hand current: {exc}")
                return
            with self.lock:
                self.currents = currents

        def on_jog(self, msg):
            if self.read_only:
                self.get_logger().warn("Read-only Direct bridge ignored jog")
                return
            if len(msg.data) != 2:
                self.get_logger().error("Jog requires [joint_number, delta_rad]")
                return
            if self.count_publishers(self.command_topic):
                self.get_logger().error("Jog rejected while a hand trajectory publisher is present")
                return
            with self.lock:
                now = time.monotonic()
                if self.active_action or (self.segment is not None and
                                          not self.segment.done(now)):
                    self.get_logger().error("Jog rejected while another hand command is active")
                    return
                try:
                    self.segment = make_jog_segment(
                        msg.data[0], msg.data[1], self.positions, now)
                except ValueError as exc:
                    self.get_logger().error(f"Rejected hand jog: {exc}")
                    return
            self.get_logger().info(
                f"Accepted hand jog: joint {int(msg.data[0])}, {msg.data[1]:+.3f} rad")

        def accept_goal(self, request):
            if self.read_only:
                return GoalResponse.REJECT
            with self.lock:
                if self.active_action:
                    return GoalResponse.REJECT
                try:
                    self.segment_from_message(request.trajectory, self.positions)
                except ValueError as exc:
                    self.get_logger().error(f"Rejected hand action: {exc}")
                    return GoalResponse.REJECT
                self.active_action = True
            return GoalResponse.ACCEPT

        def cancel_goal(self, goal_handle):
            return CancelResponse.ACCEPT

        def execute_goal(self, goal_handle):
            result = FollowJointTrajectory.Result()
            try:
                with self.lock:
                    self.segment = self.segment_from_message(
                        goal_handle.request.trajectory, self.positions)
                    owned = self.segment
                deadline = owned.start_time + owned.duration + 3.0
                while rclpy.ok():
                    with self.lock:
                        fault = self.fault
                        measured = self.positions
                    if fault or goal_handle.is_cancel_requested:
                        with self.lock:
                            self.segment = None
                        goal_handle.canceled() if goal_handle.is_cancel_requested else goal_handle.abort()
                        result.error_code = FollowJointTrajectory.Result.INVALID_GOAL
                        result.error_string = str(fault or "canceled")
                        return result
                    if (owned.done(time.monotonic()) and
                            max(abs(a - b) for a, b in zip(measured, owned.goal)) < 0.2):
                        goal_handle.succeed()
                        result.error_code = FollowJointTrajectory.Result.SUCCESSFUL
                        return result
                    if time.monotonic() > deadline:
                        goal_handle.abort()
                        result.error_code = FollowJointTrajectory.Result.GOAL_TOLERANCE_VIOLATED
                        result.error_string = "hand did not reach requested pose in time"
                        return result
                    time.sleep(0.05)
                goal_handle.abort()
                result.error_code = FollowJointTrajectory.Result.INVALID_GOAL
                return result
            finally:
                with self.lock:
                    self.active_action = False

        def poll(self):
            # All serial operations happen only in this timer callback.
            try:
                snapshot = self.direct.read_snapshot()
                now = time.monotonic()
                with self.lock:
                    if snapshot.tick != self.last_tick:
                        self.tick_changed = now
                        self.last_tick = snapshot.tick
                    if now - self.tick_changed > 0.5:
                        raise EndProxyError("HX5 controller tick stopped updating")
                    self.positions = snapshot.positions
                    segment = self.segment
                    currents = self.currents
                stamp = self.get_clock().now().to_msg()
                joint_state = JointState()
                joint_state.header.stamp = stamp
                joint_state.name = list(JOINT_NAMES)
                joint_state.position = list(snapshot.positions)
                self.joints_pub.publish(joint_state)
                tactile = HandPressures()
                tactile.header.stamp = stamp
                tactile.header.frame_id = "hx5_d20_left_base"
                tactile.hand_name = "left"
                for i, values in enumerate(snapshot.pressures, start=1):
                    sensor = TactileSensor()
                    sensor.sensor_name = f"finger_l_sensor{i}"
                    sensor.pressure_names = [f"Present Pressure {j}" for j in range(1, 10)]
                    sensor.pressure_values = list(values)
                    tactile.sensors.append(sensor)
                self.pressure_pub.publish(tactile)
                if segment is not None and not self.read_only:
                    self.direct.write_goals(segment.sample(now), currents)
            except (EndProxyError, OSError, ValueError) as exc:
                with self.lock:
                    self.fault = exc
                    self.segment = None
                self.get_logger().error(f"END direct control stopped: {exc}")
                rclpy.shutdown()

    xacro = (Path(get_package_share_directory("robotis_hand_description")) /
             "ros2_control/hx5_d20_rev2/hx5_d20_left.ros2_control.xacro")
    expected = load_vendor_motor_settings(xacro)
    try:
        lock_fd = acquire_end_bus_lock()
    except EndProxyError as exc:
        parser.exit(1, f"END direct bringup failed: {exc}\n")
    port = make_fresh_rx_port(args.port)
    if not port.openPort():
        parser.exit(1, f"Cannot open {args.port}; stop other END owners first\n")
    node = None
    executor = None
    try:
        if not port.setBaudRate(args.baud):
            raise EndProxyError(f"cannot set {args.port} to {args.baud} baud")
        direct = EndDirect(
            port, PacketHandler(2.0),
            allow_active_status32=args.allow_active_status32 == "true",
            read_only=args.read_only == "true")
        issues = direct.audit_motors(expected)
        if issues:
            raise EndProxyError("HX5 motor setup does not match official Xacro:\n" +
                                "\n".join(issues))
        direct.verify_direct_setup()
        with direct.direct_session() as first:
            rclpy.init(args=ros_args)
            node = DirectNode(direct, first, read_only=args.read_only == "true")
            executor = MultiThreadedExecutor(num_threads=3)
            executor.add_node(node)
            interface_note = (
                "Hand goals rejected; joint and tactile topics active."
                if node.read_only else
                "ROBOTIS left-hand keyboard trajectory and tactile topics are active.")
            node.get_logger().info(
                "END 210 -> HX5 140 Direct Mode ready. No motion command sent. "
                f"read_only={node.read_only}, active_status={first.status}. "
                + interface_note)
            try:
                executor.spin()
            except (KeyboardInterrupt, ExternalShutdownException):
                pass
            if node.fault:
                raise node.fault
        return 0
    except (EndProxyError, OSError, ValueError) as exc:
        parser.exit(1, f"END direct bringup failed: {exc}\n")
    finally:
        if executor is not None:
            executor.shutdown()
        if node is not None:
            node.destroy_node()
        if 'rclpy' in locals() and rclpy.ok():
            rclpy.shutdown()
        port.closePort()
        import os
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
