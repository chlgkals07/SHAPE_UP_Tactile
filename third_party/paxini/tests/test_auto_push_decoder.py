"""Tests for the payload-aware auto-push decoder.

Cross-checked against:
- Protocol PDF section 4.4.2: payload length is determined by 0x0010-0x0013,
  0x0016 and 0x0030-0x0067.
- The captured Paxini host-app CSV "2026-05-18-160858" which had only one
  active module (Index-Tip = module index 6) with 52 distributed-force points
  and the default 0x0016 = 0x03 (both resultant and distributed).
"""

import pytest

from paxini_sdk.boards.high_speed import (
    AutoPushConfig,
    AutoPushFrame,
    _decode_resultant_6bytes,
    _decode_distributed_3bytes,
)
from paxini_sdk import registers


# ---- bitmap parsing --------------------------------------------------------


def test_parse_bitmap_single_index_tip():
    """0x40 in byte 0 corresponds to bit 6 = Index-Tip (module index 6)."""
    active = registers.parse_active_modules_bitmap(b"\x40\x00\x00\x00")
    assert active == [6]
    assert registers.MODULE_NAMES[6] == "Index-Tip"


def test_parse_bitmap_thumb_proximal_and_palm8():
    active = registers.parse_active_modules_bitmap(b"\x01\x00\x00\x08")
    assert active == [0, 27]  # Thumb-Proximal, Palm-8
    assert registers.MODULE_NAMES[0] == "Thumb-Proximal"
    assert registers.MODULE_NAMES[27] == "Palm-8"


def test_parse_bitmap_all_28():
    active = registers.parse_active_modules_bitmap(b"\xFF\xFF\xFF\x0F")
    assert active == list(range(28))


def test_parse_bitmap_ignores_unused_bits_in_byte3():
    # bits 4-7 of byte 3 do not correspond to any module (28 slots only)
    active = registers.parse_active_modules_bitmap(b"\x00\x00\x00\xF0")
    assert active == []  # those high bits don't index any module


# ---- AutoPushConfig --------------------------------------------------------


def test_config_expected_payload_size_index_tip_only():
    """With only Index-Tip active, 52 pts, default 0x16 = 0x03:
    payload = 6 (resultant) + 52*3 (distributed) = 162 bytes."""
    cfg = AutoPushConfig(
        active_modules=[6],
        has_resultant=True,
        has_distributed=True,
        point_counts={6: 52},
    )
    assert cfg.expected_payload_size() == 162


def test_config_resultant_only_two_modules():
    cfg = AutoPushConfig(
        active_modules=[2, 6],
        has_resultant=True,
        has_distributed=False,
        point_counts={2: 50, 6: 52},
    )
    assert cfg.expected_payload_size() == 12  # 2 * 6


def test_config_module_offset_finds_right_section():
    cfg = AutoPushConfig(
        active_modules=[2, 6],
        has_resultant=True,
        has_distributed=True,
        point_counts={2: 10, 6: 5},
    )
    # Module 2: resultant at 0, distributed at 6
    assert cfg.module_offset(2) == (0, 6)
    # Module 6: resultant at 6 + 10*3 = 36, distributed at 36+6 = 42
    assert cfg.module_offset(6) == (36, 42)
    assert cfg.module_offset(99) is None


# ---- Decode helpers --------------------------------------------------------


def test_decode_resultant_low_byte_rule():
    # Raw bytes [0xFE, 0x00, 0x05, 0x00, 0xC8, 0x00]:
    # Fx = -2 (signed int8 of 0xFE), Fy = 5, Fz = 200 (uint8)
    assert _decode_resultant_6bytes(bytes.fromhex("FE000500C800")) == (-2, 5, 200)
    # All zeros
    assert _decode_resultant_6bytes(bytes(6)) == (0, 0, 0)
    # Extremes
    assert _decode_resultant_6bytes(bytes.fromhex("7F00800000FF00")) == (127, -128, 0)
    # Note last byte 0xFF would only matter if Fz were signed — Fz is uint8.


def test_decode_distributed_low_byte_rule():
    # Distributed force packs are 3 bytes: [Fx_lo, Fy_lo, Fz_lo]
    assert _decode_distributed_3bytes(bytes.fromhex("FE05C8")) == (-2, 5, 200)
    assert _decode_distributed_3bytes(b"\x00\x00\x00") == (0, 0, 0)


# ---- AutoPushFrame end-to-end --------------------------------------------


def _build_payload_index_tip(fx: int, fy: int, fz_uint: int,
                              dist_points: list) -> bytes:
    """Assemble a 162-byte payload as the board would emit for Index-Tip only."""
    # Resultant section (6 bytes)
    fx_byte = fx & 0xFF
    fy_byte = fy & 0xFF
    resultant = bytes([fx_byte, 0, fy_byte, 0, fz_uint & 0xFF, 0])
    # Distributed: 52 × 3 bytes
    dist = bytearray()
    for fx_p, fy_p, fz_p in dist_points:
        dist.extend([fx_p & 0xFF, fy_p & 0xFF, fz_p & 0xFF])
    while len(dist) < 52 * 3:
        dist.extend(b"\x00\x00\x00")
    return resultant + bytes(dist[: 52 * 3])


def test_auto_push_frame_decodes_index_tip_only_payload():
    cfg = AutoPushConfig(
        active_modules=[6],
        has_resultant=True,
        has_distributed=True,
        point_counts={6: 52},
    )
    # Press event: Fz=8 LSB (0.8 N), small Fx/Fy
    payload = _build_payload_index_tip(
        fx=2, fy=-1, fz_uint=8,
        dist_points=[(0, 0, 4)] * 5 + [(0, 0, 0)] * 47,
    )
    assert len(payload) == cfg.expected_payload_size()

    frame = AutoPushFrame(config=cfg, error_code=0, valid_data=payload, raw=b"")
    # Resultant should be just Index-Tip
    assert frame.resultant_forces == {"Index-Tip": (2, -1, 8)}
    assert frame.resultant_forces_newtons == {"Index-Tip": (0.2, -0.1, 0.8)}
    # No "Thumb-Tip" or other spurious slots in output
    assert "Thumb-Tip" not in frame.resultant_forces
    assert set(frame.resultant_forces.keys()) == {"Index-Tip"}

    # Distributed: 52 points, first 5 have Fz=4, rest zero
    dist = frame.distributed_forces["Index-Tip"]
    assert len(dist) == 52
    assert dist[0] == (0, 0, 4)
    assert dist[4] == (0, 0, 4)
    assert dist[5] == (0, 0, 0)
    assert dist[51] == (0, 0, 0)

    # Newton scaling on distributed
    dn = frame.distributed_forces_newtons["Index-Tip"]
    assert dn[0] == (0.0, 0.0, 0.4)


def test_auto_push_frame_negative_fx_decoded_as_signed():
    """The bug we found: 0xFE for Fx should be -2, not +254."""
    cfg = AutoPushConfig(
        active_modules=[6], has_resultant=True, has_distributed=False,
        point_counts={6: 0},
    )
    # Resultant section only; Fx_lo = 0xFE
    payload = bytes([0xFE, 0, 0x00, 0, 0x00, 0])
    frame = AutoPushFrame(config=cfg, error_code=0, valid_data=payload, raw=b"")
    forces = frame.resultant_forces
    assert forces == {"Index-Tip": (-2, 0, 0)}


def test_auto_push_frame_no_active_modules_returns_empty():
    cfg = AutoPushConfig(active_modules=[], has_resultant=True,
                         has_distributed=True, point_counts={})
    frame = AutoPushFrame(config=cfg, error_code=0, valid_data=b"", raw=b"")
    assert frame.resultant_forces == {}
    assert frame.distributed_forces == {}


def test_auto_push_frame_two_active_modules_separates_correctly():
    """With Thumb-Tip (module 2, 5 pts) and Index-Tip (module 6, 4 pts):

    payload layout:
      [Thumb-Tip resultant 6 bytes]
      [Thumb-Tip distributed 15 bytes (5*3)]
      [Index-Tip resultant 6 bytes]
      [Index-Tip distributed 12 bytes (4*3)]
      = 39 bytes total
    """
    cfg = AutoPushConfig(
        active_modules=[2, 6],
        has_resultant=True,
        has_distributed=True,
        point_counts={2: 5, 6: 4},
    )
    # Build a payload where Thumb-Tip has Fz=10 and Index-Tip has Fz=20
    thumb_resultant = bytes([5, 0, 3, 0, 10, 0])
    thumb_dist = bytes([1, 1, 1] * 5)
    index_resultant = bytes([0xFF, 0, 0xFF, 0, 20, 0])  # Fx=-1, Fy=-1, Fz=20
    index_dist = bytes([2, 2, 2] * 4)
    payload = thumb_resultant + thumb_dist + index_resultant + index_dist
    assert len(payload) == cfg.expected_payload_size()

    frame = AutoPushFrame(config=cfg, error_code=0, valid_data=payload, raw=b"")
    rf = frame.resultant_forces
    assert rf["Thumb-Tip"] == (5, 3, 10)
    assert rf["Index-Tip"] == (-1, -1, 20)
    assert set(rf.keys()) == {"Thumb-Tip", "Index-Tip"}

    df = frame.distributed_forces
    assert len(df["Thumb-Tip"]) == 5
    assert len(df["Index-Tip"]) == 4
    assert df["Thumb-Tip"][0] == (1, 1, 1)
    assert df["Index-Tip"][0] == (2, 2, 2)


# ---- Calibration frame ----------------------------------------------------


def test_high_speed_calibration_frame_matches_vendor():
    """The wrapper's calibration frame must byte-match the one hardcoded in
    vendor Hand_UI.py (line ~274): '55AA00170200010001E6'."""
    from paxini_sdk.protocol import (
        FUNC_HS_CALIBRATION,
        build_simple_request,
    )
    frame = build_simple_request(FUNC_HS_CALIBRATION, 0x0002, data=b"\x01")
    assert frame.hex().upper() == "55AA001702000100" + "01" + "E6"
    # Last byte LRC = 0xE6
    assert frame[-1] == 0xE6
