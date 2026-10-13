"""ROS 2 I/O for a single HX5-D20 leader/tactile teleoperation publisher.

The pure parsers stay importable without ROS so malformed or stale messages can be
tested before a hand is connected. ROS imports happen only when the bridge starts.
"""

from __future__ import annotations

import math
import time
from hx5_teleop.core import Hx5GraspCore, TactileFrame
from hx5_teleop.leader import LeaderGripperConfig, grasp_from_trajectory


def joint_names(side: str) -> tuple[str, ...]:
    if side not in ("left", "right"):
        raise ValueError("side must be left or right")
    return tuple(f"finger_{side[0]}_joint{i}" for i in range(1, 21))


def pressure_sensor_names(side: str) -> tuple[str, ...]:
    if side not in ("left", "right"):
        raise ValueError("side must be left or right")
    return tuple(f"finger_{side[0]}_sensor{i}" for i in range(1, 6))


def joint_positions(msg: object, side: str) -> tuple[float, ...] | None:
    """Read exactly the selected hand's twenty joint states in official order."""
    names = getattr(msg, "name", ())
    positions = getattr(msg, "position", ())
    if len(names) != len(positions) or len(set(names)) != len(names):
        return None
    by_name = dict(zip(names, positions))
    try:
        values = tuple(float(by_name[name]) for name in joint_names(side))
    except (KeyError, TypeError, ValueError):
        return None
    return values if all(math.isfinite(value) for value in values) else None


def pressure_frame(
    msg: object,
    *,
    side: str,
    received_at: float,
    ros_now_ns: int,
    max_stamp_age: float = 0.5,
) -> TactileFrame | None:
    """Validate hand identity, stamp, and all five 3x3 uint8 arrays.

    Convert the ROS stamp's age to a monotonic sample time for control timeouts.
    The two hosts need synced clocks. A small permitted future clock skew is
    clamped to the arrival time, never treated as a future sample.
    """
    if getattr(msg, "hand_name", None) != side:
        return None
    if not math.isfinite(received_at) or max_stamp_age <= 0:
        return None
    try:
        stamp = msg.header.stamp
        stamp_ns = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
        sensors = msg.sensors
    except (AttributeError, TypeError, ValueError):
        return None
    age_ns = ros_now_ns - stamp_ns
    if stamp_ns <= 0 or age_ns > max_stamp_age * 1e9 or age_ns < -100_000_000:
        return None
    expected = pressure_sensor_names(side)
    if len(sensors) != len(expected):
        return None
    by_name = {sensor.sensor_name: sensor for sensor in sensors}
    if len(by_name) != len(expected) or set(by_name) != set(expected):
        return None
    values = []
    for name in expected:
        sensor = by_name[name]
        if len(sensor.pressure_names) != 9 or len(sensor.pressure_values) != 9:
            return None
        try:
            row = tuple(int(value) for value in sensor.pressure_values)
        except (TypeError, ValueError):
            return None
        if any(
            value < 0 or value > 255 or value != raw
            for value, raw in zip(row, sensor.pressure_values)
        ):
            return None
        values.append(row)
    sample_time = received_at - max(0.0, age_ns / 1_000_000_000)
    return TactileFrame(timestamp=sample_time, values=tuple(values))


class Hx5RosBridge:
    """Own exactly one HX5 command topic; never starts the official grasp demo."""

    def __init__(
        self,
        core: Hx5GraspCore,
        leader: LeaderGripperConfig,
        *,
        side: str = "left",
        dry_run: bool = False,
        control_hz: float = 20.0,
        leader_timeout: float = 0.5,
        joint_timeout: float = 0.5,
        tracking_error_limit: float = 0.5,
    ) -> None:
        if core.config.hand_side != side:
            raise ValueError("core hand_side must match the ROS bridge side")
        import rclpy
        from rclpy.qos import qos_profile_sensor_data
        from robotis_interfaces.msg import HandPressures
        from sensor_msgs.msg import JointState
        from trajectory_msgs.msg import JointTrajectory

        if not (0 < control_hz <= 100 and leader_timeout > 0 and joint_timeout > 0):
            raise ValueError("invalid control rate or timeout")
        if tracking_error_limit <= 0:
            raise ValueError("tracking_error_limit must be positive")
        self.side = side
        self.names = joint_names(side)
        self.topic = f"/hand_{side[0]}_controller/joint_trajectory"
        self._core = core
        self._leader_cfg = leader
        self._dry_run = dry_run
        self._leader_timeout = leader_timeout
        self._joint_timeout = joint_timeout
        self._tracking_error_limit = tracking_error_limit
        self._startup_delta_limit = core.config.max_joint_speed_rad_s / control_hz
        self._startup_motion_fault = False
        self._rclpy = rclpy
        self._owns_context = not rclpy.ok()
        if self._owns_context:
            rclpy.init()
        self.node = rclpy.create_node(f"hx5_{side}_omy_teleop")
        self._leader: tuple[float, float] | None = None
        self._joint: tuple[tuple[float, ...], float] | None = None
        self._tactile: TactileFrame | None = None
        self._used_tactile_time = -math.inf
        self._last_stamp_ns = -1
        self._last_command: tuple[float, ...] | None = None
        self._active = False
        self._last_log = 0.0
        self._mode = "waiting for joint states"
        self._JointTrajectory = JointTrajectory
        self._publisher = None if dry_run else self.node.create_publisher(
            JointTrajectory, self.topic, 10
        )
        self.node.create_subscription(
            JointTrajectory, leader.topic, self._on_leader, qos_profile_sensor_data
        )
        self.node.create_subscription(
            HandPressures,
            f"/{side}_hand/finger_pressures",
            self._on_pressure,
            qos_profile_sensor_data,
        )
        self.node.create_subscription(
            JointState, "/joint_states", self._on_joint, qos_profile_sensor_data
        )
        self.node.create_timer(1.0 / control_hz, self._tick)

    def _on_leader(self, msg: object) -> None:
        points = [point.positions for point in msg.points[:1]]
        grasp = grasp_from_trajectory(msg.joint_names, points, self._leader_cfg)
        if grasp is not None:
            self._leader = (grasp, time.monotonic())

    def _on_pressure(self, msg: object) -> None:
        stamp = msg.header.stamp
        stamp_ns = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
        if stamp_ns <= self._last_stamp_ns:
            return
        frame = pressure_frame(
            msg,
            side=self.side,
            received_at=time.monotonic(),
            ros_now_ns=self.node.get_clock().now().nanoseconds,
        )
        if frame is not None:
            self._last_stamp_ns = stamp_ns
            self._tactile = frame

    def _on_joint(self, msg: object) -> None:
        values = joint_positions(msg, self.side)
        if values is None:
            return
        now = time.monotonic()
        self._joint = (values, now)
        if self._last_command is None:
            try:
                self._core.initialize(values, now)
            except ValueError as exc:
                self._report(f"invalid initial joint state: {exc}; command stopped", now)
                return
            self._last_command = self._core.command

    def _tick(self) -> None:
        now = time.monotonic()
        if (self._last_command is None or self._joint is None
                or now - self._joint[1] > self._joint_timeout):
            self._report("joint states stale; command stopped", now)
            return
        if not self._dry_run and self.node.count_publishers(self.topic) > 1:
            self._report("another HX5 command publisher detected; command stopped", now)
            return
        if self._last_command is not None and max(
            abs(a - b) for a, b in zip(self._last_command, self._joint[0])
        ) > self._tracking_error_limit:
            self._report("joint tracking error; command stopped", now)
            return
        if not self._active:
            # A pre-activation command has never been sent to the hand. If the
            # measured posture changed, baseline samples and the seeded target
            # may no longer describe the same unloaded open hand.
            if max(abs(a - b) for a, b in zip(self._last_command, self._joint[0])) > self._startup_delta_limit:
                self._startup_motion_fault = True
            if self._startup_motion_fault:
                self._report("hand moved during baseline; restart bridge before commanding", now)
                return
        grasp = None
        if self._leader is not None and now - self._leader[1] <= self._leader_timeout:
            grasp = self._leader[0]
        tactile = None
        if self._tactile is not None and self._tactile.timestamp > self._used_tactile_time:
            tactile = self._tactile
            self._used_tactile_time = tactile.timestamp
        positions = self._core.step(grasp, tactile, now, motion_enabled=self._active)
        if len(positions) != 20 or not all(math.isfinite(value) for value in positions):
            self._report("invalid core command; command stopped", now)
            return
        if not self._active:
            if grasp is None or not self._core.baseline_ready:
                self._report(
                    "waiting for released leader and tactile baseline "
                    f"({self._core.baseline_samples}/{self._core.config.baseline_frames})",
                    now,
                )
                return
            self._active = True
        self._last_command = tuple(positions)
        if self._publisher is not None:
            from trajectory_msgs.msg import JointTrajectoryPoint

            msg = self._JointTrajectory()
            # ros2_control treats a zero trajectory stamp as "start now".
            # This also works when Gazebo's controller uses simulated time
            # while the bridge receives wall-clock leader/tactile messages.
            msg.joint_names = list(self.names)
            point = JointTrajectoryPoint()
            point.positions = list(positions)
            point.time_from_start.nanosec = 50_000_000
            msg.points = [point]
            self._publisher.publish(msg)
        self._report(
            f"{'dry-run' if self._dry_run else 'live'} grasp={grasp} "
            f"index_j6={positions[5]:.3f} thumb_j3={positions[2]:.3f} "
            f"raw_sums={tuple(round(value, 1) for value in self._core.pressure_sums)} "
            f"contact={self._core.contacted} fault={self._core.faulted}",
            now,
        )

    def _report(self, message: str, now: float) -> None:
        mode = message.split(" ", 1)[0]
        if mode != self._mode or now - self._last_log >= 2.0:
            self.node.get_logger().info(message)
            self._mode = mode
            self._last_log = now

    def spin(self) -> None:
        from rclpy.executors import ExternalShutdownException

        try:
            self._rclpy.spin(self.node)
        except (KeyboardInterrupt, ExternalShutdownException):
            pass
        finally:
            self.node.destroy_node()
            if self._owns_context and self._rclpy.ok():
                self._rclpy.shutdown()
