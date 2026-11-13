"""Hardware smoke test for the Paxini **Serial Converter Board** (single sensor).

The Serial Converter Board carries one PX-6AX GEN3 sensor and speaks the
request/response "fin_master" protocol (section 3 of the Communication Board
protocol PDF). It has no auto-push mode and no point-count register, so you
must tell this tool which sensor is attached.

Usage:
    python -m paxini_sdk.tools.smoke_test_serial --port COM3 --sensor PXSR-STDDP03A --calibrate
    python -m paxini_sdk.tools.smoke_test_serial --port COM3 --n-points 135 --calibrate

This tool runs every transaction at the raw level: it prints the request
frame, the raw response bytes, and decodes the device status byte by name
(ERR_SUC / ERR_LEN / ...). It never aborts on a device error - it reports
and moves on - so a single run surfaces every problem at once.

Forces are reported in newtons (0.1 N / LSB, per vendor USB_UI.py).
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional, Tuple

from paxini_sdk import SingleSensorBoard, list_serial_ports, sensor_registry
from paxini_sdk import registers
from paxini_sdk.protocol import (
    FIN_FUNC_CALIBRATION,
    FIN_FUNC_FORCE,
    build_fin_request,
    fin_error_name,
    parse_fin_response,
)

_LSB_N = 0.1  # newtons per LSB (vendor USB_UI.py)


def pick_port(provided: Optional[str]) -> str:
    if provided:
        return provided
    ports = list(list_serial_ports())
    if not ports:
        sys.exit("No serial ports detected.")
    print("Available serial ports:")
    for p in ports:
        print(f"  {p}")
    sys.exit("Pass one with --port (e.g. --port COM3 or --port /dev/cu.usbserial-XXXX).")


def resolve_points(sensor: Optional[str], n_points: Optional[int]) -> int:
    if n_points is not None:
        return n_points
    if sensor is not None:
        variant = sensor_registry.find_by_part_code(sensor)
        if variant is None:
            known = [s.vendor_part_code for s in sensor_registry.list_sensors()]
            sys.exit(f"Unknown sensor part code {sensor!r}.\nKnown codes: {known}")
        print(f"[sensor] {variant.vendor_part_code} = {variant.sensor_model} "
              f"({variant.geometry}, {variant.n_points} points)")
        return variant.n_points
    sys.exit("Pass --sensor <PART-CODE> or --n-points <N>: the Serial Converter "
             "Board cannot report how many distributed-force points the sensor has.")


def raw_transaction(board: SingleSensorBoard, req: bytes, label: str):
    """Send `req`, print the raw response, parse it, and return the parsed
    FinResponse (or None on a transport/frame failure). Never raises on a
    non-zero device status - prints the named status instead."""
    print(f"  -> request : {req.hex().upper()}")
    try:
        raw = board.transport.fin_transaction(req, timeout=board.response_timeout)
    except Exception as e:
        print(f"  !! {label}: transport error: {e}")
        return None
    print(f"  <- response: {raw.hex().upper()}  ({len(raw)} bytes)")
    try:
        resp = parse_fin_response(raw)
    except Exception as e:
        print(f"  !! {label}: frame parse error: {e}")
        return None
    name = fin_error_name(resp.status)
    flag = "OK" if resp.status == 0 else "ERROR"
    print(f"  .. status = 0x{resp.status:02X} ({name})  [{flag}]"
          f"   data = {resp.data.hex().upper() or '(none)'}")
    return resp


def decode_resultant(data: bytes) -> Optional[Tuple[float, float, float]]:
    if len(data) < 3:
        return None
    fx = data[0] - 256 if data[0] >= 128 else data[0]
    fy = data[1] - 256 if data[1] >= 128 else data[1]
    fz = data[2]
    return (fx * _LSB_N, fy * _LSB_N, fz * _LSB_N)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--port", help="Serial port. If omitted, lists ports and exits.")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--sensor", default=None, help="Vendor part code, e.g. PXSR-STDDP03A.")
    p.add_argument("--n-points", type=int, default=None,
                   help="Explicit distributed-force point count (overrides --sensor).")
    p.add_argument("--device-id", type=lambda x: int(x, 0), default=0x01,
                   help="Slave address = module number + 1 (default 0x01).")
    p.add_argument("--calibrate", action="store_true",
                   help="Zero the baseline before reading.")
    p.add_argument("--calibrate-settle", type=float, default=0.8,
                   help="Seconds to wait after the calibration command (default 0.8).")
    p.add_argument("--duration", type=float, default=15.0)
    args = p.parse_args()

    port = pick_port(args.port)
    n_points = resolve_points(args.sensor, args.n_points)
    dev = args.device_id

    cal_req = build_fin_request(FIN_FUNC_CALIBRATION, registers.FIN_ADDR_CALIBRATION,
                                read=False, data=b"\x01", device_id=dev)
    res_req = build_fin_request(FIN_FUNC_FORCE, registers.FIN_ADDR_RESULTANT_FORCE,
                                read=True, data_len=3, device_id=dev)
    dist_req = build_fin_request(FIN_FUNC_FORCE, registers.FIN_ADDR_DISTRIBUTED_FORCE,
                                 read=True, data_len=n_points * 3, device_id=dev)

    print(f"\nOpening {port} @ {args.baud} baud (device-id 0x{dev:02X}) ...\n")

    with SingleSensorBoard(port, baudrate=args.baud, device_id=dev,
                           n_points=n_points) as board:

        # ---- [1] calibration ------------------------------------------------
        if args.calibrate:
            print("[1] calibration (write 0x01 -> 0x0003) ...")
            resp = raw_transaction(board, cal_req, "calibration")
            if resp is not None and resp.status == 0:
                print(f"    calibration acknowledged; settling {args.calibrate_settle:.1f}s ...")
            time.sleep(args.calibrate_settle)
        else:
            print("[1] calibration skipped (pass --calibrate to enable)")

        # ---- [2] resultant-force read --------------------------------------
        print("\n[2] resultant-force read (3 bytes @ 0x03F0) ...")
        resp = raw_transaction(board, res_req, "resultant")
        if resp is not None:
            forces = decode_resultant(resp.data)
            if forces:
                print(f"    decoded: Fx={forces[0]:+.1f} N  Fy={forces[1]:+.1f} N  "
                      f"Fz={forces[2]:+.1f} N")

        # ---- [3] distributed-force read ------------------------------------
        print(f"\n[3] distributed-force read ({n_points * 3} bytes @ 0x040E) ...")
        resp = raw_transaction(board, dist_req, "distributed")
        if resp is not None and len(resp.data) >= 3:
            npts = len(resp.data) // 3
            print(f"    got {npts} points (expected {n_points})")
            for i in (0, npts // 2, npts - 1):
                d = resp.data[i * 3:i * 3 + 3]
                f = decode_resultant(d)
                if f:
                    print(f"      point {i:3d}: Fx={f[0]:+.1f}  Fy={f[1]:+.1f}  Fz={f[2]:+.1f} N")

        # ---- [4] streaming loop --------------------------------------------
        print(f"\n[4] polling resultant + distributed force for {args.duration:.0f}s "
              f"(Ctrl+C to stop). Press the sensor to see it move ...")
        print("      'peakFz' is the largest Fz across all "
              f"{n_points} distributed taxels.")
        t0 = time.monotonic()
        reads = ok = 0
        last_print = 0.0
        try:
            while time.monotonic() - t0 < args.duration:
                try:
                    # resultant
                    raw = board.transport.fin_transaction(
                        res_req, timeout=board.response_timeout)
                    r = parse_fin_response(raw)
                    reads += 1
                    if r.status == 0:
                        ok += 1
                    # distributed: find the peak taxel Fz
                    rawd = board.transport.fin_transaction(
                        dist_req, timeout=board.response_timeout)
                    rd = parse_fin_response(rawd)
                    peak_fz = 0.0
                    peak_i = -1
                    for i in range(len(rd.data) // 3):
                        fz = rd.data[i * 3 + 2] * _LSB_N
                        if fz > peak_fz:
                            peak_fz, peak_i = fz, i
                    now = time.monotonic()
                    if now - last_print >= 0.2:
                        f = decode_resultant(r.data) or (0.0, 0.0, 0.0)
                        print(f"      t={now - t0:5.1f}s  "
                              f"resultant Fx={f[0]:+5.1f} Fy={f[1]:+5.1f} Fz={f[2]:+5.1f} N"
                              f"   |  peakFz={peak_fz:+5.1f} N @ taxel {peak_i}")
                        last_print = now
                except Exception as e:
                    print(f"      read error: {e}")
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n    stopped by user")
        elapsed = time.monotonic() - t0
        rate = reads / elapsed if elapsed else 0
        print(f"    {reads} resultant+distributed read pairs in {elapsed:.1f}s "
              f"(~{rate:.0f} Hz)")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
