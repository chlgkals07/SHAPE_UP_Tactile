"""Grasp input from the OMY leader gripper (rh_r1_joint on /leader/joint_trajectory).

rclpy is imported inside Ros2LeaderSource.__init__ so the rest of the package, and the
pure function below, work and test without ROS installed.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Sequence

from leap_teleop.config import LeaderGripperConfig
from leap_teleop.sources.base import Source
from leap_teleop.types import Reading


def grasp_from_trajectory(
    joint_names: Sequence[str],
    points_positions: Sequence[Sequence[float]],
    cfg: LeaderGripperConfig,
) -> float | None:
    """Normalise the leader gripper joint of the first trajectory point to 0 (open)..1 (closed)."""
    if cfg.joint_name not in joint_names or not points_positions:
        return None
    index = list(joint_names).index(cfg.joint_name)
    positions = points_positions[0]
    if index >= len(positions):
        return None
    value = float(positions[index])
    if not math.isfinite(value):
        return None
    grasp = (value - cfg.open_value) / (cfg.closed_value - cfg.open_value)
    return min(1.0, max(0.0, grasp))


class Ros2LeaderSource(Source):
    def __init__(
        self, cfg: LeaderGripperConfig, clock: Callable[[], float] = time.monotonic
    ) -> None:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from trajectory_msgs.msg import JointTrajectory

        self._cfg = cfg
        self._clock = clock
        self._rclpy = rclpy
        self._owns_context = not rclpy.ok()
        if self._owns_context:
            rclpy.init()
        self._node = rclpy.create_node("leap_teleop_leader_source")
        self._lock = threading.Lock()
        self._latest: Reading | None = None
        # Best-effort QoS matches both reliable and best-effort publishers.
        self._node.create_subscription(
            JointTrajectory, cfg.topic, self._on_message, qos_profile_sensor_data
        )
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._thread.start()

    def _on_message(self, msg) -> None:
        points = [list(point.positions) for point in msg.points[:1]]
        grasp = grasp_from_trajectory(list(msg.joint_names), points, self._cfg)
        if grasp is None:
            return
        reading = Reading(timestamp=self._clock(), grasp=grasp)
        with self._lock:
            self._latest = reading

    def poll(self, now: float) -> Reading | None:
        with self._lock:
            return self._latest

    def close(self) -> None:
        self._executor.shutdown()
        self._node.destroy_node()
        if self._owns_context and self._rclpy.ok():
            self._rclpy.shutdown()
        self._thread.join(timeout=1.0)
