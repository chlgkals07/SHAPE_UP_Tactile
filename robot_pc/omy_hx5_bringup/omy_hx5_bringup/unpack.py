"""Move the OMY arm to ROBOTIS's unpack pose and monitor its held posture.

The controller manager remains alive after this action completes. Hand motion
requires this node's continuously refreshed ready signal; faults are latched.
"""

from __future__ import annotations

import math
import time

from omy_hx5_bringup.arm_bridge import ARM_JOINTS, arm_positions

# Official open_manipulator_bringup/config/omy_3m/{initial,pack}_positions.yaml.
UNPACK_POSITION = (0.0,) * 6
PACK_POSITION = (0.0, 0.0, -2.61799, -0.52360, 0.0, 0.0)


def allowed_start(positions: tuple[float, ...], tolerance: float = 0.15) -> bool:
    """Only accept the documented packed posture or an already unpacked arm."""
    return len(positions) == 6 and all(math.isfinite(x) for x in positions) and any(
        max(abs(a - b) for a, b in zip(positions, pose)) <= tolerance
        for pose in (PACK_POSITION, UNPACK_POSITION)
    )


def create_coordinator():
    import rclpy
    from action_msgs.msg import GoalStatus
    from control_msgs.action import FollowJointTrajectory
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import JointState
    from std_msgs.msg import Bool
    from trajectory_msgs.msg import JointTrajectoryPoint

    class ArmUnpackCoordinator(Node):
        def __init__(self):
            super().__init__("omy_hx5_unpack_and_hold")
            defaults = {
                "unpack_duration": 10.0,
                "startup_timeout": 30.0,
                "settle_timeout": 5.0,
                "joint_timeout": 0.5,
                "position_tolerance": 0.01,
                "hold_tolerance": 0.05,
                "start_tolerance": 0.15,
                "settle_duration": 0.5,
            }
            for name, default in defaults.items():
                self.declare_parameter(name, default)
                value = float(self.get_parameter(name).value)
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(f"{name} must be finite and positive")
                setattr(self, name, value)
            self.phase = "waiting"
            self.deadline = time.monotonic() + self.startup_timeout
            self.joint = None
            self.settled_since = None
            self.goal_handle = None
            self.ready = self.create_publisher(Bool, "/hx5/arm_unpack_ready", 10)
            self.client = ActionClient(self, FollowJointTrajectory,
                                       "/arm_controller/follow_joint_trajectory")
            self.create_subscription(JointState, "/joint_states", self.on_joint,
                                     qos_profile_sensor_data)
            self.create_timer(0.05, self.tick)
            self.get_logger().info("Waiting for arm controller and measured joints; hand blocked")

        def on_joint(self, msg):
            values = arm_positions(msg.name, msg.position)
            if values is not None:
                self.joint = (values, time.monotonic())

        def fault(self, reason):
            if self.phase == "fault":
                return
            self.phase = "fault"
            self.ready.publish(Bool(data=False))
            if self.goal_handle is not None:
                self.goal_handle.cancel_goal_async()
            self.get_logger().error(f"{reason}; hand blocked. Restart launch after resolving fault")

        def goal_response(self, future):
            try:
                handle = future.result()
                if not handle.accepted:
                    self.fault("Arm unpack goal rejected")
                    return
                self.goal_handle = handle
                if self.phase == "fault":
                    handle.cancel_goal_async()
                    return
                handle.get_result_async().add_done_callback(self.goal_result)
            except Exception as exc:
                self.fault(f"Arm unpack goal failed: {exc}")

        def goal_result(self, future):
            if self.phase == "fault":
                return
            try:
                result = future.result()
                if (result.status != GoalStatus.STATUS_SUCCEEDED
                        or result.result.error_code != FollowJointTrajectory.Result.SUCCESSFUL):
                    self.fault(f"Arm unpack failed: {result.result.error_string}")
                    return
            except Exception as exc:
                self.fault(f"Arm unpack result failed: {exc}")
                return
            self.phase = "verifying"
            self.deadline = time.monotonic() + self.settle_timeout
            self.settled_since = None

        def tick(self):
            self.advance()
            self.ready.publish(Bool(data=self.phase == "ready"))

        def advance(self):
            now = time.monotonic()
            if self.phase == "fault":
                return
            if self.count_publishers("/arm_controller/joint_trajectory"):
                self.fault("Another arm trajectory publisher detected")
                return
            fresh = self.joint is not None and now - self.joint[1] <= self.joint_timeout
            if self.phase == "waiting":
                if now >= self.deadline:
                    self.fault("Arm startup timed out")
                elif fresh and self.client.server_is_ready():
                    if not allowed_start(self.joint[0], self.start_tolerance):
                        self.fault("Arm is neither in the official packed nor unpacked posture")
                        return
                    goal = FollowJointTrajectory.Goal()
                    goal.trajectory.joint_names = list(ARM_JOINTS)
                    point = JointTrajectoryPoint(positions=list(UNPACK_POSITION))
                    sec, nanosec = divmod(round(self.unpack_duration * 1e9), 1_000_000_000)
                    point.time_from_start.sec = sec
                    point.time_from_start.nanosec = nanosec
                    goal.trajectory.points = [point]
                    self.phase = "moving"
                    self.deadline = now + self.unpack_duration + self.settle_timeout
                    self.client.send_goal_async(goal).add_done_callback(self.goal_response)
                    self.get_logger().info("Moving arm to unpack pose; hand commands blocked")
                return
            if not fresh:
                self.fault("Arm joint states stale")
                return
            error = max(abs(a - b) for a, b in zip(self.joint[0], UNPACK_POSITION))
            if self.phase in ("moving", "verifying") and now >= self.deadline:
                self.fault("Arm unpack/settling timed out")
            elif self.phase == "verifying":
                if error > self.position_tolerance:
                    self.settled_since = None
                elif self.settled_since is None:
                    self.settled_since = now
                elif now - self.settled_since >= self.settle_duration:
                    self.phase = "ready"
                    self.get_logger().info(
                        "Arm unpack complete; arm controller holds pose; keyboard hand control enabled")
            elif self.phase == "ready" and error > self.hold_tolerance:
                self.fault("Arm departed from held unpack pose")

    return ArmUnpackCoordinator()


def main(args=None):
    import rclpy
    from rclpy.executors import ExternalShutdownException

    rclpy.init(args=args)
    node = create_coordinator()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
