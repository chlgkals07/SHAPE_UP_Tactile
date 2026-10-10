"""OMY leader gripper to HX5-D20 tactile assisted teleoperation."""

from __future__ import annotations

import argparse
import math

from hx5_teleop.core import Hx5CoreConfig, Hx5GraspCore
from leap_teleop.config import LeaderGripperConfig


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--side", choices=("left", "right"), default="left")
    p.add_argument("--leader-open", type=float, required=True,
                   help="measured rh_r1_joint value with leader gripper fully open")
    p.add_argument("--leader-closed", type=float, required=True,
                   help="measured rh_r1_joint value with leader gripper fully closed")
    p.add_argument("--leader-topic", default="/leader/joint_trajectory")
    p.add_argument("--leader-joint", default="rh_r1_joint")
    p.add_argument("--contact-threshold", type=float, default=10.0,
                   help="experimental baseline-corrected 9-taxel sum, not newtons")
    p.add_argument("--pressure-hard-cap", type=float, default=30.0,
                   help="experimental 9-taxel sum ceiling, not newtons")
    p.add_argument("--baseline-frames", type=int, default=30)
    p.add_argument("--max-joint-speed", type=float, default=0.5,
                   help="per-joint command slew limit in rad/s")
    p.add_argument("--dry-run", action="store_true",
                   help="subscribe and calculate but publish no hand command")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if (not math.isfinite(args.leader_open) or not math.isfinite(args.leader_closed)
            or args.leader_open == args.leader_closed):
        parser().error("leader open and closed must be different finite measurements")
    core = Hx5GraspCore(Hx5CoreConfig(
        hand_side=args.side,
        baseline_frames=args.baseline_frames,
        contact_threshold=args.contact_threshold,
        pressure_hard_cap=args.pressure_hard_cap,
        max_joint_speed_rad_s=args.max_joint_speed,
    ))
    leader = LeaderGripperConfig(
        topic=args.leader_topic,
        joint_name=args.leader_joint,
        open_value=args.leader_open,
        closed_value=args.leader_closed,
    )
    from hx5_teleop.ros_bridge import Hx5RosBridge

    bridge = Hx5RosBridge(core, leader, side=args.side, dry_run=args.dry_run)
    bridge.spin()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
