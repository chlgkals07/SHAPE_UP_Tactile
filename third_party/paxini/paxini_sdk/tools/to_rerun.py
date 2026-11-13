"""Stream Paxini tactile data into rerun.io.

Two modes:

    Live capture from the High-Speed Communication Board:
        python paxini_to_rerun.py --port COM7

    Replay a Paxini host-app CSV recording:
        python paxini_to_rerun.py --csv data/2026-05-18-160858_paxini_app_v1.0.11_session2.csv

Optional flags:
    --calibrate     Zero the sensor baseline before streaming (live mode).
    --duration N    Stop after N seconds (live mode; default: run until Ctrl+C).
    --web-viewer    Serve a browser viewer instead of launching a native window.
    --spawn         Launch the rerun viewer process. Default behaviour: use
                    a running viewer if you've started one, otherwise spawn.
    --memory-limit MB  Pass through to rerun (default: 1024).

What gets logged to rerun:

    sensor/                      static / timeless metadata
        firmware                 ASCII string
        active_modules           text list
    sensor/{module_name}/        per-active-module time-series tree
        resultant/fx             scalar (N), signed
        resultant/fy             scalar (N), signed
        resultant/fz             scalar (N), unsigned
        distributed              3D point cloud, colors map Fz to a blue ramp
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

try:
    import rerun as rr
except ImportError:
    sys.exit(
        "rerun-sdk is not installed. Install it with:\n"
        "    pip install rerun-sdk\n"
        "(needs Python 3.9+; on Windows see https://rerun.io/docs/getting-started/installing-viewer)"
    )

from paxini_sdk import HighSpeedHandBoard, list_serial_ports
from paxini_sdk import registers
from paxini_sdk import sensor_registry


# ---- Coordinate-asset loading ---------------------------------------------


def resolve_sensor_variant(
    point_count: Optional[int] = None,
    geometry_hint: Optional[str] = None,
    sensor_part_override: Optional[str] = None,
):
    """Pick a SensorVariant from the registry. Manual override wins, otherwise
    look up by point count (geometry hint disambiguates collisions if any).
    Returns the SensorVariant; raises LookupError on no match.
    """
    if sensor_part_override:
        v = sensor_registry.find_by_part_code(sensor_part_override)
        if v is None:
            raise LookupError(
                f"Unknown sensor part code: {sensor_part_override!r}. "
                f"Available: {[s.vendor_part_code for s in sensor_registry.list_sensors()]}"
            )
        return v
    if point_count is not None:
        v = sensor_registry.find_by_point_count(point_count, geometry_hint=geometry_hint)
        if v is not None:
            return v
        raise LookupError(
            f"No bundled sensor variant matches point count {point_count}. "
            f"Bundled counts: {sorted({s.n_points for s in sensor_registry.list_sensors()})}"
        )
    raise LookupError("Must pass either point_count or sensor_part_override")


def load_sensor_points(variant) -> List[Tuple[float, float, float]]:
    """Load the per-point (x_mm, y_mm, z_mm) tuples for a SensorVariant."""
    return sensor_registry.load_points(variant)


# ---- Rerun helpers --------------------------------------------------------


def _fz_color(fz_lsb: int, fz_full: int = 30) -> Tuple[int, int, int]:
    """Map an Fz LSB count to an RGB blue ramp.

    fz_full sets the upper end (default 30 LSB = 3.0 N). Anything ≥ fz_full
    saturates to the darkest blue. Zero / negative reads map to a near-neutral
    light fill so unloaded points stay visible.
    """
    if fz_lsb <= 0:
        return (210, 215, 220)  # Light neutral
    t = min(1.0, fz_lsb / max(1, fz_full))
    # blue 50 (230, 241, 251) → blue 600 (24, 95, 165)
    r = round(230 + (24 - 230) * t)
    g = round(241 + (95 - 241) * t)
    b = round(251 + (165 - 251) * t)
    return (r, g, b)


def log_static_metadata(firmware: Optional[str], active_modules: List[str],
                        coordinates: Dict[str, List[Tuple[float, float, float]]]) -> None:
    """Log timeless metadata + the static point positions."""
    if firmware:
        rr.log("sensor/firmware", rr.TextDocument(firmware), static=True)
    rr.log(
        "sensor/active_modules",
        rr.TextDocument("\n".join(active_modules)),
        static=True,
    )
    # Keep each module's geometry visible before the first force update.
    for name, coord_mm in coordinates.items():
        rr.log(
            f"sensor/{name.lower().replace('-', '_')}/anatomy",
            rr.Points3D(
                positions=coord_mm,
                colors=[(210, 215, 220)] * len(coord_mm),
                radii=0.4,
            ),
            static=True,
        )


def log_resultant(module_name: str, fx_n: float, fy_n: float, fz_n: float) -> None:
    base = f"sensor/{module_name.lower().replace('-', '_')}/resultant"
    rr.log(f"{base}/fx", rr.Scalars(fx_n))
    rr.log(f"{base}/fy", rr.Scalars(fy_n))
    rr.log(f"{base}/fz", rr.Scalars(fz_n))


def log_distributed(module_name: str,
                    coord_mm: List[Tuple[float, float, float]],
                    fz_lsb_per_point: List[int]) -> None:
    """Log a distributed grid as colored 3D points."""
    path = f"sensor/{module_name.lower().replace('-', '_')}/distributed"
    if len(fz_lsb_per_point) != len(coord_mm):
        n = min(len(fz_lsb_per_point), len(coord_mm))
        positions = coord_mm[:n]
        fz_vals = fz_lsb_per_point[:n]
    else:
        positions = coord_mm
        fz_vals = fz_lsb_per_point
    colors = [_fz_color(v) for v in fz_vals]
    radii = [0.4 + min(1.5, max(0.0, v * 0.05)) for v in fz_vals]
    rr.log(path, rr.Points3D(positions=positions, colors=colors, radii=radii))


# ---- Live capture ---------------------------------------------------------


def run_live(port: str, baud: int, duration: Optional[float],
             calibrate: bool, sensor_part_override: Optional[str],
             record_path: Optional[str] = None,
             native_format: bool = False) -> None:
    with HighSpeedHandBoard(port, baudrate=baud) as hand:
        firmware = hand.read_version()
        active = hand.read_active_modules()
        active_names = [registers.MODULE_NAMES[m] for m in active]
        print(f"Firmware: {firmware!r}")
        print(f"Active modules: {active_names}")
        if not active:
            sys.exit("No active modules. Check FPC cable orientation.")

        coordinates = {}
        variants = {}
        for module, name in zip(active, active_names):
            n_pts = hand.read_distribution_point_count(module)
            variant = resolve_sensor_variant(
                point_count=n_pts,
                sensor_part_override=sensor_part_override,
            )
            if variant.n_points != n_pts:
                raise ValueError(
                    f"{name}: {n_pts} points reported, but "
                    f"{variant.vendor_part_code} has {variant.n_points}. "
                    "Omit --sensor-part to detect each module automatically."
                )
            coordinates[name] = load_sensor_points(variant)
            variants[name] = variant
            print(f"Resolved sensor [{name}]: {variant.vendor_part_code} "
                  f"({variant.sensor_model}, {variant.geometry}, {n_pts} pts)")

        if calibrate:
            print("Calibrating ...")
            hand.calibrate()
            print("Calibration successful.")

        log_static_metadata(firmware, active_names, coordinates)
        # Sensor coordinates are local to each sensor, so use separate views.
        import rerun.blueprint as rrb
        rr.send_blueprint(rrb.Blueprint(rrb.Horizontal(*[
            rrb.Vertical(
                rrb.Spatial3DView(
                    name=name,
                    origin=f"sensor/{name.lower().replace('-', '_')}",
                ),
                rrb.TimeSeriesView(
                    name=f"{name} force (N)",
                    origin=f"sensor/{name.lower().replace('-', '_')}/resultant",
                ),
            ) for name in active_names
        ])))

        # Optional CSV recorder
        recorder = None
        if record_path:
            from paxini_sdk.recording import CsvRecorder
            cfg = hand.read_auto_push_config()
            fmt = "native" if native_format else "vendor"
            recorder = CsvRecorder(record_path, cfg, format=fmt,
                                    firmware=firmware,
                                    sensor_part=(next(iter(variants.values())).vendor_part_code
                                                 if len(variants) == 1 else None))
            print(f"Recording to {record_path} ({fmt} format)")

        # Drive rerun's timeline from monotonic seconds since stream start.
        rr.set_time("session_s", duration=0.0)
        t0 = time.monotonic()
        frames = 0
        try:
          for frame in hand.stream_auto_push(duration=duration):
            t_now = time.monotonic() - t0
            rr.set_time("session_s", duration=t_now)
            if recorder is not None:
                recorder.write(frame)
            forces_n = frame.resultant_forces_newtons
            distributed = frame.distributed_forces
            for name, (fx, fy, fz) in forces_n.items():
                log_resultant(name, fx, fy, fz)
            for name, pts in distributed.items():
                fz_per_point = [p[2] for p in pts]
                log_distributed(name, coordinates[name], fz_per_point)
            frames += 1
        finally:
          if recorder is not None:
              recorder.close()
        elapsed = time.monotonic() - t0
        rate = frames / elapsed if elapsed > 0 else 0.0
        print(f"Streamed {frames} frames in {elapsed:.1f} s (~{rate:.0f} Hz).")
        if recorder is not None:
            print(f"Recorded {recorder.rows_written} rows to {record_path}")


# ---- CSV replay ----------------------------------------------------------


def _parse_paxini_csv_header(header: List[str]) -> Tuple[List[Tuple[int, int]], int]:
    """Parse the Paxini host-app CSV header to find resultant + distributed columns.

    Returns (resultant_col_triples, n_distributed_points). The resultant col
    triples is a list of (slot_id, base_column_index) for each "M-S-1x1-X"
    triplet in the header. The distributed point count is read from the
    "M-S-NxN-X[i]" max index.
    """
    import re
    # Find 1x1 triplets: M-S-1x1-{X,Y,Z}
    res_triplets: Dict[Tuple[int, int], List[int]] = {}
    max_nxn_idx = -1
    for i, col in enumerate(header):
        m = re.match(r"(\d+)-(\d+)-1x1-([XYZ])$", col)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            triplet_idx = "XYZ".index(m.group(3))
            res_triplets.setdefault(key, [None, None, None])[triplet_idx] = i
            continue
        m = re.match(r"(\d+)-(\d+)-NxN-([XYZ])\[(\d+)\]$", col)
        if m:
            max_nxn_idx = max(max_nxn_idx, int(m.group(4)))
    triples_list = []
    for key, cols in res_triplets.items():
        if None in cols:
            continue
        triples_list.append((key, tuple(cols)))
    return triples_list, max_nxn_idx + 1


def _parse_csv_timestamp(s: str) -> float:
    """Parse 'HH:MM:SS.ms' into seconds-of-day."""
    h, m, rest = s.split(":")
    sec, ms = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000.0


def run_csv_replay(csv_path: Path, sensor_part: str) -> None:
    # CSV mode has no board to query, so the override (or the default) wins
    variant = resolve_sensor_variant(sensor_part_override=sensor_part)
    coord = load_sensor_points(variant)
    print(f"Using sensor coordinates: {variant.vendor_part_code} "
          f"({variant.sensor_model}, {variant.n_points} pts)")
    with csv_path.open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    print(f"Loaded {len(rows)} rows from {csv_path.name} ({len(header)} columns).")
    triples, n_pts = _parse_paxini_csv_header(header)
    print(f"Parsed header: {len(triples)} resultant-force columns, {n_pts} NxN points.")
    if len(triples) == 0:
        sys.exit("No 1x1 resultant-force columns in this CSV; cannot replay.")

    # Map host-app "M-S" slot pairs to module names. The host app uses
    # finger=0..5, module=0..3 (proximal,middle,tip,nail) per the protocol's
    # bit ordering. We can't fully invert that to MODULE_NAMES indices without
    # vendor docs on the exact (finger, module) → module_index mapping, but
    # for one-active-fingertip recordings (which is the case in our captures
    # so far), the slot label can be passed through.
    SLOT_TO_NAME = {
        # Index-Tip is what we've observed
        (1, 2): "Index-Tip",
        (0, 2): "Thumb-Tip",
        (2, 2): "Middle-Tip",
        (3, 2): "Ring-Tip",
        (4, 2): "Little-Tip",
    }

    # Static metadata first
    inferred_modules = [SLOT_TO_NAME.get(t[0], f"slot_{t[0][0]}_{t[0][1]}") for t in triples]
    log_static_metadata(
        firmware=f"(replay of {csv_path.name})",
        active_modules=inferred_modules,
        coordinates={name: coord for name in inferred_modules},
    )

    t0 = _parse_csv_timestamp(rows[0][0])
    for row in rows:
        t = _parse_csv_timestamp(row[0]) - t0
        rr.set_time("session_s", duration=t)
        for (slot, (cx, cy, cz)), name in zip(triples, inferred_modules):
            fx = int(row[cx]) * 0.1
            fy = int(row[cy]) * 0.1
            fz = int(row[cz]) * 0.1
            log_resultant(name, fx, fy, fz)
        # Distributed grid: columns past the resultant block, in groups of 3
        # for n_pts points. Assume one module's worth (the host app only
        # records the active modules).
        if n_pts > 0:
            base = 1 + len(triples) * 3
            fz_per_point: List[int] = []
            for i in range(n_pts):
                z_col = base + i * 3 + 2
                if z_col < len(row):
                    fz_per_point.append(int(row[z_col]))
                else:
                    fz_per_point.append(0)
            log_distributed(inferred_modules[0], coord, fz_per_point)
    print(f"Replay complete: {len(rows)} frames logged.")


# ---- CLI -----------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="COM port for live capture (e.g. COM7).")
    src.add_argument("--csv", type=Path, help="Replay a Paxini app CSV recording.")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--duration", type=float, default=None,
                   help="Live mode: stop after N seconds (default: until Ctrl+C).")
    p.add_argument("--calibrate", action="store_true",
                   help="Live mode: zero the baseline before streaming.")
    p.add_argument("--sensor-part", default=None,
                   help="Force a specific coordinate variant (e.g. PXSR-STDDP03F). "
                        "Default: auto-detect from the board\u2019s point count in live mode, "
                        "fall back to PXSR-STDDP03G in CSV mode.")
    viewer = p.add_mutually_exclusive_group()
    viewer.add_argument("--spawn", action="store_true",
                   help="(default behaviour) Launch a fresh rerun viewer. "
                        "Kept as an explicit flag for clarity in docs.")
    viewer.add_argument("--connect", action="store_true",
                   help="Attach to a running rerun viewer instead of spawning a new one. "
                        "Useful if you've already opened the viewer manually.")
    viewer.add_argument("--web-viewer", action="store_true",
                        help="Serve a browser viewer on port 9090; open the printed URL "
                             "in Windows Chrome/Edge to bypass WSL graphics drivers.")
    p.add_argument("--memory-limit", default="1024MB",
                   help="Memory limit for the viewer (default 1024MB).")
    p.add_argument("--record", metavar="PATH", default=None,
                   help="Also write every streamed frame's per-taxel data to PATH (CSV). "
                        "Live mode only. Default format is vendor-compatible "
                        "(replayable through --csv); pass --native for the wrapper-native format.")
    p.add_argument("--native", action="store_true",
                   help="With --record: use wrapper-native column scheme.")
    args = p.parse_args()

    if args.web_viewer and not all(
        hasattr(rr, name) for name in ("serve_grpc", "serve_web_viewer")
    ):
        p.error("--web-viewer requires a newer rerun-sdk: pip install -U '.[viz]'")
    if args.csv and not args.csv.exists():
        p.error(f"CSV not found: {args.csv}")

    rr.init("paxini_tactile", spawn=False)
    if args.web_viewer:
        uri = rr.serve_grpc(grpc_port=9876, server_memory_limit=args.memory_limit)
        rr.serve_web_viewer(web_port=9090, open_browser=False)
        query = urlencode({"url": uri})
        print(f"Open in Windows Chrome/Edge: http://localhost:9090/?{query}", flush=True)
    elif args.connect:
        try:
            rr.connect_grpc()
        except Exception as e:
            print(f"Warning: --connect failed ({e}); spawning viewer instead",
                  file=sys.stderr)
            rr.spawn(memory_limit=args.memory_limit)
    else:
        rr.spawn(memory_limit=args.memory_limit)

    try:
        if args.csv:
            run_csv_replay(args.csv, args.sensor_part or 'PXSR-STDDP03G')
        else:
            run_live(args.port, args.baud, args.duration, args.calibrate, args.sensor_part, record_path=args.record, native_format=args.native)
        if args.web_viewer:
            print("Web viewer remains available. Press Ctrl+C to close.", flush=True)
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nViewer stopped.")
    finally:
        rr.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
