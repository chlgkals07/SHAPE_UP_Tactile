"""Hardware smoke test for Paxini PXSR-STDOTO4B + DP-S2015-Elite.

Usage:
    python smoke_test.py --port COM7 --duration 25 --calibrate
    python smoke_test.py --port COM7 --duration 25 --record run.csv

Steps:
  1. Read firmware version.
  2. Read active-modules bitmap (0x0010-0x0013), decode to module names.
  3. Read data-type combination (0x0016).
  4. Read distributed-force point counts for the active modules.
  4b. Optionally calibrate (--calibrate).
  5. One-shot read of each active module's resultant force.
  6. Stream auto-push for --duration seconds; print resultant force at 5 Hz.
     Optionally also write per-taxel CSV (--record file.csv [--native]).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

from paxini_sdk import HighSpeedHandBoard, list_serial_ports
from paxini_sdk import registers


def pick_port(provided: Optional[str]) -> str:
    if provided:
        return provided
    ports = list(list_serial_ports())
    if not ports:
        print("No serial ports detected.", file=sys.stderr)
        sys.exit(1)
    print("Available serial ports:")
    for p in ports:
        print(f"  {p}")
    sys.exit("Pass one with --port (e.g. --port COM7).")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", help="COM port (e.g. COM7). If omitted, lists ports.")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--duration", type=float, default=25.0)
    p.add_argument("--module", default=None,
                   help="Module name to focus on in the stream printout.")
    p.add_argument("--calibrate", action="store_true",
                   help="Zero the baseline before streaming.")
    p.add_argument("--record", metavar="PATH", default=None,
                   help="Also write every streamed frame's per-taxel data to "
                        "PATH as CSV (vendor-compatible by default).")
    p.add_argument("--native", action="store_true",
                   help="With --record: use wrapper-native column scheme + "
                        "JSON metadata header.")
    args = p.parse_args()

    port = pick_port(args.port)
    print(f"Opening {port} @ {args.baud} baud ...")

    with HighSpeedHandBoard(port, baudrate=args.baud) as hand:
        try:
            ver = hand.read_version()
            print(f"[1] firmware version: {ver!r}")
        except Exception as e:
            print(f"[1] FAILED reading version: {e}")
            return 1

        try:
            active = hand.read_active_modules()
            print(f"[2] active modules ({len(active)}): "
                  f"{[registers.MODULE_NAMES[m] for m in active]}")
            if not active:
                print("    No active modules. Check FPC cabling.")
                return 1
        except Exception as e:
            print(f"[2] FAILED reading active modules: {e}")
            return 1

        try:
            dt = hand.read_data_type()
            bits = []
            if dt & registers.DATA_TYPE_RESULTANT:
                bits.append("resultant")
            if dt & registers.DATA_TYPE_DISTRIBUTED:
                bits.append("distributed")
            print(f"[3] data-type 0x0016 = 0x{dt:02X} ({', '.join(bits) or 'none'})")
        except Exception as e:
            print(f"[3] FAILED reading data-type: {e}")
            return 1

        try:
            for m in active:
                pc = hand.read_distribution_point_count(m)
                print(f"[4] {registers.MODULE_NAMES[m]} distributed-force points: {pc}")
        except Exception as e:
            print(f"[4] FAILED reading point counts: {e}")

        if args.calibrate:
            try:
                print("[4b] calibrating (zeroing baseline) ...")
                hand.calibrate()
                print("      calibration successful")
            except Exception as e:
                print(f"[4b] FAILED to calibrate: {e}")

        try:
            forces = hand.read_resultant_forces_newtons()
            print(f"[5] one-shot resultant forces (N):")
            for name, (fx, fy, fz) in forces.items():
                print(f"      {name:<16} Fx={fx:+5.1f}  Fy={fy:+5.1f}  Fz={fz:+5.1f}")
        except Exception as e:
            print(f"[5] FAILED one-shot read: {e}")

        focus = args.module or registers.MODULE_NAMES[active[0]]
        print(f"[6] streaming auto-push for {args.duration:.1f} s, focus = {focus} ...")

        recorder = None
        if args.record:
            from paxini_sdk.recording import CsvRecorder
            cfg = hand.read_auto_push_config()
            fmt = "native" if args.native else "vendor"
            recorder = CsvRecorder(args.record, cfg, format=fmt,
                                    firmware=ver, sensor_part=None)
            print(f"      recording per-taxel data to {args.record} ({fmt} format)")

        last_print = 0.0
        frames = 0
        try:
            for frame in hand.stream_auto_push(duration=args.duration):
                frames += 1
                if recorder is not None:
                    recorder.write(frame)
                named = frame.resultant_forces_newtons
                if focus not in named:
                    if frames == 1 and named:
                        focus = next(iter(named))
                    else:
                        continue
                now = time.monotonic()
                if now - last_print >= 0.2:
                    fx, fy, fz = named[focus]
                    print(f"      t={now:.2f}  {focus}: "
                          f"Fx={fx:+5.1f}  Fy={fy:+5.1f}  Fz={fz:+5.1f}")
                    last_print = now
            rate = frames / args.duration if args.duration else 0
            print(f"      received {frames} frames (~{rate:.0f} Hz over {args.duration:.1f} s)")
            if recorder is not None:
                print(f"      wrote {recorder.rows_written} rows to {args.record}")
        except Exception as e:
            print(f"[6] FAILED streaming: {e}")
            return 1
        finally:
            if recorder is not None:
                recorder.close()

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
