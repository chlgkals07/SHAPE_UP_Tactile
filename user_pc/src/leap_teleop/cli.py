"""Command line entry point: `leap-teleop`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from leap_teleop.app import run_teleop
from leap_teleop.config import load_leader_gripper, load_postures
from leap_teleop.hand.base import HandDriver
from leap_teleop.retarget.scalar_posture import ScalarPostureRetargeter
from leap_teleop.safety import StaleGuard
from leap_teleop.sources.base import Source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leap-teleop",
        description="Drive a LEAP Hand v1 from the keyboard or the OMY leader gripper.",
    )
    parser.add_argument("--source", choices=("keyboard", "leader"), default="keyboard")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="LEAP Hand serial port")
    parser.add_argument(
        "--motor-calibration-file", type=Path, default=Path("config/hardware_motors.yaml")
    )
    parser.add_argument("--postures", type=Path, default=Path("config/postures.yaml"))
    parser.add_argument("--leader-gripper", type=Path, default=Path("config/leader_gripper.yaml"))
    parser.add_argument("--rate", type=float, default=50.0, help="control loop Hz (10-200)")
    parser.add_argument("--stale-timeout", type=float, default=0.5)
    parser.add_argument("--release-timeout", type=float, default=3.0)
    parser.add_argument("--current-limit", type=int, default=300, help="motor current limit in mA")
    parser.add_argument("--dry-run", action="store_true", help="log targets, do not touch hardware")
    return parser


def build_source(args: argparse.Namespace) -> Source:
    if args.source == "leader":
        from leap_teleop.sources.ros2_leader import Ros2LeaderSource

        return Ros2LeaderSource(load_leader_gripper(args.leader_gripper))
    from leap_teleop.sources.keyboard import KeyboardSource

    return KeyboardSource()


def build_driver(args: argparse.Namespace) -> HandDriver:
    if args.dry_run:
        from leap_teleop.hand.dry_run import LogDriver

        return LogDriver()
    from leap_teleop.hand.leap_driver import LeapHandDriver
    from leap_teleop.hand.leap_v1 import LeapHandHardwareController

    controller = LeapHandHardwareController(
        args.port,
        current_limit_milliamps=args.current_limit,
        motor_calibration=args.motor_calibration_file,
    )
    return LeapHandDriver(controller)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not 10.0 <= args.rate <= 200.0:
            raise ValueError("rate must be between 10 and 200 Hz (the bus watchdog is 500 ms)")
        open_pose, fist_pose = load_postures(args.postures)
        if not args.dry_run and not args.motor_calibration_file.exists():
            raise FileNotFoundError(
                f"{args.motor_calibration_file} not found. Run "
                "`python3 -m leap_teleop.tools.calibrate_motors` first; "
                "refusing to use nominal zeros."
            )
        if not args.dry_run and args.motor_calibration_file.name.endswith(".example.yaml"):
            raise ValueError(
                f"{args.motor_calibration_file} is the nominal template, not a measurement. "
                "Run `python3 -m leap_teleop.tools.calibrate_motors` and use its output."
            )
        guard = StaleGuard(open_pose, args.stale_timeout, args.release_timeout)
        retarget = ScalarPostureRetargeter(open_pose, fist_pose)
        driver = build_driver(args)
        source = build_source(args)
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    try:
        run_teleop(source, retarget, guard, driver, rate_hz=args.rate)
    except KeyboardInterrupt:
        print("interrupted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
