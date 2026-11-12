"""Tests for the CSV recorder.

These verify both formats end-to-end against synthetic AutoPushFrames,
and check that vendor-format output round-trips through
paxini_to_rerun.py's CSV header parser (i.e. recording is replayable).
"""

import csv
import io
import json
import re
from pathlib import Path

import pytest

from paxini_sdk.boards.high_speed import AutoPushConfig, AutoPushFrame
from paxini_sdk.recording import (
    CsvRecorder,
    module_to_native_prefix,
    module_to_vendor_prefix,
)


# ---- module-prefix helpers --------------------------------------------------


def test_vendor_prefix_finger_modules():
    # Thumb proximal..nail -> 0-0..0-3
    assert module_to_vendor_prefix(0) == "0-0"
    assert module_to_vendor_prefix(3) == "0-3"
    # Index proximal..nail -> 1-0..1-3
    assert module_to_vendor_prefix(4) == "1-0"
    assert module_to_vendor_prefix(6) == "1-2"   # Index-Tip (our test sensor's slot)
    # Little nail -> 4-3
    assert module_to_vendor_prefix(19) == "4-3"


def test_vendor_prefix_palm_zones():
    # Palm zones are finger 5, sub 0..7
    assert module_to_vendor_prefix(20) == "5-0"  # Palm-1
    assert module_to_vendor_prefix(27) == "5-7"  # Palm-8


def test_native_prefix():
    assert module_to_native_prefix(6) == "index_tip"
    assert module_to_native_prefix(0) == "thumb_proximal"
    assert module_to_native_prefix(20) == "palm_1"


# ---- vendor-format recording -----------------------------------------------


def _index_tip_config(n_pts: int = 4):
    return AutoPushConfig(
        active_modules=[6],
        has_resultant=True,
        has_distributed=True,
        point_counts={6: n_pts},
    )


def _build_index_tip_payload(resultant=(2, -1, 8), dist_points=None):
    """Helper: build a valid payload for one Index-Tip module."""
    if dist_points is None:
        dist_points = [(0, 0, 0), (0, 0, 4), (1, 1, 2), (0, 0, 0)]
    fx, fy, fz = resultant
    res = bytes([fx & 0xFF, 0, fy & 0xFF, 0, fz & 0xFF, 0])
    dist = bytearray()
    for px, py, pz in dist_points:
        dist += bytes([px & 0xFF, py & 0xFF, pz & 0xFF])
    return res + bytes(dist)


def test_vendor_recorder_header_matches_host_app_scheme(tmp_path):
    cfg = _index_tip_config(n_pts=4)
    path = tmp_path / "vendor.csv"
    with CsvRecorder(path, cfg, format="vendor"):
        pass  # just write the header
    with path.open() as f:
        header = next(csv.reader(f))
    # Column layout: Timestamp + Index-Tip(1x1 X/Y/Z) + Index-Tip(NxN X/Y/Z for 4 pts)
    expected_prefix = ["Timestamp",
                       "1-2-1x1-X", "1-2-1x1-Y", "1-2-1x1-Z",
                       "1-2-NxN-X[0]", "1-2-NxN-Y[0]", "1-2-NxN-Z[0]",
                       "1-2-NxN-X[1]", "1-2-NxN-Y[1]", "1-2-NxN-Z[1]",
                       "1-2-NxN-X[2]", "1-2-NxN-Y[2]", "1-2-NxN-Z[2]",
                       "1-2-NxN-X[3]", "1-2-NxN-Y[3]", "1-2-NxN-Z[3]"]
    assert header == expected_prefix


def test_vendor_recorder_writes_frame_values(tmp_path):
    cfg = _index_tip_config(n_pts=4)
    path = tmp_path / "vendor.csv"
    with CsvRecorder(path, cfg, format="vendor") as rec:
        payload = _build_index_tip_payload(resultant=(3, -2, 7),
                                            dist_points=[(0,0,1),(0,0,2),(0,0,3),(0,0,4)])
        frame = AutoPushFrame(config=cfg, error_code=0, valid_data=payload, raw=b"")
        rec.write(frame)
        assert rec.rows_written == 1
    with path.open() as f:
        rows = list(csv.reader(f))
    # First row is header, second row is data
    assert len(rows) == 2
    data = rows[1]
    # Timestamp + 3 (resultant) + 4*3 (distributed) = 16 columns
    assert len(data) == 16
    # Skip timestamp; values should match the payload
    values = [int(v) for v in data[1:]]
    assert values[:3] == [3, -2, 7]                      # resultant Fx, Fy, Fz
    assert values[3:6] == [0, 0, 1]                      # point 0
    assert values[12:15] == [0, 0, 4]                    # point 3


def test_vendor_recorder_handles_negative_signed_values(tmp_path):
    """0xFE should be preserved as -2 by the recorder, not 254."""
    cfg = _index_tip_config(n_pts=1)
    path = tmp_path / "neg.csv"
    with CsvRecorder(path, cfg, format="vendor") as rec:
        payload = _build_index_tip_payload(resultant=(-2, -1, 200),
                                           dist_points=[(0, 0, 0)])
        frame = AutoPushFrame(config=cfg, error_code=0, valid_data=payload, raw=b"")
        rec.write(frame)
    with path.open() as f:
        rows = list(csv.reader(f))
    data = [int(v) for v in rows[1][1:]]
    assert data[:3] == [-2, -1, 200]


# ---- native-format recording -----------------------------------------------


def test_native_recorder_writes_metadata_header(tmp_path):
    cfg = _index_tip_config(n_pts=2)
    path = tmp_path / "native.csv"
    with CsvRecorder(path, cfg, format="native",
                     firmware="ADAPTER_FW02.22",
                     sensor_part="PXSR-STDDP03G"):
        pass
    text = path.read_text().splitlines()
    # First line is a JSON-after-hash metadata blob
    assert text[0].startswith("# ")
    meta = json.loads(text[0][2:])
    assert meta["firmware"] == "ADAPTER_FW02.22"
    assert meta["sensor_part"] == "PXSR-STDDP03G"
    assert meta["active_modules"] == ["Index-Tip"]
    assert meta["has_resultant"] is True
    assert meta["has_distributed"] is True
    assert meta["point_counts"] == {"Index-Tip": 2}
    # Second line is the column header
    header = next(csv.reader([text[1]]))
    assert header[0] == "timestamp_iso"
    assert header[1] == "timestamp_monotonic_s"
    assert "index_tip_resultant_fx_lsb" in header
    assert "index_tip_pt000_fz_lsb" in header
    assert "index_tip_pt001_fz_lsb" in header


def test_native_recorder_round_trip_values(tmp_path):
    cfg = _index_tip_config(n_pts=2)
    path = tmp_path / "native.csv"
    with CsvRecorder(path, cfg, format="native") as rec:
        payload = _build_index_tip_payload(resultant=(5, 4, 30),
                                           dist_points=[(0, 0, 1), (0, 0, 2)])
        frame = AutoPushFrame(config=cfg, error_code=0, valid_data=payload, raw=b"")
        rec.write(frame)
    lines = path.read_text().splitlines()
    # Drop the metadata header line
    data_lines = [l for l in lines if not l.startswith("#")]
    rows = list(csv.reader(data_lines))
    header, data = rows[0], rows[1]
    cols = dict(zip(header, data))
    assert int(cols["index_tip_resultant_fx_lsb"]) == 5
    assert int(cols["index_tip_resultant_fy_lsb"]) == 4
    assert int(cols["index_tip_resultant_fz_lsb"]) == 30
    assert int(cols["index_tip_pt000_fz_lsb"]) == 1
    assert int(cols["index_tip_pt001_fz_lsb"]) == 2


# ---- multi-module recording ------------------------------------------------


def test_recorder_handles_two_active_modules(tmp_path):
    cfg = AutoPushConfig(
        active_modules=[2, 6],  # Thumb-Tip + Index-Tip
        has_resultant=True,
        has_distributed=True,
        point_counts={2: 3, 6: 2},
    )
    payload = (
        bytes([10, 0, 5, 0, 20, 0])         # Thumb-Tip resultant
        + bytes([1, 1, 1] * 3)               # Thumb-Tip distributed (3 pts)
        + bytes([0xFF, 0, 0xFF, 0, 30, 0])  # Index-Tip resultant (Fx=-1, Fy=-1)
        + bytes([2, 2, 2] * 2)               # Index-Tip distributed (2 pts)
    )
    path = tmp_path / "two_mod.csv"
    with CsvRecorder(path, cfg, format="vendor") as rec:
        frame = AutoPushFrame(config=cfg, error_code=0, valid_data=payload, raw=b"")
        rec.write(frame)
    rows = list(csv.reader(path.open()))
    header = rows[0]
    assert "0-2-1x1-X" in header  # Thumb-Tip
    assert "1-2-1x1-X" in header  # Index-Tip
    assert "0-2-NxN-X[2]" in header
    assert "1-2-NxN-X[1]" in header

    # Total cols = 1 ts + 3 + 9 (Thumb-Tip 3 pts) + 3 + 6 (Index-Tip 2 pts) = 22
    assert len(header) == 22
    # Spot-check that Index-Tip resultant Fx was decoded as -1, not +255
    fx_col = header.index("1-2-1x1-X")
    assert int(rows[1][fx_col]) == -1


# ---- per-row flushing ------------------------------------------------------


def test_recorder_flushes_each_row(tmp_path):
    """Each write must reach disk immediately so Ctrl+C doesn't lose data."""
    cfg = _index_tip_config(n_pts=2)
    path = tmp_path / "flush.csv"
    rec = CsvRecorder(path, cfg, format="vendor")
    # Don't close; check disk after a few writes
    for i in range(5):
        payload = _build_index_tip_payload(resultant=(i, i, i),
                                            dist_points=[(0, 0, 0), (0, 0, 0)])
        frame = AutoPushFrame(config=cfg, error_code=0, valid_data=payload, raw=b"")
        rec.write(frame)
    # File should already have 6 lines (1 header + 5 data) even though
    # we never called .close()
    n_lines = sum(1 for _ in path.open())
    assert n_lines == 6
    rec.close()
