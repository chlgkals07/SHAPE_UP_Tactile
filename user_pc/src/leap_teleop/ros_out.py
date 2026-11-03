"""Record-only ROS 2 outputs for Cyclo (spec 2026-10-29-ros-data-interface-design.md, section 3.1).

Never on the control path: a failure here must not stop the hand, so publish() swallows errors.
rclpy is imported inside RosPublisher.__init__ so the package works and tests without ROS.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np

from leap_teleop.hand.joints import ANGLE_NAMES
from leap_teleop.types import HUMAN_ANGLE_NAMES, Reading

JOINT_NAMES = tuple(f"leap_{name}" for name in ANGLE_NAMES)
MODE_REPEAT_S = 1.0


def hand_state_units(feedback) -> tuple[list[float], list[float], list[float]]:
    """LeapHandFeedback (deg, deg/s, mA) -> JointState position (rad), velocity (rad/s), effort (mA)."""
    return (
        np.deg2rad(feedback.positions_degrees).tolist(),
        np.deg2rad(feedback.velocities_degrees_per_second).tolist(),
        np.asarray(feedback.currents_milliamps, dtype=float).tolist(),
    )


class RosPublisher:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        import rclpy
        from geometry_msgs.msg import PoseArray
        from sensor_msgs.msg import JointState
        from std_msgs.msg import String

        self._rclpy = rclpy
        self._clock = clock
        self._owns_context = not rclpy.ok()
        if self._owns_context:
            rclpy.init()
        self._node = rclpy.create_node("leap_teleop_record")
        make = self._node.create_publisher
        self._command = make(JointState, "/leap/joint_command", 10)
        self._state = make(JointState, "/leap/joint_states", 10)
        self._human = make(JointState, "/leap/human_hand", 10)
        self._keypoints = make(PoseArray, "/leap/human_keypoints", 10)
        self._mode = make(String, "/leap/teleop_mode", 10)
        self._msgs = (JointState, PoseArray, String)
        self._last_human_time: float | None = None
        self._last_mode: str | None = None
        self._mode_sent_at = 0.0

    def publish(
        self, command_degrees, feedback, mode: str, reading: Reading | None
    ) -> None:
        try:
            self._publish(command_degrees, feedback, mode, reading)
        except Exception:  # noqa: BLE001 - recording must never stop the hand
            pass

    def _publish(self, command_degrees, feedback, mode, reading) -> None:
        JointState, PoseArray, String = self._msgs
        stamp = self._node.get_clock().now().to_msg()

        msg = JointState()
        msg.header.stamp = stamp
        msg.name = list(JOINT_NAMES)
        msg.position = np.deg2rad(command_degrees).tolist()
        self._command.publish(msg)

        if feedback is not None:
            msg = JointState()
            msg.header.stamp = stamp
            msg.name = list(JOINT_NAMES)
            msg.position, msg.velocity, msg.effort = hand_state_units(feedback)
            self._state.publish(msg)

        human = reading.human if reading is not None else None
        if human is not None and reading.timestamp != self._last_human_time:
            self._last_human_time = reading.timestamp
            msg = JointState()  # raw Manus ergonomics, degrees (not converted)
            msg.header.stamp = stamp
            msg.name = list(HUMAN_ANGLE_NAMES)
            msg.position = human.angles.tolist()
            self._human.publish(msg)
            if human.keypoints is not None:
                points = PoseArray()  # order = KEYPOINT_NAMES, glove frame, metres
                points.header.stamp = stamp
                points.header.frame_id = "manus_glove"
                for x, y, z in human.keypoints:
                    points.poses.append(self._pose(x, y, z))
                self._keypoints.publish(points)

        now = self._clock()
        if mode != self._last_mode or now - self._mode_sent_at >= MODE_REPEAT_S:
            self._last_mode, self._mode_sent_at = mode, now
            self._mode.publish(String(data=mode))

    @staticmethod
    def _pose(x, y, z):
        from geometry_msgs.msg import Pose

        pose = Pose()
        pose.position.x, pose.position.y, pose.position.z = float(x), float(y), float(z)
        pose.orientation.w = 1.0
        return pose

    def close(self) -> None:
        for step in (self._node.destroy_node, *([self._rclpy.shutdown] if self._owns_context else [])):
            try:
                step()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
