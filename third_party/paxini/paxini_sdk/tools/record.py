"""Dedicated CSV recorder for the Paxini High-Speed Communication Board.

Captures every auto-push frame's per-taxel data to disk. No terminal
spam, no rerun viewer, no smoke checks — just data capture.

Usage:
    python record.py --port COM7 --out runs/session1.csv --duration 60
    python record.py --port COM7 --out runs/session1.csv  # run until Ctrl+C
    python record.py --port COM7 --out runs/session1.csv --calibrate --native

CSV formats:
    default: vendor-compatible (replayable with paxini_to_rerun.py --csv)
    --native: cleaner column names + JSON metadata header, easier for pandas

Each row is flushed immediately so Ctrl+C never loses more than the last
frame.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

from paxini_sdk import HighSpeedHandBoard, list_serial_ports
from paxini_sdk import registers
from paxini_sdk.recording import CsvRecorder
from paxini_sdk import sensor_registry


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", required=True, help="COM port, e.g. COM7.")
    p.add_argument("--out", required=True, help="Output CSV path.")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--duration", type=float, default=None,
                   help="Stop after N seconds. Default: run until Ctrl+C.")
    p.add_argument("--calibrate", action="store_true",
                   help="Zero the baseline before recording.")
    p.add_argument("--native", action="store_true",
                   help="Wrapper-native CSV format instead of vendor-compatible.")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress the periodic 'frames so far' progress line.")
    args = p.parse_args()

    out_path = args.out
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    with HighSpeedHandBoard(args.port, baudrate=args.baud) as hand:
        firmware = hand.read_version()
        active = hand.read_active_modules()
        if not active:
            sys.exit("No active modules. Check the FPC cable.")
        cfg = hand.read_auto_push_config()

        # Try to resolve sensor variant for metadata (best-effort)
        try:
            n_pts = hand.read_distribution_point_count(active[0])
            variant = sensor_registry.find_by_point_count(n_pts)
            sensor_part = variant.vendor_part_code if variant else None
        except Exception:
            sensor_part = None

        if args.calibrate:
            print(f"Calibrating ...", flush=True)
            hand.calibrate()

        fmt = "native" if args.native else "vendor"
        print(f"Firmware:        {firmware}", flush=True)
        print(f"Active modules:  {[registers.MODULE_NAMES[m] for m in active]}", flush=True)
        print(f"Sensor part:     {sensor_part or '(unknown)'}", flush=True)
        print(f"Recording to:    {out_path}  ({fmt} format)", flush=True)
        if args.duration:
            print(f"Duration:        {args.duration:.1f} s", flush=True)
        else:
            print(f"Duration:        unlimited (Ctrl+C to stop)", flush=True)

        with CsvRecorder(out_path, cfg, format=fmt,
                          firmware=firmware,
                          sensor_part=sensor_part) as recorder:
            t0 = time.monotonic()
            last_progress = t0
            frames = 0
            try:
                for frame in hand.stream_auto_push(duration=args.duration):
                    recorder.write(frame)
                    frames += 1
                    now = time.monotonic()
                    if not args.quiet and now - last_progress >= 1.0:
                        elapsed = now - t0
                        rate = frames / elapsed if elapsed > 0 else 0
                        print(f"  t={elapsed:5.1f} s   frames={frames:5d}   "
                              f"rate={rate:5.1f} Hz", flush=True)
                        last_progress = now
            except KeyboardInterrupt:
                print("\n(Ctrl+C — flushing final row and exiting cleanly)", flush=True)

            elapsed = time.monotonic() - t0
            rate = frames / elapsed if elapsed > 0 else 0
            print(f"\nFinished: {frames} frames in {elapsed:.1f} s "
                  f"(~{rate:.0f} Hz)", flush=True)
            print(f"Wrote {recorder.rows_written} rows to {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
