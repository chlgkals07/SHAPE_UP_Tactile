"""Find where a LEAP joint stopped following its command in a ``--log-csv`` file.

    python3 -m leap_teleop.tools.analyze_log run.csv --joints 0 1 2 3

For every tick it classifies each joint:
  stall    sent - pos > --lag deg and |current| >= --cur-frac x limit  (blocked: contact/collision)
  lag      sent - pos > --lag deg, current below the limit                (slow / gains / friction)
  clipped  cmd and sent differ by > --lag deg for a while               (LEAP bounds or slew limit)
and prints the episodes (runs of consecutive ticks) with the glove values at their start,
so you can tell glove-side drops (cmd itself goes back) from motor-side stops.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from leap_teleop.hand.joints import ANGLE_NAMES

FINGER_GLOVE = {
    "index": ("IndexSpread", "IndexMCPStretch", "IndexPIPStretch", "IndexDIPStretch"),
    "middle": ("MiddleSpread", "MiddleMCPStretch", "MiddlePIPStretch", "MiddleDIPStretch"),
    "ring": ("RingSpread", "RingMCPStretch", "RingPIPStretch", "RingDIPStretch"),
    "thumb": ("ThumbSpread", "ThumbCMCStretch", "ThumbMCPStretch", "ThumbIPStretch"),
}


def load(path: Path) -> dict[str, np.ndarray]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    cols: dict[str, np.ndarray] = {}
    for key in rows[0]:
        if key == "mode":
            cols[key] = np.array([r[key] for r in rows])
        else:
            cols[key] = np.array([float(r[key]) if r[key] else np.nan for r in rows])
    return cols


def episodes(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    out, start = [], None
    for i, m in enumerate(np.append(mask, False)):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", type=Path)
    p.add_argument("--joints", type=int, nargs="+", default=[0, 1, 2, 3])
    p.add_argument("--lag", type=float, default=8.0, help="deg of sent-vs-present gap that counts")
    p.add_argument("--current-limit", type=float, default=300.0)
    p.add_argument("--cur-frac", type=float, default=0.85)
    p.add_argument("--min-ticks", type=int, default=5, help="ignore shorter runs (50 Hz: 5 = 0.1 s)")
    a = p.parse_args(argv)

    d = load(a.csv)
    t = d["t"]
    glove = {k[6:]: v for k, v in d.items() if k.startswith("glove_")}
    # forward-fill glove (blank on ticks without a new sample)
    for k, v in glove.items():
        idx = np.where(~np.isnan(v), np.arange(len(v)), 0)
        np.maximum.accumulate(idx, out=idx)
        glove[k] = v[idx]
    live = d["mode"] == "live"
    print(f"{a.csv}: {len(t)} ticks, {t[-1]:.1f} s, live {live.mean() * 100:.0f}%")

    for j in a.joints:
        name = ANGLE_NAMES[j]
        finger = name.split("_")[0]
        cmd, sent, pos, cur = d[f"cmd_{j}"], d[f"sent_{j}"], d[f"pos_{j}"], d[f"cur_{j}"]
        if np.all(np.isnan(pos)):
            print(f"\nID {j} {name}: no feedback (dry-run?)")
            continue
        gap = sent - pos
        sat = np.abs(cur) >= a.cur_frac * a.current_limit
        kinds = {
            "stall": live & (np.abs(gap) > a.lag) & sat,
            "lag": live & (np.abs(gap) > a.lag) & ~sat,
            "clipped": live & (np.abs(cmd - sent) > a.lag),
        }
        print(f"\nID {j} {name}: |cur| max {np.nanmax(np.abs(cur)):.0f} mA, "
              f"p95 {np.nanpercentile(np.abs(cur), 95):.0f} mA, "
              f"gap max {np.nanmax(np.abs(gap)):.1f} deg")
        for kind, mask in kinds.items():
            eps = episodes(mask, a.min_ticks)
            if not eps:
                continue
            total = sum(e - s for s, e in eps) / len(t) * 100
            print(f"  {kind}: {len(eps)} episodes, {total:.1f}% of ticks")
            for s, e in eps[:8]:
                g = "  ".join(f"{n[len(finger):] or n}={glove[n][s]:.0f}"
                              for n in FINGER_GLOVE[finger] if n in glove)
                print(f"    t={t[s]:6.2f}-{t[e - 1]:6.2f}s  cmd={cmd[s]:6.1f} sent={sent[s]:6.1f} "
                      f"pos={pos[s]:6.1f} cur={cur[s]:5.0f}  glove: {g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
