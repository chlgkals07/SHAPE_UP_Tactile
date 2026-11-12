"""GEN3 wire protocol primitives.

The Paxini PX-6AX GEN3 product family uses two closely-related framings on the
USB-serial link, depending on which communication board is in use.

1. **fin_master / Serial Converter Board** (single-channel USB-serial board):

       55 AA  | LL LL | DD | 00 | FC | AA AA AA AA | LN LN | <data> | CC

   - ``55 AA``           request frame head (master -> sensor)
   - ``LL LL``           total frame length minus 5 (little-endian, uint16)
   - ``DD``              slave / device id (typically ``0x01``)
   - ``00``              reserved
   - ``FC``              function code; bit 7 set indicates *read*
   - ``AA AA AA AA``     start address (little-endian, uint32)
   - ``LN LN``           data length (little-endian, uint16)
   - ``<data>``          payload (write only)
   - ``CC``              LRC checksum

   Responses use ``AA 55`` as the head and the *same* layout for the body,
   followed by a status byte and the requested data.

2. **High-Speed Communication Board** (robotic hand controller):

   The high-speed board uses a slimmer framing — no slave id, and a 16-bit
   register address (instead of 32-bit):

       55 AA  | 00 | FC | RR RR | LN LN | <data> | CC

   - ``55 AA``           request head
   - ``00``              reserved
   - ``FC``              function code (``0x03`` read, ``0x10`` write)
   - ``RR RR``           register address (little-endian, uint16)
   - ``LN LN``           data length (little-endian, uint16)
   - ``<data>``          payload (write only)
   - ``CC``              LRC

   Normal responses use ``AA 55``; auto-push frames (continuous data stream)
   use ``AA 56``.

LRC is the classic Modbus-style checksum: sum all bytes, two's-complement,
keep low byte.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .exceptions import DeviceError, FrameError, LRCError


# ---- Frame heads -----------------------------------------------------------

REQ_HEAD = b"\x55\xAA"           # master -> sensor / board
RESP_HEAD_GENERAL = b"\xAA\x55"  # sensor / board -> master (normal)
RESP_HEAD_AUTO_PUSH = b"\xAA\x56"  # high-speed board auto-push frames

# ---- Function codes (high-speed / register-style boards) -------------------

FUNC_READ_SIMPLE = 0x03
FUNC_WRITE_SIMPLE = 0x10
# Custom calibration function code used by the high-speed board.
# Verified against the hardcoded frame in vendor Hand_UI.py
# ("55AA00170200010001E6" — FC=0x17, reg=0x0002, data=[0x01]).
FUNC_HS_CALIBRATION = 0x17

# ---- Function codes (fin_master / Serial Converter Board) -------------------
#
# In fin_master, the high bit of the function code means "read". The base
# function codes for force/calibration registers are:
#
#   0x79: calibration (write)
#   0x7B: read distributed/resultant force (read; bit 7 set -> 0xFB)
#   0x7A: enter OTA mode (write)
#   0x78: OTA chunk write
#
# Many official examples send the request with the read bit pre-set into the
# byte (0xFB). We expose helper functions that take a "base code" and a
# `read` boolean so callers don't have to remember which form the example used.

FIN_FUNC_CALIBRATION = 0x79
FIN_FUNC_FORCE = 0x7B
FIN_FUNC_OTA_ENTER = 0x7A
FIN_FUNC_OTA_WRITE = 0x78


# fin_master device status / error codes, returned in the response status
# byte. From protocol PDF section 2.7 "Error Code Query Table".
FIN_ERROR_NAMES = {
    0x00: "ERR_SUC",          # success
    0x01: "ERR_LEN",          # data length mismatch
    0x02: "ERR_VERIFY",       # check (LRC) failed
    0x03: "ERR_MAIN_CMD",     # main command invalid
    0x04: "ERR_SUB_CMD",      # subcommand invalid
    0x05: "ERR_REC_OUTRAGE",  # received data length exceeds info_buff
    0x06: "ERR_PARAM",        # parameter error
    0x07: "ERR_DATA_NONE",    # no data
    0x0A: "ERR_DATA_ARRANGE", # error during data transmission/arrangement
}


def fin_error_name(status: int) -> str:
    """Human-readable name for a fin_master status/error byte."""
    return FIN_ERROR_NAMES.get(status, f"ERR_UNKNOWN_0x{status:02X}")


# ---- LRC --------------------------------------------------------------------

def lrc(data: bytes) -> int:
    """Compute the GEN3 LRC checksum.

    Sum bytes, two's-complement, mask to 8 bits.
    """
    s = 0
    for b in data:
        s = (s + b) & 0xFF
    return ((~s) + 1) & 0xFF


def verify_lrc(frame: bytes) -> None:
    """Verify the LRC byte at the end of *frame*. Raises :class:`LRCError`."""
    if len(frame) < 2:
        raise LRCError(f"frame too short for LRC ({len(frame)} bytes)")
    expected = lrc(frame[:-1])
    actual = frame[-1]
    if expected != actual:
        raise LRCError(
            f"LRC mismatch: computed 0x{expected:02X}, frame carries 0x{actual:02X}"
        )


# ---- fin_master (Serial Converter Board) ------------------------------------

FIN_HEADER_LEN = 13  # head(2) + len(2) + dev(1) + rsv(1) + fc(1) + addr(4) + dlen(2)


def build_fin_request(
    func_code: int,
    addr: int,
    *,
    read: bool,
    data: bytes = b"",
    data_len: Optional[int] = None,
    device_id: int = 0x01,
) -> bytes:
    """Build a fin_master request frame for the Serial Converter Board.

    Parameters
    ----------
    func_code:
        Base function code (e.g. ``FIN_FUNC_FORCE``). Bit 7 will be set
        automatically when ``read=True``.
    addr:
        Start address (uint32).
    read:
        ``True`` for a read request, ``False`` for a write.
    data:
        Payload bytes (write only). Ignored if ``read`` is ``True``.
    data_len:
        Length of the data domain to encode in the request. For reads this is
        the number of bytes the master wants back. For writes it defaults to
        ``len(data)``.
    device_id:
        Slave id (default ``0x01``).
    """
    if read:
        fc_byte = (func_code | 0x80) & 0xFF
        payload = b""
        if data_len is None:
            raise ValueError("data_len is required for read requests")
    else:
        fc_byte = func_code & 0x7F
        payload = bytes(data)
        if data_len is None:
            data_len = len(payload)

    total = FIN_HEADER_LEN + len(payload) + 1  # header + payload + LRC
    length_field = total - 5  # matches the official C/Python examples

    buf = bytearray()
    buf += REQ_HEAD
    buf += length_field.to_bytes(2, "little")
    buf.append(device_id & 0xFF)
    buf.append(0x00)  # reserved
    buf.append(fc_byte)
    buf += int(addr).to_bytes(4, "little")
    buf += int(data_len).to_bytes(2, "little")
    buf += payload
    buf.append(lrc(bytes(buf)))
    return bytes(buf)


@dataclass
class FinResponse:
    head: bytes
    length_field: int
    device_id: int
    reserved: int
    func_code: int
    addr: int
    data_len: int
    status: int
    data: bytes
    raw: bytes


def parse_fin_response(frame: bytes) -> FinResponse:
    """Parse a fin_master response frame (Serial Converter Board).

    The response layout mirrors the request, with the same ``13``-byte header
    followed by a 1-byte status, the data, and the LRC.
    """
    if len(frame) < FIN_HEADER_LEN + 2:
        raise FrameError(f"fin response too short: {len(frame)} bytes")
    if frame[:2] != RESP_HEAD_GENERAL:
        raise FrameError(
            f"unexpected fin response head: {frame[:2].hex()} (expected aa55)"
        )

    length_field = int.from_bytes(frame[2:4], "little")
    device_id = frame[4]
    reserved = frame[5]
    func_code = frame[6]
    addr = int.from_bytes(frame[7:11], "little")
    data_len = int.from_bytes(frame[11:13], "little")
    status = frame[FIN_HEADER_LEN]
    # The status byte sits at index 13; data (if any) starts at index 14.
    # Read responses (FC bit 7 set, e.g. 0xFB) carry `data_len` payload
    # bytes after the status byte. Write responses (e.g. 0x79) carry NO
    # payload -- just status then LRC -- even though the ReturnedDataLength
    # field still echoes the request's length. Verified on hardware: a
    # calibration write ACK is exactly 15 bytes (13 header + status + LRC).
    is_read = bool(func_code & 0x80)
    data_start = FIN_HEADER_LEN + 1
    data_end = data_start + data_len if is_read else data_start
    if len(frame) < data_end + 1:  # +1 for LRC
        raise FrameError(
            f"fin response truncated: need {data_end + 1} bytes, got {len(frame)}"
        )
    verify_lrc(frame[: data_end + 1])
    data = bytes(frame[data_start:data_end])

    # NOTE: a non-zero status is NOT raised here -- parse_fin_response is a
    # pure parser. Callers (SingleSensorBoard._read / _write) inspect
    # `status` and raise DeviceError with a named code as appropriate.

    return FinResponse(
        head=frame[:2],
        length_field=length_field,
        device_id=device_id,
        reserved=reserved,
        func_code=func_code,
        addr=addr,
        data_len=data_len,
        status=status,
        data=data,
        raw=bytes(frame),
    )


# ---- High-Speed register-style protocol -------------------------------------


def build_simple_request(
    func_code: int,
    reg_addr: int,
    *,
    data: bytes = b"",
    data_len: Optional[int] = None,
) -> bytes:
    """Build a request frame for the High-Speed Communication Board.

    Parameters
    ----------
    func_code:
        ``FUNC_READ_SIMPLE`` (0x03) or ``FUNC_WRITE_SIMPLE`` (0x10).
    reg_addr:
        16-bit register address.
    data:
        Payload (write only).
    data_len:
        Number of bytes; defaults to ``len(data)`` for writes.
    """
    payload = bytes(data)
    if data_len is None:
        if func_code == FUNC_READ_SIMPLE:
            raise ValueError("data_len is required for read requests")
        data_len = len(payload)

    buf = bytearray()
    buf += REQ_HEAD
    buf.append(0x00)  # reserved
    buf.append(func_code & 0xFF)
    buf += int(reg_addr).to_bytes(2, "little")
    buf += int(data_len).to_bytes(2, "little")
    buf += payload
    buf.append(lrc(bytes(buf)))
    return bytes(buf)


@dataclass
class SimpleResponse:
    head: bytes
    reserved: int
    func_code: int
    reg_addr: int
    data_len: int
    data: bytes
    is_error: bool
    error_code: int
    raw: bytes


def parse_simple_response(frame: bytes) -> SimpleResponse:
    """Parse a normal-mode response from the High-Speed Communication Board."""
    if len(frame) < 9:
        raise FrameError(f"response too short: {len(frame)} bytes")
    if frame[:2] != RESP_HEAD_GENERAL:
        raise FrameError(
            f"unexpected response head: {frame[:2].hex()} (expected aa55)"
        )

    reserved = frame[2]
    func_code = frame[3]
    reg_addr = int.from_bytes(frame[4:6], "little")
    data_len = int.from_bytes(frame[6:8], "little")
    is_error = bool(func_code & 0x80)
    error_code = func_code & 0x7F if is_error else 0

    expected_total = 8 + data_len + 1
    if len(frame) < expected_total:
        raise FrameError(
            f"response truncated: need {expected_total} bytes, got {len(frame)}"
        )
    verify_lrc(frame[:expected_total])
    data = bytes(frame[8 : 8 + data_len])

    if is_error:
        raise DeviceError(
            f"device error 0x{error_code:02X} at register 0x{reg_addr:04X}",
            code=error_code,
        )

    return SimpleResponse(
        head=frame[:2],
        reserved=reserved,
        func_code=func_code,
        reg_addr=reg_addr,
        data_len=data_len,
        data=data,
        is_error=is_error,
        error_code=error_code,
        raw=bytes(frame[:expected_total]),
    )


@dataclass
class AutoPushParse:
    head: bytes
    reserved: int
    valid_frame_len: int
    error_code: int
    valid_data: bytes
    raw: bytes


def parse_auto_push(frame: bytes) -> AutoPushParse:
    """Parse an auto-push (``AA 56``) frame from the High-Speed board.

    Layout::

        AA 56 | RR | FL FL | EC | <valid data> | CC

    where ``FL`` is the *valid frame length* (valid_data_len + 1 for EC).
    """
    if len(frame) < 7:
        raise FrameError(f"auto-push frame too short: {len(frame)} bytes")
    if frame[:2] != RESP_HEAD_AUTO_PUSH:
        raise FrameError(
            f"unexpected auto-push head: {frame[:2].hex()} (expected aa56)"
        )
    reserved = frame[2]
    valid_frame_len = int.from_bytes(frame[3:5], "little")
    error_code = frame[5]
    valid_data_len = max(0, valid_frame_len - 1)
    expected_total = 6 + valid_data_len + 1
    if len(frame) < expected_total:
        raise FrameError(
            f"auto-push frame truncated: need {expected_total} bytes, got {len(frame)}"
        )
    verify_lrc(frame[:expected_total])
    valid_data = bytes(frame[6 : 6 + valid_data_len])
    return AutoPushParse(
        head=frame[:2],
        reserved=reserved,
        valid_frame_len=valid_frame_len,
        error_code=error_code,
        valid_data=valid_data,
        raw=bytes(frame[:expected_total]),
    )


# ---- Helpers ----------------------------------------------------------------


def split_force_xyz(data: bytes) -> Tuple[int, int, int]:
    """Decode a 3-byte resultant-force payload into signed Fx/Fy and unsigned Fz."""
    if len(data) < 3:
        raise FrameError(f"force payload too short: {len(data)} bytes")
    fx = data[0] - 256 if data[0] >= 128 else data[0]
    fy = data[1] - 256 if data[1] >= 128 else data[1]
    fz = data[2]  # unsigned
    return fx, fy, fz
