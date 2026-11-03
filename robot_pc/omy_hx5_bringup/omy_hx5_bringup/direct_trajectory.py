"""ROS-independent validation and interpolation for the END direct bridge."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

JOINT_NAMES = tuple(f"finger_l_joint{i}" for i in range(1, 21))
# Same left-hand limits as ROBOTIS hx5_d20_teleop.py.
JOINT_LIMITS = (
    (-1.57, 1.57), (0.0, 1.57), (-1.57, 0.5), (-1.57, 0.5),
    (-0.6, 0.6), (0.0, 2.0), (0.0, 1.57), (0.0, 1.57),
    (-0.6, 0.6), (0.0, 2.0), (0.0, 1.57), (0.0, 1.57),
    (-0.6, 0.6), (0.0, 2.0), (0.0, 1.57), (0.0, 1.57),
    (-0.6, 0.6), (0.0, 2.0), (0.0, 1.57), (0.0, 1.57),
)
MAX_SPEED = 1.0  # rad/s; lengthens unusually fast incoming trajectories


@dataclass(frozen=True)
class Segment:
    start: tuple[float, ...]
    goal: tuple[float, ...]
    start_time: float
    duration: float

    def sample(self, now: float) -> tuple[float, ...]:
        fraction = max(0.0, min(1.0, (now - self.start_time) / self.duration))
        return tuple(a + (b - a) * fraction for a, b in zip(self.start, self.goal))

    def done(self, now: float) -> bool:
        return now >= self.start_time + self.duration


def make_segment(names, positions, duration: float, measured, now: float) -> Segment:
    if tuple(names) != JOINT_NAMES or len(positions) != 20 or len(measured) != 20:
        raise ValueError("trajectory must contain all 20 left-hand joints in vendor order")
    if not isfinite(duration) or not 0 < duration <= 30:
        raise ValueError("trajectory duration must be in (0, 30] seconds")
    if any(not isfinite(value) or not low <= value <= high
           for value, (low, high) in zip(positions, JOINT_LIMITS)):
        raise ValueError("trajectory exceeds a ROBOTIS left-hand joint limit")
    if any(not isfinite(value) for value in measured):
        raise ValueError("hand state is not finite")
    start = tuple(measured)
    goal = tuple(positions)
    safe_duration = max(duration, max(abs(a - b) for a, b in zip(start, goal)) / MAX_SPEED)
    return Segment(start, goal, now, safe_duration)


def make_trajectory_segment(names, points, measured, now: float) -> Segment:
    """Accept vendor keyboard's one point and official init's 100 points.

    The bridge follows the final pose with a bounded linear ramp rather than
    replaying the vendor's sampled intermediate points over the slower END bus.
    Every intermediate pose and timestamp is still validated.
    """
    if not 1 <= len(points) <= 1000:
        raise ValueError("trajectory requires 1..1000 points")
    previous = -1.0
    for point in points:
        at = point.time_from_start.sec + point.time_from_start.nanosec / 1e9
        if at < 0 or at <= previous or at > 30:
            raise ValueError("trajectory times must increase within 30 seconds")
        make_segment(names, point.positions, 1.0, measured, now)
        previous = at
    return make_segment(names, points[-1].positions, previous, measured, now)


def validate_currents(values) -> tuple[int, ...]:
    if len(values) != 20 or any(not isfinite(v) or v < 0 or v > 910
                                for v in values):
        raise ValueError("current command must contain 20 finite values in 0..910")
    return tuple(round(v) for v in values)
