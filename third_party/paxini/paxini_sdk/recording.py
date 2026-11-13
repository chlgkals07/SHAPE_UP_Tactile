"""Per-frame CSV recorder for AutoPushFrames.

Two output formats:

* ``vendor`` (default) — column scheme matches the Paxini host app's
  ``HH-MM-SS.csv`` recordings:

      Timestamp,M-S-1x1-X,M-S-1x1-Y,M-S-1x1-Z,M-S-NxN-X[0],M-S-NxN-Y[0],M-S-NxN-Z[0],...

  where M is the finger/slot index (0=thumb, 1=index, 2=middle, 3=ring,
  4=little, 5=palm) and S is the module-within-finger index (0=proximal,
  1=middle, 2=tip/distal, 3=nail for fingers; 0..7 for the 8 palm zones).

  Files in this format are drop-in compatible with
  ``paxini_to_rerun.py --csv``.

* ``native`` — slightly cleaner column names ("index_tip_fx_lsb",
  "index_tip_pt00_fz_lsb"), preceded by a JSON metadata header line
  describing the firmware, active modules, sample units, and provenance.
  Easier to parse downstream in pandas.

Values are written as **raw LSB counts** (signed int for Fx/Fy, unsigned
for Fz) since that's what the vendor host app records and what
characterization typically needs. Multiply by 0.1 to get newtons.

Usage::

    from paxini_sdk import HighSpeedHandBoard
    from paxini_sdk.recording import CsvRecorder

    with HighSpeedHandBoard("COM7") as hand, \\
         CsvRecorder("run.csv", hand.read_auto_push_config(),
                     firmware=hand.read_version()) as rec:
        for frame in hand.stream_auto_push(duration=30.0):
            rec.write(frame)
"""

from __future__ import annotations

import csv
import io
import json
import time
from datetime import datetime
from pathlib import Path
from typing import IO, Dict, List, Optional, Union

from . import registers


def module_to_vendor_prefix(module_idx: int) -> str:
    """Translate a wrapper module index (0..27) into the host-app's
    ``finger-module`` prefix used in CSV column headers."""
    if module_idx < 20:
        finger = module_idx // 4  # 0..4 = thumb/index/middle/ring/little
        sub = module_idx % 4       # 0..3 = proximal/middle/tip/nail
    else:
        finger = 5                 # 5 = palm
        sub = module_idx - 20      # 0..7 for the 8 palm zones
    return f"{finger}-{sub}"


def module_to_native_prefix(module_idx: int) -> str:
    """Lowercase underscore-separated module name, e.g. 'index_tip'."""
    name = registers.MODULE_NAMES[module_idx]
    return name.lower().replace("-", "_")


def _timestamp_now() -> str:
    """HH:MM:SS.mmm matching the host app's CSV timestamp format."""
    now = datetime.now()
    return f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}.{now.microsecond // 1000:03d}"


class CsvRecorder:
    """Streaming CSV writer for AutoPushFrames.

    The recorder is config-aware: it inspects the AutoPushConfig at open
    time and only writes columns for modules / data-types that the board
    is actually emitting. Frames whose payload shape doesn't match the
    initial config are still accepted but extra modules are ignored.

    Each ``write(frame)`` flushes the row to disk immediately, so a
    Ctrl+C kill or crash won't lose more than the last frame.
    """

    def __init__(
        self,
        path: Union[str, Path, IO],
        config,                       # AutoPushConfig — typed loosely to avoid import cycle
        *,
        format: str = "vendor",
        firmware: Optional[str] = None,
        sensor_part: Optional[str] = None,
    ):
        if format not in ("vendor", "native"):
            raise ValueError(f"format must be 'vendor' or 'native', got {format!r}")
        self.format = format
        self.config = config
        self.firmware = firmware
        self.sensor_part = sensor_part
        self._rows_written = 0
        self._owns_file = False
        self._t0 = None  # captured on first write so the user can see "elapsed since start"

        if isinstance(path, (str, Path)):
            self._fh = open(path, "w", newline="", encoding="utf-8")
            self._owns_file = True
            self.path = Path(path)
        else:
            self._fh = path
            self.path = None

        self._writer = csv.writer(self._fh)
        self._write_header()

    # ---- header --------------------------------------------------------

    def _vendor_columns(self) -> List[str]:
        cols = ["Timestamp"]
        for m in self.config.active_modules:
            prefix = module_to_vendor_prefix(m)
            if self.config.has_resultant:
                for axis in ("X", "Y", "Z"):
                    cols.append(f"{prefix}-1x1-{axis}")
            if self.config.has_distributed:
                n_pts = self.config.point_counts.get(m, 0)
                for i in range(n_pts):
                    for axis in ("X", "Y", "Z"):
                        cols.append(f"{prefix}-NxN-{axis}[{i}]")
        return cols

    def _native_columns(self) -> List[str]:
        cols = ["timestamp_iso", "timestamp_monotonic_s"]
        for m in self.config.active_modules:
            prefix = module_to_native_prefix(m)
            if self.config.has_resultant:
                for axis in ("fx", "fy", "fz"):
                    cols.append(f"{prefix}_resultant_{axis}_lsb")
            if self.config.has_distributed:
                n_pts = self.config.point_counts.get(m, 0)
                for i in range(n_pts):
                    for axis in ("fx", "fy", "fz"):
                        cols.append(f"{prefix}_pt{i:03d}_{axis}_lsb")
        return cols

    def _write_header(self) -> None:
        if self.format == "native":
            # Native format prepends a JSON metadata line (a single "#" comment row)
            meta = {
                "format_version": 1,
                "wrapper": "paxini_sdk",
                "firmware": self.firmware,
                "sensor_part": self.sensor_part,
                "units_force": "0.1 N per LSB (Fx/Fy signed int8, Fz uint8)",
                "active_modules": [registers.MODULE_NAMES[m] for m in self.config.active_modules],
                "has_resultant": self.config.has_resultant,
                "has_distributed": self.config.has_distributed,
                "point_counts": {
                    registers.MODULE_NAMES[m]: self.config.point_counts.get(m, 0)
                    for m in self.config.active_modules
                },
                "recording_started_iso": datetime.now().isoformat(timespec="microseconds"),
            }
            self._fh.write("# " + json.dumps(meta, separators=(",", ":")) + "\n")
            self._writer.writerow(self._native_columns())
        else:
            self._writer.writerow(self._vendor_columns())
        self._fh.flush()

    # ---- per-frame -----------------------------------------------------

    def write(self, frame) -> None:
        """Write one row for the given AutoPushFrame.

        Caller's responsibility to pass a frame whose ``frame.config``
        matches the recorder's config (i.e. came from the same
        ``stream_auto_push`` call).
        """
        if self._t0 is None:
            self._t0 = time.monotonic()
        if self.format == "native":
            row: List = [
                datetime.now().isoformat(timespec="microseconds"),
                round(time.monotonic() - self._t0, 6),
            ]
        else:
            row = [_timestamp_now()]
        res = frame.resultant_forces if self.config.has_resultant else {}
        dist = frame.distributed_forces if self.config.has_distributed else {}
        for m in self.config.active_modules:
            name = registers.MODULE_NAMES[m]
            n_pts = self.config.point_counts.get(m, 0)
            if self.config.has_resultant:
                fx, fy, fz = res.get(name, (0, 0, 0))
                row += [fx, fy, fz]
            if self.config.has_distributed:
                pts = dist.get(name, [])
                for i in range(n_pts):
                    if i < len(pts):
                        fx, fy, fz = pts[i]
                    else:
                        fx, fy, fz = 0, 0, 0
                    row += [fx, fy, fz]
        self._writer.writerow(row)
        self._fh.flush()
        self._rows_written += 1

    @property
    def rows_written(self) -> int:
        return self._rows_written

    # ---- lifecycle -----------------------------------------------------

    def close(self) -> None:
        if self._owns_file and self._fh and not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> "CsvRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
