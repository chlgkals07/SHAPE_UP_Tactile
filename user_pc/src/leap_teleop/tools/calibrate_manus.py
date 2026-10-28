"""Record an operator's open hand and fist with the Manus glove -> config/manus_calibration.yaml.

Run on the User PC with ROS 2 sourced and the Manus SDK node publishing. No LEAP Hand needed.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from leap_teleop.config import (
    ManusCalibration,
    load_manus_calibration,
    load_manus_leap,
    load_postures,
    save_manus_calibration,
)
from leap_teleop.kinematics import LEAP_URDF, Chain, load_chain
from leap_teleop.retarget.manus_leap import ManusLeapRetargeter
from leap_teleop.types import HumanHand


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=Path("config/manus_leap.yaml"))
    parser.add_argument("--postures", type=Path, default=Path("config/postures.yaml"))
    parser.add_argument("--output", type=Path, default=Path("config/manus_calibration.yaml"))
    parser.add_argument("--side", default="Right")
    parser.add_argument("--seconds", type=float, default=1.5, help="hold time per pose")
    parser.add_argument("--force", action="store_true", help="allow replacing --output")
    return parser.parse_args(argv)


def median_hand(samples: Sequence[HumanHand]) -> HumanHand:
    """Per-value median, robust to a single glitchy frame. Keypoints only if every frame has them."""
    if not samples:
        raise ValueError("no glove samples were received")
    angles = np.median([s.angles for s in samples], axis=0)
    keypoints = None
    if all(s.keypoints is not None for s in samples):
        keypoints = np.median([s.keypoints for s in samples], axis=0)
    return HumanHand(angles, keypoints)


def hand_scale(chain: Chain, open_hand: HumanHand) -> float:
    """LEAP index length (MCP -> tip, open) over the operator's, measured the same way."""
    leap = np.linalg.norm(
        chain.link_position("index_tip_head", {}) - chain.link_position("mcp_joint", {})
    )
    human = np.linalg.norm(open_hand.point("index_tip") - open_hand.point("index_mcp"))
    if human <= 0.0:
        raise ValueError("index MCP and tip keypoints coincide")
    return float(leap / human)


def fist_thumb_sides_mm(
    retarget: ManusLeapRetargeter, fist_hand: HumanHand, fist_thumb_deg: np.ndarray,
    urdf_offset_deg: np.ndarray,
) -> tuple[float, float]:
    """How far in front of the palm (+) or behind it (-) the thumb tip is, in the LEAP frame.

    Returns (IK target from the operator's fist, LEAP fist posture). In a fist both thumbs sit
    in front of the palm, so opposite signs mean the glove palm frame is mirrored
    (flip thumb_ik.flip_normal). An open hand cannot show this: the thumb lies in the palm plane.
    """
    normal = retarget.palm_normal
    target, _ = retarget.thumb_targets(fist_hand)
    leap_tip, _ = retarget.thumb_points(np.radians(fist_thumb_deg + urdf_offset_deg))
    base = retarget.thumb_base
    return float((target - base) @ normal * 1000.0), float((leap_tip - base) @ normal * 1000.0)


def record(source, seconds: float) -> HumanHand:
    samples, seen = [], set()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        reading = source.poll(time.monotonic())
        if reading is not None and reading.timestamp not in seen:
            seen.add(reading.timestamp)
            samples.append(reading.human)
        time.sleep(0.01)
    print(f"  {len(samples)} samples")
    return median_hand(samples)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.output.exists() and not args.force:
        print(f"error: {args.output} exists; use --force to replace it", file=sys.stderr)
        return 2
    cfg = load_manus_leap(args.config)
    fist_pose = load_postures(args.postures)[1]
    chain = load_chain(LEAP_URDF)

    from leap_teleop.sources.manus import Ros2ManusSource

    source = Ros2ManusSource(cfg.topic, side=args.side)
    try:
        input("손을 완전히 편 채(손가락 붙이고 엄지는 자연스럽게) Enter → 기록")
        open_hand = record(source, args.seconds)
        input("주먹을 꽉 쥔 채 Enter → 기록")
        fist_hand = record(source, args.seconds)
    finally:
        source.close()

    if open_hand.keypoints is None:
        scale = load_manus_calibration(args.output).scale if args.output.exists() else 1.6
        print(f"warning: no keypoints, keeping scale {scale} (thumb IK will fall back to affine)")
    else:
        scale = hand_scale(chain, open_hand)
    calibration = ManusCalibration(open_hand.angles, fist_hand.angles, scale)
    save_manus_calibration(calibration, args.output)
    print(f"saved {args.output} (scale {scale:.3f})")

    small_span = np.abs(fist_hand.angles - open_hand.angles) < 10.0
    if small_span.any():
        from leap_teleop.types import HUMAN_ANGLE_NAMES

        print("note: these barely moved (spreads are expected):",
              [n for n, s in zip(HUMAN_ANGLE_NAMES, small_span) if s])
    if fist_hand.keypoints is not None:
        retarget = ManusLeapRetargeter(cfg, calibration, fist_pose, chain, "ik")
        target, leap = fist_thumb_sides_mm(
            retarget, fist_hand, fist_pose[12:16], cfg.urdf_offset_deg[12:16])
        print(f"fist thumb, mm in front of palm: glove target {target:.0f}, LEAP fist {leap:.0f}")
        if target * leap < 0:
            print("WARNING: opposite sides -> palm frame mirrored. "
                  "Set thumb_ik.flip_normal in the config and re-run with --force.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
