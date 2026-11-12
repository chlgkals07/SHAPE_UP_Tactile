"""Command-line interface for the Paxini SDK.

After installation (``pip install -e .``) you get a ``paxini`` console script:

* ``paxini list`` — enumerate USB-serial ports
* ``paxini info --port <port>`` — read the firmware version (high-speed board)
* ``paxini single calibrate --port <port>``
* ``paxini single force --port <port> [--watch]``
* ``paxini hand stream --port <port> [--duration N]``
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Sequence

from .boards.high_speed import HighSpeedHandBoard
from .boards.serial_converter import SingleSensorBoard
from .exceptions import PaxiniError
from .transport import list_serial_ports


def _cmd_list(args: argparse.Namespace) -> int:
    ports = list_serial_ports()
    if not ports:
        print("No serial ports detected.", file=sys.stderr)
        print(
            "  On macOS, ensure your USB-serial driver is installed.\n"
            "  Common bridges: CH340 (WCH), CP2102 (Silicon Labs), FTDI.\n"
            "  Look for /dev/cu.usbserial-* or /dev/cu.SLAB_USBtoUART.",
            file=sys.stderr,
        )
        return 1
    print(f"{'DEVICE':<32} {'DESCRIPTION':<32} HWID")
    for p in ports:
        print(f"{p.device:<32} {p.description:<32} {p.hwid}")
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    with HighSpeedHandBoard(args.port, baudrate=args.baud) as hand:
        print("Firmware version:", hand.read_version())
    return 0


def _cmd_single_calibrate(args: argparse.Namespace) -> int:
    with SingleSensorBoard(args.port, baudrate=args.baud) as board:
        board.calibrate()
        print("Calibration command sent.")
    return 0


def _cmd_single_force(args: argparse.Namespace) -> int:
    with SingleSensorBoard(args.port, baudrate=args.baud) as board:
        if args.calibrate:
            board.calibrate()
            print("Calibrated.")
        try:
            while True:
                fx, fy, fz = board.read_resultant_force()
                print(f"Fx={fx:>5}  Fy={fy:>5}  Fz={fz:>5}")
                if not args.watch:
                    break
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


def _cmd_single_distributed(args: argparse.Namespace) -> int:
    with SingleSensorBoard(args.port, baudrate=args.baud) as board:
        if args.calibrate:
            board.calibrate()
        points = board.read_distributed_force(point_count=args.points)
        print(f"Got {len(points)} points")
        for i, p in enumerate(points):
            print(f"  [{i:>3}] Fx={p.fx:>5}  Fy={p.fy:>5}  Fz={p.fz:>5}")
    return 0


def _cmd_hand_stream(args: argparse.Namespace) -> int:
    with HighSpeedHandBoard(args.port, baudrate=args.baud) as hand:
        deadline = time.monotonic() + args.duration if args.duration > 0 else None
        try:
            for frame in hand.stream_auto_push(
                duration=args.duration if args.duration > 0 else None
            ):
                forces = frame.module_forces
                print(
                    f"[{frame.timestamp:.3f}] err=0x{frame.error_code:02X} "
                    f"modules={len(forces)} bytes={len(frame.valid_data)}"
                )
                if args.verbose:
                    for name, (fx, fy, fz) in zip(
                        ["Th-P", "Th-M", "Th-T", "Th-N",
                         "Ix-P", "Ix-M", "Ix-T", "Ix-N",
                         "Mi-P", "Mi-M", "Mi-T", "Mi-N",
                         "Ri-P", "Ri-M", "Ri-T", "Ri-N",
                         "Li-P", "Li-M", "Li-T", "Li-N",
                         "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"],
                        forces,
                    ):
                        print(f"   {name:>5}: Fx={fx:>6} Fy={fy:>6} Fz={fz:>6}")
                if deadline and time.monotonic() >= deadline:
                    break
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


def _cmd_hand_modules(args: argparse.Namespace) -> int:
    with HighSpeedHandBoard(args.port, baudrate=args.baud) as hand:
        forces = hand.read_module_forces()
        for name, (fx, fy, fz) in zip(
            [
                "Thumb-Proximal", "Thumb-Middle", "Thumb-Tip", "Thumb-Nail",
                "Index-Proximal", "Index-Middle", "Index-Tip", "Index-Nail",
                "Middle-Proximal", "Middle-Middle", "Middle-Tip", "Middle-Nail",
                "Ring-Proximal", "Ring-Middle", "Ring-Tip", "Ring-Nail",
                "Little-Proximal", "Little-Middle", "Little-Tip", "Little-Nail",
                "Palm-1", "Palm-2", "Palm-3", "Palm-4",
                "Palm-5", "Palm-6", "Palm-7", "Palm-8",
            ],
            forces,
        ):
            print(f"  {name:<18}  Fx={fx:>6}  Fy={fy:>6}  Fz={fz:>6}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paxini",
        description="Cross-platform CLI for Paxini PX-6AX GEN3 tactile sensors.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list available serial ports").set_defaults(
        func=_cmd_list
    )

    p_info = sub.add_parser("info", help="read firmware version (high-speed board)")
    p_info.add_argument("--port", required=True)
    p_info.add_argument("--baud", type=int, default=921600)
    p_info.set_defaults(func=_cmd_info)

    # Single sensor
    p_single = sub.add_parser("single", help="single-sensor (Serial Converter Board)")
    p_single_sub = p_single.add_subparsers(dest="single_cmd", required=True)

    p_cal = p_single_sub.add_parser("calibrate", help="trigger calibration")
    p_cal.add_argument("--port", required=True)
    p_cal.add_argument("--baud", type=int, default=921600)
    p_cal.set_defaults(func=_cmd_single_calibrate)

    p_force = p_single_sub.add_parser("force", help="read resultant force")
    p_force.add_argument("--port", required=True)
    p_force.add_argument("--baud", type=int, default=921600)
    p_force.add_argument("--watch", action="store_true", help="poll continuously")
    p_force.add_argument("--interval", type=float, default=0.1)
    p_force.add_argument("--calibrate", action="store_true", help="calibrate first")
    p_force.set_defaults(func=_cmd_single_force)

    p_dist = p_single_sub.add_parser("distributed", help="read distributed-force grid")
    p_dist.add_argument("--port", required=True)
    p_dist.add_argument("--baud", type=int, default=921600)
    p_dist.add_argument("--points", type=int, default=77)
    p_dist.add_argument("--calibrate", action="store_true")
    p_dist.set_defaults(func=_cmd_single_distributed)

    # Hand
    p_hand = sub.add_parser("hand", help="High-Speed Communication Board (28-module hand)")
    p_hand_sub = p_hand.add_subparsers(dest="hand_cmd", required=True)

    p_stream = p_hand_sub.add_parser("stream", help="continuous auto-push stream")
    p_stream.add_argument("--port", required=True)
    p_stream.add_argument("--baud", type=int, default=921600)
    p_stream.add_argument("--duration", type=float, default=0.0,
                          help="stop after N seconds (0 = forever)")
    p_stream.add_argument("--verbose", action="store_true")
    p_stream.set_defaults(func=_cmd_hand_stream)

    p_mod = p_hand_sub.add_parser("modules", help="one-shot read of all 28 modules")
    p_mod.add_argument("--port", required=True)
    p_mod.add_argument("--baud", type=int, default=921600)
    p_mod.set_defaults(func=_cmd_hand_modules)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PaxiniError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
