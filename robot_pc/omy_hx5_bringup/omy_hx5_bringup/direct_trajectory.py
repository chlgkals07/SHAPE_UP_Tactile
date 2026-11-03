"""ROS-independent validation and interpolation for the END direct bridge."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi

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
MAX_JOG = 0.05  # rad; first physical trial must be a small single-joint move
OFFICIAL_GOAL_CURRENT = 300  # robotis_hand_bringup hx5_d20_left.launch.py
# ROBOTIS joint_trajectory_executor starts its quintic path at the measured
# pose. The 2026-11-03 hand rested 0.049 rad past joint17's limit, so only the
# followed final point must be inside the limits.
WAYPOINT_LIMIT_MARGIN = 0.1


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


def make_segment(names, positions, duration: float, start, now: float,
                 *, limit_margin: float = 0.0) -> Segment:
    """Interpolate from ``start``: the last commanded pose, as JTC does.

    Restarting from measured state would rewrite every untouched joint with
    its sagging measurement on each message, so idle fingers drift and a
    20 Hz stream never reaches its target.
    """
    if tuple(names) != JOINT_NAMES or len(positions) != 20 or len(start) != 20:
        raise ValueError("trajectory must contain all 20 left-hand joints in vendor order")
    if not isfinite(duration) or not 0 < duration <= 30:
        raise ValueError("trajectory duration must be in (0, 30] seconds")
    if any(not isfinite(value) or not low - limit_margin <= value <= high + limit_margin
           for value, (low, high) in zip(positions, JOINT_LIMITS)):
        raise ValueError("trajectory exceeds a ROBOTIS left-hand joint limit")
    if any(not isfinite(value) for value in start):
        raise ValueError("hand command state is not finite")
    start = tuple(start)
    goal = tuple(positions)
    safe_duration = max(duration, max(abs(a - b) for a, b in zip(start, goal)) / MAX_SPEED)
    return Segment(start, goal, now, safe_duration)


def make_jog_segment(joint_number: float, delta: float, start, now: float) -> Segment:
    """Move one joint relative to the commanded pose; keep the other goals.

    A real hand can hold a pose slightly outside the keyboard's target
    limits. Clamping every joint on the first command would move other
    fingers, so only the selected joint is checked against its target limit.
    """
    if (not isfinite(joint_number) or int(joint_number) != joint_number or
            not 1 <= joint_number <= 20):
        raise ValueError("jog joint number must be an integer from 1 to 20")
    if not isfinite(delta) or not 0 < abs(delta) <= MAX_JOG:
        raise ValueError("jog delta must be nonzero and at most 0.05 rad")
    if len(start) != 20 or any(not isfinite(value) or not -pi <= value <= pi
                               for value in start):
        raise ValueError("jog requires 20 finite commanded joint positions")
    index = int(joint_number) - 1
    goal = list(start)
    goal[index] += delta
    low, high = JOINT_LIMITS[index]
    if not low <= goal[index] <= high:
        raise ValueError(f"joint {index + 1} jog target exceeds its official limit")
    return Segment(tuple(start), tuple(goal), now, 0.5)


def make_trajectory_segment(names, points, start, now: float) -> Segment:
    """Accept vendor keyboard's one point and official init's 100 points.

    The bridge follows the final pose with a bounded linear ramp rather than
    replaying the vendor's sampled intermediate points over the slower END bus.
    Every intermediate pose and timestamp is still validated; intermediate
    poses may sit up to ``WAYPOINT_LIMIT_MARGIN`` outside a limit.
    """
    if not 1 <= len(points) <= 1000:
        raise ValueError("trajectory requires 1..1000 points")
    previous = -1.0
    for point in points:
        at = point.time_from_start.sec + point.time_from_start.nanosec / 1e9
        if at < 0 or at <= previous or at > 30:
            raise ValueError("trajectory times must increase within 30 seconds")
        make_segment(names, point.positions, 1.0, start, now,
                     limit_margin=WAYPOINT_LIMIT_MARGIN)
        previous = at
    return make_segment(names, points[-1].positions, previous, start, now)


def validate_currents(values) -> tuple[int, ...]:
    if len(values) != 20 or any(not isfinite(v) or v < 0 or v > 910
                                for v in values):
        raise ValueError("current command must contain 20 finite values in 0..910")
    return tuple(round(v) for v in values)
