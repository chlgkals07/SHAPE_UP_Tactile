"""Hardware-free tests for the protocol layer.

These tests exercise framing & LRC against the byte-exact request strings
shown in the official Paxini Python examples, so we know our builders match
the wire format expected by the boards.
"""

from __future__ import annotations

import pytest

from paxini_sdk.protocol import (
    FIN_FUNC_CALIBRATION,
    FIN_FUNC_FORCE,
    FUNC_READ_SIMPLE,
    FUNC_WRITE_SIMPLE,
    build_fin_request,
    build_simple_request,
    lrc,
    parse_auto_push,
    parse_simple_response,
    split_force_xyz,
)
from paxini_sdk.exceptions import LRCError, FrameError


def hexs(s: str) -> bytes:
    return bytes.fromhex(s.replace(" ", ""))


# ---- LRC --------------------------------------------------------------------


def test_lrc_known_values():
    # From official Read_Single_Sensor_Hand.py: 55AA 00 03 0000 0F00 -> EF
    assert lrc(hexs("55AA000300000F00")) == 0xEF
    # From the same example: open auto-push 55AA00101700010001 -> D8
    assert lrc(hexs("55AA00101700010001")) == 0xD8


def test_lrc_roundtrip_for_zero_payload():
    assert lrc(b"\x00\x00\x00") == 0x00
    # Sum + (~sum + 1) == 0 mod 256 — i.e. appending the LRC zeroes the sum
    payload = b"\x12\x34\x56\x78"
    assert (sum(payload) + lrc(payload)) % 256 == 0


# ---- High-speed (simple) framing -------------------------------------------


def test_build_read_version_matches_example():
    # Read 15 bytes from register 0x0000 -> "55AA000300000F00EF"
    frame = build_simple_request(FUNC_READ_SIMPLE, 0x0000, data_len=0x000F)
    assert frame.hex().upper() == "55AA000300000F00EF"


def test_build_enable_auto_push_matches_example():
    # Write 1 byte = 0x01 to register 0x0017 -> "55AA00101700010001D8"
    frame = build_simple_request(FUNC_WRITE_SIMPLE, 0x0017, data=b"\x01")
    assert frame.hex().upper() == "55AA00101700010001D8"


def test_parse_simple_read_response_roundtrip():
    # Build a synthetic response: head AA55, reserved 00, fc 03, addr 0000,
    # data_len 04, data 41 42 43 44, LRC.
    body = bytearray.fromhex("AA55000300000400") + b"ABCD"
    body.append(lrc(bytes(body)))
    parsed = parse_simple_response(bytes(body))
    assert parsed.func_code == FUNC_READ_SIMPLE
    assert parsed.reg_addr == 0x0000
    assert parsed.data == b"ABCD"
    assert parsed.is_error is False


def test_parse_simple_response_bad_head_raises():
    with pytest.raises(FrameError):
        parse_simple_response(b"\xDE\xAD" + b"\x00" * 10)


def test_parse_simple_response_bad_lrc_raises():
    body = bytearray.fromhex("AA55000300000400") + b"ABCD" + b"\x00"
    with pytest.raises(LRCError):
        parse_simple_response(bytes(body))


def test_parse_auto_push_basic():
    # head AA56, reserved 00, valid_frame_len = 5 (=> 4 bytes valid data + 1 ec),
    # error_code 0x00, valid_data 4 bytes, LRC
    payload = bytearray.fromhex("AA56000500" + "00") + b"\x01\x02\x03\x04"
    payload.append(lrc(bytes(payload)))
    p = parse_auto_push(bytes(payload))
    assert p.error_code == 0x00
    assert p.valid_data == b"\x01\x02\x03\x04"


# ---- fin_master (Serial Converter Board) framing ----------------------------


def test_build_fin_calibration_matches_example():
    # Official frame from Read_Single_Sensor_Usb.py:
    # "55 AA 0A 00 01 00 79 03 00 00 00 01 00 01 78"
    # That writes 1 byte (0x01) to addr 0x00000003 with FC 0x79.
    frame = build_fin_request(
        FIN_FUNC_CALIBRATION, addr=0x00000003, read=False, data=b"\x01"
    )
    assert frame.hex().upper() == "55AA0A000100790300000001000178"
    assert frame[-1] == 0x78


def test_build_fin_read_resultant_force_matches_example():
    # "55 AA 09 00 01 00 FB F0 03 00 00 03 00 06"
    # Read 3 bytes from addr 0x000003F0 with base FC 0x7B (read => 0xFB).
    frame = build_fin_request(
        FIN_FUNC_FORCE, addr=0x000003F0, read=True, data_len=3
    )
    assert frame.hex().upper() == "55AA09000100FBF00300000300" + f"{frame[-1]:02X}".upper()
    assert frame[-1] == 0x06


def test_build_fin_read_distributed_force_matches_example():
    # "55 AA 09 00 01 00 FB 0E 04 00 00 E7 00 03"
    # Read 0x00E7 = 231 bytes from addr 0x0000040E with FC 0xFB.
    frame = build_fin_request(
        FIN_FUNC_FORCE, addr=0x0000040E, read=True, data_len=0x00E7
    )
    expected = "55AA09000100FB0E040000E700"
    assert frame.hex().upper().startswith(expected)
    assert frame[-1] == 0x03


# ---- helpers ----------------------------------------------------------------


def test_split_force_xyz_signed_unsigned():
    # Fx negative, Fy positive, Fz unsigned high
    assert split_force_xyz(b"\xFE\x05\xC8") == (-2, 5, 200)
    assert split_force_xyz(b"\x00\x00\x00") == (0, 0, 0)
    assert split_force_xyz(b"\x7F\x80\xFF") == (127, -128, 255)
