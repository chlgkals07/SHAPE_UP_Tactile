#!/usr/bin/env python3
"""Remote keyboard for OMY's left HX5 hand-only teleoperation.

ROBOTIS's HX5 keyboard uses x for all-close and z for all-open. This client
keeps those keys, but sends one normalized grasp value to the Robot PC hand
bridge rather than commanding 20 joints directly. No arm joint is published.
"""

from __future__ import annotations

import argparse
import math
import select
import sys
import termios
import time
import tty
from contextlib import contextmanager
from dataclasses import dataclass


DEFAULT_TOPIC = "/hx5/keyboard_grasp_trajectory"
JOINT_NAME = "rh_r1_joint"


@dataclass
class KeyboardGrasp:
    value: float = 0.0
    step: float = 0.1

    def __post_init__(self) -> None:
        if not math.isfinite(self.value) or not 0.0 <= self.value <= 1.0:
            raise ValueError("initial grasp must be in [0, 1]")
        if not math.isfinite(self.step) or not 0.0 < self.step <= 1.0:
            raise ValueError("step must be in (0, 1]")

    def update(self, key: str) -> bool:
        """Return whether a recognized key changed the requested grasp."""
        before = self.value
        if key == "x":
            self.value = 1.0
        elif key == "z":
            self.value = 0.0
        elif key == "]":
            self.value = min(1.0, self.value + self.step)
        elif key == "[":
            self.value = max(0.0, self.value - self.step)
        return self.value != before


@contextmanager
def raw_keyboard():
    fd = sys.stdin.fileno()
    if not sys.stdin.isatty():
        raise RuntimeError("keyboard control needs an interactive terminal")
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield fd
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--topic", default=DEFAULT_TOPIC)
    p.add_argument("--rate-hz", type=float, default=20.0)
    p.add_argument("--step", type=float, default=0.1)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.topic or not math.isfinite(args.rate_hz) or not 1.0 <= args.rate_hz <= 100.0:
        parser().error("topic is required and rate-hz must be in [1, 100]")
    grasp = KeyboardGrasp(step=args.step)
    if not sys.stdin.isatty():
        parser().error("run from an interactive terminal")

    import rclpy
    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

    rclpy.init()
    node = rclpy.create_node("omy_hx5_hand_keyboard")
    publisher = node.create_publisher(JointTrajectory, args.topic, 10)
    period = 1.0 / args.rate_hz
    next_publish = time.monotonic()
    print("Left HX5 hand: x=close, z=open, ]=close 10%, [=open 10%, ESC=quit")
    print("Start at open (0%). Press z and allow the hand to open before quitting.")
    try:
        with raw_keyboard() as fd:
            while rclpy.ok():
                now = time.monotonic()
                if now >= next_publish:
                    msg = JointTrajectory()
                    msg.joint_names = [JOINT_NAME]
                    point = JointTrajectoryPoint()
                    point.positions = [grasp.value]
                    msg.points = [point]
                    publisher.publish(msg)
                    next_publish = now + period
                remaining = max(0.0, min(next_publish - time.monotonic(), period))
                ready, _, _ = select.select([fd], [], [], remaining)
                if ready:
                    key = sys.stdin.read(1)
                    if key == "\x1b":
                        break
                    if grasp.update(key):
                        print(f"\rrequested grasp: {grasp.value:.0%}   ", end="", flush=True)
                    elif key == "p":
                        print(f"\rrequested grasp: {grasp.value:.0%}   ", end="", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        print()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
