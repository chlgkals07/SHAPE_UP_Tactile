"""Vendor-accurate module-force decode tests.

Cross-checked against vendor Hand_UI.py / parse_module_forces (lines
~1101-1135) and PaXini PX-6AX GEN3 Communication Board Communication
Protocol section 1.3.3. Each module is 6 bytes
[Fx_lo Fx_hi Fy_lo Fy_hi Fz_lo Fz_hi]; only the low byte is meaningful;
Fx/Fy signed int8, Fz uint8; scale = 0.1 N/LSB.
"""
from paxini_sdk.boards.high_speed import (
    AutoPushFrame,
    _decode_module_forces_lowbyte,
    _to_newtons,
)


def test_decode_module_forces_lowbyte_matches_vendor_rules():
    # Module 0: raw 0xFE 0x00, 0x05 0x00, 0xC8 0x00
    #   => Fx=-2, Fy=+5, Fz=200
    # Module 1: raw 0x7F 0x00, 0x80 0x00, 0xFF 0x00
    #   => Fx=+127, Fy=-128, Fz=255
    data = bytes.fromhex("FE000500C800") + bytes.fromhex("7F0080" + "00FF" + "00")
    decoded = _decode_module_forces_lowbyte(data)
    assert decoded[0] == (-2, 5, 200)
    assert decoded[1] == (127, -128, 255)
    n = _to_newtons(decoded)
    assert n[0] == (-0.2, 0.5, 20.0)
    assert n[1] == (12.7, -12.8, 25.5)


def test_decode_module_forces_ignores_high_bytes():
    """Vendor rule: high byte of each axis is reserved/ignored."""
    clean = bytes.fromhex("FE000500C800")  # one module
    dirty = bytes.fromhex("FEFF05AAC8DE")  # same low bytes, junk high bytes
    assert _decode_module_forces_lowbyte(clean) == _decode_module_forces_lowbyte(dirty)
    assert _decode_module_forces_lowbyte(dirty) == [(-2, 5, 200)]


def test_decode_module_forces_truncates_short_payload():
    """If the board emits < 28 modules, decode only what's there."""
    # 1 full module of 6 bytes + 3 leftover bytes -> 1 module decoded
    data = bytes.fromhex("00000000010A") + bytes.fromhex("000000")
    decoded = _decode_module_forces_lowbyte(data)
    assert len(decoded) == 1
    assert decoded[0] == (0, 0, 1)


def test_decode_module_forces_zero_padding():
    """All-zero payload decodes to all-zero forces (no false negatives)."""
    data = b"\x00" * 12  # two modules of zeros
    assert _decode_module_forces_lowbyte(data) == [(0, 0, 0), (0, 0, 0)]


def test_auto_push_frame_module_forces_vs_raw16():
    """Demonstrate the new low-byte decoder reads negative Fx/Fy correctly.

    Was previously also asserting on a legacy ``module_forces_raw16``
    accessor; that path was removed when the AutoPushFrame API became
    config-aware. The byte-level rule the test enforces still holds.
    """
    from paxini_sdk.boards.high_speed import AutoPushConfig
    # One module (Index-Tip): Fx = -2 (raw 0xFE), Fy = +5, Fz = 200
    valid_data = bytes.fromhex("FE000500C800")
    cfg = AutoPushConfig(active_modules=[6], has_resultant=True,
                         has_distributed=False, point_counts={6: 0})
    frame = AutoPushFrame(config=cfg, error_code=0, valid_data=valid_data, raw=b"")
    assert frame.resultant_forces["Index-Tip"] == (-2, 5, 200)
    assert frame.resultant_forces_newtons["Index-Tip"] == (-0.2, 0.5, 20.0)

def test_named_module_forces_uses_vendor_decode():
    """resultant_forces is dict-keyed by module name, only for active slots."""
    from paxini_sdk.boards.high_speed import AutoPushConfig
    # 28 modules all active, each with Fx=-1 raw 0xFF, Fz=10
    payload = b""
    for _ in range(28):
        payload += bytes.fromhex("FF0000000A00")  # Fx=-1, Fy=0, Fz=10
    cfg = AutoPushConfig(active_modules=list(range(28)),
                         has_resultant=True, has_distributed=False,
                         point_counts={i: 0 for i in range(28)})
    frame = AutoPushFrame(config=cfg, error_code=0, valid_data=payload, raw=b"")
    rf = frame.resultant_forces
    assert rf["Thumb-Tip"] == (-1, 0, 10)
    assert rf["Index-Tip"] == (-1, 0, 10)
    nn = frame.resultant_forces_newtons
    assert nn["Thumb-Tip"] == (-0.1, 0.0, 1.0)