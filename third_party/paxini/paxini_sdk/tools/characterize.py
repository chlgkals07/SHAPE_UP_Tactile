"""Sensor characterization: noise floor, drift, and load response.

Three capture modes + one offline analysis mode. Each capture mode writes
a vendor-compatible CSV using :class:`CsvRecorder` and, when numpy /
matplotlib are available, a summary JSON + PNG plot alongside it.

::

    paxini-characterize noise    --port COM7 --duration 60   --out runs/noise.csv
    paxini-characterize drift    --port COM7 --duration 1800 --out runs/drift.csv
    paxini-characterize response --port COM7 --out runs/response.csv
    paxini-characterize report runs/noise.csv     # re-run analysis on an existing recording

The analysis paths also work on Paxini host-app CSVs (same column scheme),
so you can use this tool to inspect old recordings without re-collecting
data.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# Optional analysis dependencies
try:
    import numpy as np
except ImportError:
    np = None

try:
    import matplotlib
    matplotlib.use("Agg")  # no display required
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

from paxini_sdk import HighSpeedHandBoard, registers
from paxini_sdk.recording import CsvRecorder


# =============================================================================
# Shared helpers
# =============================================================================


def _check_analysis_deps() -> None:
    if np is None or plt is None:
        sys.exit(
            "Characterization analysis needs numpy + matplotlib.\n"
            "Install with: pip install paxini-sdk[char]\n"
            "or: pip install numpy matplotlib"
        )


def _parse_paxini_csv(path: Path):
    """Read a Paxini-format CSV into (timestamps_s, resultant_lsb, dist_lsb_grid).

    timestamps_s: 1D float seconds, monotonic from row 0
    resultant_lsb: (N, 3) int — Fx, Fy, Fz per row (LSB units)
    dist_lsb_grid: (N, P, 3) int — Fx, Fy, Fz per taxel per row, or None if no NxN
    """
    _check_analysis_deps()
    with path.open() as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    if not rows:
        sys.exit(f"No data rows in {path}")

    # Find resultant + distributed columns
    res_cols = []   # (slot, (cx, cy, cz))
    nxn_max = -1
    nxn_cols: Dict[Tuple[int, int], Dict[str, Dict[int, int]]] = {}
    for i, col in enumerate(header):
        m = re.match(r"(\d+)-(\d+)-1x1-([XYZ])$", col)
        if m:
            res_cols.append((int(m.group(1)), int(m.group(2)), m.group(3), i))
            continue
        m = re.match(r"(\d+)-(\d+)-NxN-([XYZ])\[(\d+)\]$", col)
        if m:
            slot = (int(m.group(1)), int(m.group(2)))
            axis = m.group(3)
            pt = int(m.group(4))
            nxn_max = max(nxn_max, pt)
            nxn_cols.setdefault(slot, {}).setdefault(axis, {})[pt] = i

    if not res_cols:
        sys.exit(f"No 1x1 resultant columns in {path}")

    # Take the first slot's resultant; assume one active module for analysis
    by_slot: Dict[Tuple[int, int], Dict[str, int]] = {}
    for slot1, slot2, axis, col_idx in res_cols:
        by_slot.setdefault((slot1, slot2), {})[axis] = col_idx
    slot, axis_cols = next(iter(by_slot.items()))

    # Parse timestamps as seconds
    def ts_to_sec(s: str) -> float:
        h, m, rest = s.split(":")
        sec, ms = rest.split(".")
        return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000.0

    t = np.array([ts_to_sec(r[0]) for r in rows], dtype=np.float64)
    t -= t[0]
    resultant = np.array(
        [[int(r[axis_cols["X"]]), int(r[axis_cols["Y"]]), int(r[axis_cols["Z"]])] for r in rows],
        dtype=np.int32,
    )

    grid = None
    if slot in nxn_cols and nxn_max >= 0:
        P = nxn_max + 1
        grid = np.zeros((len(rows), P, 3), dtype=np.int32)
        x_idx = nxn_cols[slot].get("X", {})
        y_idx = nxn_cols[slot].get("Y", {})
        z_idx = nxn_cols[slot].get("Z", {})
        for ri, r in enumerate(rows):
            for p in range(P):
                if p in x_idx:
                    grid[ri, p, 0] = int(r[x_idx[p]])
                if p in y_idx:
                    grid[ri, p, 1] = int(r[y_idx[p]])
                if p in z_idx:
                    grid[ri, p, 2] = int(r[z_idx[p]])
    return t, resultant, grid


@contextmanager
def _open_board(port: str, baud: int, *, calibrate: bool):
    with HighSpeedHandBoard(port, baudrate=baud) as hand:
        firmware = hand.read_version()
        active = hand.read_active_modules()
        if not active:
            sys.exit("No active modules. Check the FPC cable.")
        cfg = hand.read_auto_push_config()
        sensor_part = None
        try:
            from paxini_sdk import sensor_registry
            n_pts = hand.read_distribution_point_count(active[0])
            v = sensor_registry.find_by_point_count(n_pts)
            if v:
                sensor_part = v.vendor_part_code
        except Exception:
            pass

        print(f"Firmware:        {firmware}", flush=True)
        print(f"Active modules:  {[registers.MODULE_NAMES[m] for m in active]}", flush=True)
        print(f"Sensor part:     {sensor_part or '(unknown)'}", flush=True)

        if calibrate:
            print("Calibrating ...", flush=True)
            hand.calibrate()
            print("Calibration successful.", flush=True)

        yield hand, cfg, firmware, sensor_part


def _record(hand, cfg, out_path: Path, firmware: Optional[str],
            sensor_part: Optional[str], duration: float) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with CsvRecorder(out_path, cfg, format="vendor",
                      firmware=firmware, sensor_part=sensor_part) as rec:
        t0 = time.monotonic()
        last_log = t0
        for frame in hand.stream_auto_push(duration=duration):
            rec.write(frame)
            now = time.monotonic()
            if now - last_log >= 2.0:
                elapsed = now - t0
                rate = rec.rows_written / max(elapsed, 1e-6)
                remain = max(0.0, duration - elapsed)
                print(f"  t={elapsed:6.1f} s  frames={rec.rows_written:6d}  "
                      f"rate={rate:5.1f} Hz  remaining={remain:5.1f}s",
                      flush=True)
                last_log = now
        return rec.rows_written


# =============================================================================
# Analysis: noise
# =============================================================================


def analyze_noise(csv_path: Path) -> dict:
    _check_analysis_deps()
    t, res, grid = _parse_paxini_csv(csv_path)
    n = len(t)
    duration = float(t[-1]) if n > 1 else 0.0
    rate = n / duration if duration > 0 else 0.0

    # Resultant statistics in LSB and newtons
    res_n = res * 0.1
    summary = {
        "csv": csv_path.name,
        "n_frames": int(n),
        "duration_s": round(duration, 3),
        "rate_hz": round(rate, 2),
        "resultant_lsb": {
            "fx": {"mean": float(np.mean(res[:, 0])), "stdev": float(np.std(res[:, 0])),
                    "min": int(np.min(res[:, 0])), "max": int(np.max(res[:, 0])),
                    "p99": float(np.percentile(np.abs(res[:, 0]), 99))},
            "fy": {"mean": float(np.mean(res[:, 1])), "stdev": float(np.std(res[:, 1])),
                    "min": int(np.min(res[:, 1])), "max": int(np.max(res[:, 1])),
                    "p99": float(np.percentile(np.abs(res[:, 1]), 99))},
            "fz": {"mean": float(np.mean(res[:, 2])), "stdev": float(np.std(res[:, 2])),
                    "min": int(np.min(res[:, 2])), "max": int(np.max(res[:, 2])),
                    "p99": float(np.percentile(np.abs(res[:, 2]), 99))},
        },
        "resultant_newtons_stdev": {
            "fx": round(float(np.std(res_n[:, 0])), 3),
            "fy": round(float(np.std(res_n[:, 1])), 3),
            "fz": round(float(np.std(res_n[:, 2])), 3),
        },
    }
    if grid is not None:
        # Per-taxel stdev across time, then summarized
        per_taxel_std = np.std(grid, axis=0)  # shape (P, 3)
        summary["per_taxel_stdev_lsb_max"] = {
            "fx": float(np.max(per_taxel_std[:, 0])),
            "fy": float(np.max(per_taxel_std[:, 1])),
            "fz": float(np.max(per_taxel_std[:, 2])),
        }
        summary["distributed_n_taxels"] = int(grid.shape[1])

    # Plot
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    axes[0].plot(t, res_n[:, 0], label="Fx (N)", linewidth=0.8)
    axes[0].plot(t, res_n[:, 1], label="Fy (N)", linewidth=0.8)
    axes[0].plot(t, res_n[:, 2], label="Fz (N)", linewidth=0.8)
    axes[0].axhline(0, color="grey", linewidth=0.4)
    axes[0].set_ylabel("Force (N)")
    axes[0].set_title(f"Noise — {csv_path.name}  ({n} frames over {duration:.1f}s)")
    axes[0].legend(loc="upper right", fontsize=9)
    axes[0].grid(alpha=0.3)

    axes[1].hist(res_n[:, 0], bins=40, alpha=0.5, label="Fx")
    axes[1].hist(res_n[:, 1], bins=40, alpha=0.5, label="Fy")
    axes[1].hist(res_n[:, 2], bins=40, alpha=0.5, label="Fz")
    axes[1].set_xlabel("Force (N)")
    axes[1].set_ylabel("Frames")
    axes[1].set_title("Resultant-force distribution")
    axes[1].legend(loc="upper right", fontsize=9)
    axes[1].grid(alpha=0.3)
    plt.tight_layout()
    plot_path = csv_path.with_suffix(".noise.png")
    fig.savefig(plot_path, dpi=110)
    plt.close(fig)
    summary["plot"] = plot_path.name

    return summary


# =============================================================================
# Analysis: drift
# =============================================================================


def analyze_drift(csv_path: Path, bin_seconds: float = 10.0) -> dict:
    _check_analysis_deps()
    t, res, _ = _parse_paxini_csv(csv_path)
    n = len(t)
    duration = float(t[-1]) if n > 1 else 0.0
    res_n = res * 0.1

    # Bin into windows of bin_seconds and take mean per bin
    bins = np.arange(0, duration + bin_seconds, bin_seconds)
    bin_idx = np.digitize(t, bins) - 1
    bin_means = np.full((len(bins) - 1, 3), np.nan, dtype=np.float64)
    for b in range(len(bins) - 1):
        mask = bin_idx == b
        if mask.any():
            bin_means[b] = res_n[mask].mean(axis=0)
    bin_centers = 0.5 * (bins[:-1] + bins[1:])

    # Drift rate: linear fit across the whole recording, per axis
    drift_rates: Dict[str, float] = {}  # N per second
    for axis_i, axis_name in enumerate(("fx", "fy", "fz")):
        if n >= 2:
            slope, _ = np.polyfit(t, res_n[:, axis_i], 1)
            drift_rates[axis_name] = float(slope)
        else:
            drift_rates[axis_name] = 0.0

    summary = {
        "csv": csv_path.name,
        "n_frames": int(n),
        "duration_s": round(duration, 3),
        "drift_rate_N_per_min": {
            k: round(v * 60.0, 4) for k, v in drift_rates.items()
        },
        "bin_seconds": bin_seconds,
        "n_bins": int((~np.isnan(bin_means[:, 0])).sum()),
    }

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    for axis_i, (axis_name, label) in enumerate(zip(("fx", "fy", "fz"), ("Fx", "Fy", "Fz"))):
        axes[axis_i].plot(t, res_n[:, axis_i], color="lightgray", linewidth=0.4,
                          label="raw")
        axes[axis_i].plot(bin_centers, bin_means[:, axis_i],
                          marker="o", markersize=3, linewidth=1.2,
                          label=f"{bin_seconds:.0f}-s mean")
        slope = drift_rates[axis_name]
        if n >= 2:
            fit = np.polyval([slope, res_n[:, axis_i].mean() - slope * t.mean()], t)
            axes[axis_i].plot(t, fit, "r--", linewidth=0.8,
                              label=f"trend: {slope * 60:.4f} N/min")
        axes[axis_i].set_ylabel(f"{label} (N)")
        axes[axis_i].legend(loc="upper right", fontsize=8)
        axes[axis_i].grid(alpha=0.3)
    axes[-1].set_xlabel("Time (s)")
    axes[0].set_title(f"Drift — {csv_path.name}  ({duration/60:.1f} min)")
    plt.tight_layout()
    plot_path = csv_path.with_suffix(".drift.png")
    fig.savefig(plot_path, dpi=110)
    plt.close(fig)
    summary["plot"] = plot_path.name
    return summary


# =============================================================================
# Analysis: response
# =============================================================================


def analyze_response(csv_path: Path, segments_path: Optional[Path] = None) -> dict:
    """Analyze a response recording. ``segments_path`` is an optional JSON sidecar
    describing each press: [{"weight_g": 100, "t_start": 5.0, "t_end": 10.0}, ...]."""
    _check_analysis_deps()
    t, res, _ = _parse_paxini_csv(csv_path)
    res_n = res * 0.1

    segments: List[dict] = []
    if segments_path and segments_path.exists():
        segments = json.loads(segments_path.read_text())

    summary = {
        "csv": csv_path.name,
        "n_segments": len(segments),
    }

    if not segments:
        # No segment annotations — just plot the timeline.
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(t, res_n[:, 0], label="Fx", linewidth=0.7)
        ax.plot(t, res_n[:, 1], label="Fy", linewidth=0.7)
        ax.plot(t, res_n[:, 2], label="Fz", linewidth=0.9)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Force (N)")
        ax.set_title(f"Response — {csv_path.name} (no segment annotations)")
        ax.legend(loc="upper right")
        ax.grid(alpha=0.3)
        plt.tight_layout()
        plot_path = csv_path.with_suffix(".response.png")
        fig.savefig(plot_path, dpi=110)
        plt.close(fig)
        summary["plot"] = plot_path.name
        summary["note"] = ("No segments JSON given; only the raw force timeline "
                            "was plotted. Re-run with annotations to fit a response curve.")
        return summary

    # Per-segment mean Fz, plus a known_weight vs Fz scatter + linear fit
    measured_fz = []
    known_n = []
    for seg in segments:
        mask = (t >= seg["t_start"]) & (t < seg["t_end"])
        if mask.sum() == 0:
            continue
        fz_mean = float(np.mean(res_n[mask, 2]))
        measured_fz.append(fz_mean)
        known_n.append(seg["weight_g"] * 9.81e-3)  # grams → N

    known_n_arr = np.array(known_n)
    measured_arr = np.array(measured_fz)
    summary["segments"] = [
        {"known_N": round(k, 3), "measured_Fz_N": round(m, 3)}
        for k, m in zip(known_n, measured_fz)
    ]
    if len(known_n_arr) >= 2:
        slope, intercept = np.polyfit(known_n_arr, measured_arr, 1)
        residuals = measured_arr - (slope * known_n_arr + intercept)
        summary["fit"] = {
            "slope": round(float(slope), 4),
            "intercept_N": round(float(intercept), 4),
            "residual_stdev_N": round(float(np.std(residuals)), 4),
            "max_abs_residual_N": round(float(np.max(np.abs(residuals))), 4),
        }
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        axes[0].plot(t, res_n[:, 2], linewidth=0.7)
        for seg in segments:
            axes[0].axvspan(seg["t_start"], seg["t_end"], alpha=0.15, color="C1")
            axes[0].text((seg["t_start"] + seg["t_end"]) / 2,
                         axes[0].get_ylim()[1] * 0.9,
                         f"{seg['weight_g']} g", ha="center", fontsize=8)
        axes[0].set_xlabel("Time (s)")
        axes[0].set_ylabel("Fz (N)")
        axes[0].set_title("Response timeline")
        axes[0].grid(alpha=0.3)

        axes[1].plot(known_n_arr, measured_arr, "o")
        xx = np.linspace(0, max(known_n_arr) * 1.05, 50)
        axes[1].plot(xx, slope * xx + intercept, "r--",
                      label=f"fit: {slope:.3f}·F + {intercept:+.3f}")
        axes[1].plot([0, max(known_n_arr)], [0, max(known_n_arr)],
                      "k:", alpha=0.5, label="ideal y=x")
        axes[1].set_xlabel("Applied force (N)")
        axes[1].set_ylabel("Measured Fz (N)")
        axes[1].set_title("Response curve")
        axes[1].legend(loc="upper left", fontsize=9)
        axes[1].grid(alpha=0.3)
        plt.tight_layout()
        plot_path = csv_path.with_suffix(".response.png")
        fig.savefig(plot_path, dpi=110)
        plt.close(fig)
        summary["plot"] = plot_path.name
    return summary


# =============================================================================
# CLI
# =============================================================================


def _write_summary(out_path: Path, summary: dict) -> None:
    sidecar = out_path.with_suffix(".summary.json")
    sidecar.write_text(json.dumps(summary, indent=2))
    print(f"\nSummary -> {sidecar.name}", flush=True)
    for k, v in summary.items():
        if isinstance(v, dict):
            print(f"  {k}:", flush=True)
            for k2, v2 in v.items():
                print(f"    {k2}: {v2}")
        elif isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
            print(f"  {k}: {len(v)} entries")
        else:
            print(f"  {k}: {v}")


def cmd_noise(args) -> int:
    with _open_board(args.port, args.baud, calibrate=args.calibrate) as (hand, cfg, fw, part):
        print(f"\nRecording {args.duration:.0f}s of unloaded baseline ...")
        print("(keep the sensor untouched and stable.)")
        n = _record(hand, cfg, Path(args.out), fw, part, args.duration)
        print(f"\nDone. {n} frames written.")
    if not args.no_analyze:
        summary = analyze_noise(Path(args.out))
        _write_summary(Path(args.out), summary)
    return 0


def cmd_drift(args) -> int:
    with _open_board(args.port, args.baud, calibrate=args.calibrate) as (hand, cfg, fw, part):
        mins = args.duration / 60
        print(f"\nRecording {mins:.1f} min ({args.duration:.0f}s) of drift data ...")
        print("(keep the sensor untouched, ambient stable.)")
        n = _record(hand, cfg, Path(args.out), fw, part, args.duration)
        print(f"\nDone. {n} frames written.")
    if not args.no_analyze:
        summary = analyze_drift(Path(args.out), bin_seconds=args.bin_seconds)
        _write_summary(Path(args.out), summary)
    return 0


def cmd_response(args) -> int:
    """Interactive: prompt for each known weight, capture a window, repeat."""
    weights = [int(w) for w in args.weights]
    if not weights:
        sys.exit("Provide at least one --weights value, in grams (e.g. --weights 50 100 200).")
    segments: List[dict] = []
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with _open_board(args.port, args.baud, calibrate=args.calibrate) as (hand, cfg, fw, part):
        with CsvRecorder(out_path, cfg, format="vendor",
                          firmware=fw, sensor_part=part) as rec:
            session_start = time.monotonic()
            print(f"\nResponse capture — {len(weights)} weights.")
            for w_g in weights:
                input(f"\nPlace {w_g} g weight on the sensor, then press Enter ...")
                t_start = time.monotonic() - session_start
                seg_n = 0
                window = max(2.0, args.window)
                deadline = time.monotonic() + window
                for frame in hand.stream_auto_push(duration=window):
                    rec.write(frame)
                    seg_n += 1
                    if time.monotonic() >= deadline:
                        break
                t_end = time.monotonic() - session_start
                segments.append({"weight_g": w_g,
                                  "t_start": round(t_start, 3),
                                  "t_end": round(t_end, 3),
                                  "n_frames": seg_n})
                print(f"  captured {seg_n} frames for {w_g} g  ({t_start:.1f}-{t_end:.1f}s)")
                input("Remove the weight, then press Enter to continue ...")
        seg_path = out_path.with_suffix(".segments.json")
        seg_path.write_text(json.dumps(segments, indent=2))
        print(f"\nSegments -> {seg_path.name}")
    if not args.no_analyze:
        summary = analyze_response(out_path, seg_path)
        _write_summary(out_path, summary)
    return 0


def cmd_report(args) -> int:
    p = Path(args.csv)
    if not p.exists():
        sys.exit(f"File not found: {p}")
    if args.mode == "auto":
        # Auto-detect: if a sibling .segments.json exists -> response.
        # Otherwise, use the recording duration: short = noise, long = drift.
        seg = p.with_suffix(".segments.json")
        if seg.exists():
            mode = "response"
        else:
            # Quick peek at the duration
            with p.open() as f:
                first = next(csv.reader(f))
                rows = list(csv.reader(f))
            def ts(s):
                h, m, rest = s.split(":")
                sec, ms = rest.split(".")
                return int(h)*3600 + int(m)*60 + int(sec) + int(ms)/1000.0
            dur = ts(rows[-1][0]) - ts(rows[0][0]) if len(rows) > 1 else 0
            mode = "drift" if dur > 300 else "noise"
    else:
        mode = args.mode

    if mode == "noise":
        summary = analyze_noise(p)
    elif mode == "drift":
        summary = analyze_drift(p)
    elif mode == "response":
        seg = p.with_suffix(".segments.json")
        summary = analyze_response(p, seg if seg.exists() else None)
    else:
        sys.exit(f"Unknown mode: {mode}")
    _write_summary(p, summary)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    common_record = argparse.ArgumentParser(add_help=False)
    common_record.add_argument("--port", required=True, help="COM port (e.g. COM7 or /dev/cu.usbserial-XXXX).")
    common_record.add_argument("--baud", type=int, default=921600)
    common_record.add_argument("--calibrate", action="store_true",
                                help="Zero the baseline before recording.")
    common_record.add_argument("--no-analyze", action="store_true",
                                help="Just record; skip stats + plot generation.")

    p_noise = sub.add_parser("noise", parents=[common_record],
                              help="60-second unloaded baseline → noise floor stats + plot.")
    p_noise.add_argument("--duration", type=float, default=60.0)
    p_noise.add_argument("--out", default="runs/noise.csv")
    p_noise.set_defaults(func=cmd_noise)

    p_drift = sub.add_parser("drift", parents=[common_record],
                              help="Long unloaded recording → drift rate + binned trend plot.")
    p_drift.add_argument("--duration", type=float, default=1800.0,
                         help="Default 1800 s = 30 min.")
    p_drift.add_argument("--bin-seconds", type=float, default=10.0)
    p_drift.add_argument("--out", default="runs/drift.csv")
    p_drift.set_defaults(func=cmd_drift)

    p_resp = sub.add_parser("response", parents=[common_record],
                             help="Interactive known-weight presses → response curve + fit.")
    p_resp.add_argument("--weights", nargs="+", default=["50", "100", "200", "500"],
                        help="Known weights in grams.")
    p_resp.add_argument("--window", type=float, default=3.0,
                         help="Seconds to capture per weight (default 3).")
    p_resp.add_argument("--out", default="runs/response.csv")
    p_resp.set_defaults(func=cmd_response)

    p_rep = sub.add_parser("report",
                            help="Re-analyze an existing CSV (no hardware needed).")
    p_rep.add_argument("csv", help="Path to a Paxini-format CSV.")
    p_rep.add_argument("--mode", choices=["auto", "noise", "drift", "response"],
                       default="auto")
    p_rep.set_defaults(func=cmd_report)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
