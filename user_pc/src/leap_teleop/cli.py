"""Command line entry point: `leap-teleop`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from leap_teleop.app import run_teleop
from leap_teleop.config import (
    load_leader_gripper,
    load_manus_calibration,
    load_manus_leap,
    load_postures,
)
from leap_teleop.hand.base import HandDriver
from leap_teleop.retarget.scalar_posture import ScalarPostureRetargeter
from leap_teleop.safety import StaleGuard
from leap_teleop.sources.base import Source
from leap_teleop.types import Retargeter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leap-teleop",
        description="Drive a LEAP Hand v1 from the keyboard, the OMY leader gripper or a Manus glove.",
    )
    parser.add_argument("--source", choices=("keyboard", "leader", "manus"), default="keyboard")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="LEAP Hand serial port")
    parser.add_argument(
        "--motor-calibration-file", type=Path, default=Path("config/hardware_motors.yaml")
    )
    parser.add_argument("--postures", type=Path, default=Path("config/postures.yaml"))
    parser.add_argument("--leader-gripper", type=Path, default=Path("config/leader_gripper.yaml"))
    parser.add_argument("--manus-config", type=Path, default=Path("config/manus_leap.yaml"))
    parser.add_argument(
        "--manus-calibration", type=Path, default=Path("config/manus_calibration.yaml")
    )
    parser.add_argument(
        "--thumb", choices=("ik", "affine"), default="ik", help="Manus thumb retargeting"
    )
    parser.add_argument("--glove-side", default="Right", help="Manus glove side to follow")
    parser.add_argument("--rate", type=float, default=50.0, help="control loop Hz (10-200)")
    parser.add_argument("--stale-timeout", type=float, default=0.5)
    parser.add_argument("--release-timeout", type=float, default=3.0)
    parser.add_argument("--current-limit", type=int, default=300, help="motor current limit in mA")
    parser.add_argument(
        "--safe-pose",
        choices=("open", "fist"),
        default="open",
        help="pose while waiting for the first input and after the input is lost",
    )
    parser.add_argument("--dry-run", action="store_true", help="log targets, do not touch hardware")
    return parser


def build_source(args: argparse.Namespace) -> Source:
    if args.source == "manus":
        from leap_teleop.sources.manus import Ros2ManusSource

        return Ros2ManusSource(args.manus.topic, side=args.glove_side)
    if args.source == "leader":
        from leap_teleop.sources.ros2_leader import Ros2LeaderSource

        return Ros2LeaderSource(load_leader_gripper(args.leader_gripper))
    from leap_teleop.sources.keyboard import KeyboardSource

    return KeyboardSource()


def build_retargeter(
    args: argparse.Namespace, open_pose, fist_pose
) -> Retargeter:
    if args.source != "manus":
        return ScalarPostureRetargeter(open_pose, fist_pose)
    from leap_teleop.kinematics import LEAP_URDF, load_chain
    from leap_teleop.retarget.manus_leap import ManusLeapRetargeter

    if not args.manus_calibration.exists():
        raise FileNotFoundError(
            f"{args.manus_calibration} not found. Run "
            "`python3 -m leap_teleop.tools.calibrate_manus` first "
            "(for --dry-run, config/manus_calibration.example.yaml also works)."
        )
    if not args.dry_run and args.manus_calibration.name.endswith(".example.yaml"):
        raise ValueError(
            f"{args.manus_calibration} is a nominal example, not this operator's hand. "
            "Run `python3 -m leap_teleop.tools.calibrate_manus`."
        )
    return ManusLeapRetargeter(
        args.manus,
        load_manus_calibration(args.manus_calibration),
        fist_pose,
        load_chain(LEAP_URDF),
        args.thumb,
    )


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
        args.manus = load_manus_leap(args.manus_config) if args.source == "manus" else None
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
        safe_pose = fist_pose if args.safe_pose == "fist" else open_pose
        guard = StaleGuard(safe_pose, args.stale_timeout, args.release_timeout)
        retarget = build_retargeter(args, open_pose, fist_pose)
        # Input first: a missing ROS / Manus package must fail before the hand is opened.
        source = build_source(args)
        try:
            driver = build_driver(args)
        except BaseException:
            source.close()
            raise
    except (FileNotFoundError, ValueError, RuntimeError, ImportError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    try:
        run_teleop(source, retarget, guard, driver, rate_hz=args.rate)
    except KeyboardInterrupt:
        print("interrupted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
