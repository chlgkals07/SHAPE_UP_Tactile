"""High-level driver for the High-Speed Communication Board.

Implements the GEN3 register-style protocol used by the vendor's
Read_Single_Sensor_Hand.py and Hand_UI.py example scripts.

Key design point: auto-push payload size depends on which modules are active
(register 0x0010-0x0013) and which data types are emitted (register 0x0016),
per protocol PDF section 4.4.2. The driver reads that configuration before
parsing frames; AutoPushFrame instances carry an AutoPushConfig that tells
them how to decode their bytes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

from .. import registers
from ..exceptions import DeviceError, FrameError
from ..exceptions import TimeoutError as PaxiniTimeoutError
from ..protocol import (
    FUNC_HS_CALIBRATION,
    FUNC_READ_SIMPLE,
    FUNC_WRITE_SIMPLE,
    RESP_HEAD_AUTO_PUSH,
    RESP_HEAD_GENERAL,
    build_simple_request,
    parse_auto_push,
    parse_simple_response,
)
from ..transport import SerialTransport


# ---- Force decoding helpers (low-byte rule from vendor Hand_UI.py) ---------
#
# Each module's resultant force is 6 bytes: [Fx_lo Fx_hi Fy_lo Fy_hi Fz_lo Fz_hi]
# Only the low byte of each axis is meaningful; Fx/Fy signed int8, Fz uint8.
# Physical scale: 0.1 N per LSB. Distributed-force grid points are 3 bytes each:
# [Fx_lo Fy_lo Fz_lo], same signed/unsigned rule, same 0.1 N/LSB scale.


def _decode_resultant_6bytes(buf: bytes) -> Tuple[int, int, int]:
    fx_lo, fy_lo, fz_lo = buf[0], buf[2], buf[4]
    fx = fx_lo - 256 if fx_lo >= 128 else fx_lo
    fy = fy_lo - 256 if fy_lo >= 128 else fy_lo
    return fx, fy, fz_lo


def _decode_distributed_3bytes(buf: bytes) -> Tuple[int, int, int]:
    fx_lo, fy_lo, fz_lo = buf[0], buf[1], buf[2]
    fx = fx_lo - 256 if fx_lo >= 128 else fx_lo
    fy = fy_lo - 256 if fy_lo >= 128 else fy_lo
    return fx, fy, fz_lo


def _to_newtons_triple(t: Tuple[int, int, int]) -> Tuple[float, float, float]:
    return round(t[0] * 0.1, 1), round(t[1] * 0.1, 1), round(t[2] * 0.1, 1)


# ---- Config that captures the auto-push payload shape ----------------------


@dataclass
class AutoPushConfig:
    """The shape of the auto-push payload, derived from board registers.

    active_modules is in payload order (sorted ascending by module index per
    the bitmap layout in registers.parse_active_modules_bitmap).
    point_counts maps module index to number of distributed-force points
    reported for that module.
    """

    active_modules: List[int]
    has_resultant: bool
    has_distributed: bool
    point_counts: Dict[int, int]

    def expected_payload_size(self) -> int:
        size = 0
        for m in self.active_modules:
            if self.has_resultant:
                size += 6
            if self.has_distributed:
                size += self.point_counts.get(m, 0) * 3
        return size

    def module_offset(self, module_idx: int) -> Optional[Tuple[int, int]]:
        """Return (resultant_start, distributed_start) byte offsets for one
        active module, or None if the module is not active."""
        offset = 0
        for m in self.active_modules:
            r_start = offset if self.has_resultant else -1
            if self.has_resultant:
                offset += 6
            d_start = offset if self.has_distributed else -1
            if self.has_distributed:
                offset += self.point_counts.get(m, 0) * 3
            if m == module_idx:
                return r_start, d_start
        return None


# ---- Auto-push frame -------------------------------------------------------


@dataclass
class AutoPushFrame:
    """One auto-push burst, decoded against a known AutoPushConfig."""

    config: AutoPushConfig
    error_code: int
    valid_data: bytes
    raw: bytes
    timestamp: float = field(default_factory=time.time)

    @property
    def resultant_forces(self) -> Dict[str, Tuple[int, int, int]]:
        """{module_name: (Fx_lsb, Fy_lsb, Fz_lsb)} for each active module.

        Empty dict if the config doesn't include resultant data.
        """
        if not self.config.has_resultant:
            return {}
        out: Dict[str, Tuple[int, int, int]] = {}
        offset = 0
        for m in self.config.active_modules:
            if offset + 6 > len(self.valid_data):
                break
            out[registers.MODULE_NAMES[m]] = _decode_resultant_6bytes(
                self.valid_data[offset:offset + 6]
            )
            offset += 6
            if self.config.has_distributed:
                offset += self.config.point_counts.get(m, 0) * 3
        return out

    @property
    def resultant_forces_newtons(self) -> Dict[str, Tuple[float, float, float]]:
        return {k: _to_newtons_triple(v) for k, v in self.resultant_forces.items()}

    @property
    def distributed_forces(self) -> Dict[str, List[Tuple[int, int, int]]]:
        """{module_name: [(Fx_lsb, Fy_lsb, Fz_lsb), ...]} per active module."""
        if not self.config.has_distributed:
            return {}
        out: Dict[str, List[Tuple[int, int, int]]] = {}
        offset = 0
        for m in self.config.active_modules:
            if self.config.has_resultant:
                offset += 6
            n_pts = self.config.point_counts.get(m, 0)
            pts: List[Tuple[int, int, int]] = []
            for p in range(n_pts):
                base = offset + p * 3
                if base + 3 > len(self.valid_data):
                    break
                pts.append(_decode_distributed_3bytes(self.valid_data[base:base + 3]))
            out[registers.MODULE_NAMES[m]] = pts
            offset += n_pts * 3
        return out

    @property
    def distributed_forces_newtons(self) -> Dict[str, List[Tuple[float, float, float]]]:
        return {k: [_to_newtons_triple(p) for p in v]
                for k, v in self.distributed_forces.items()}


class HighSpeedHandBoard:
    DEFAULT_BAUDRATE = 921600

    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE, *, response_timeout: float = 1.0):
        self.transport = SerialTransport(port, baudrate)
        self.response_timeout = response_timeout

    def open(self):
        self.transport.open()
        return self

    def close(self):
        try:
            self.disable_auto_push()
        except Exception:
            pass
        self.transport.close()

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def read_register(self, addr: int, length: int) -> bytes:
        if not (1 <= length <= 512):
            raise ValueError(f"length out of range (1..512): {length}")
        req = build_simple_request(FUNC_READ_SIMPLE, addr, data_len=length)
        raw = self.transport.transaction(
            req, expected_head=RESP_HEAD_GENERAL,
            response_delay=0.05, timeout=self.response_timeout,
        )
        resp = parse_simple_response(raw)
        if resp.func_code != FUNC_READ_SIMPLE:
            raise FrameError(f"unexpected response func code 0x{resp.func_code:02X} (wanted read)")
        if len(resp.data) < length:
            raise FrameError(f"short read: wanted {length} bytes, got {len(resp.data)}")
        return resp.data[:length]

    def write_register(self, addr: int, data: bytes, *, response_head: bytes = RESP_HEAD_GENERAL) -> None:
        if not (1 <= len(data) <= 10):
            raise ValueError(f"write length out of range (1..10): {len(data)}")
        req = build_simple_request(FUNC_WRITE_SIMPLE, addr, data=data)
        raw = self.transport.transaction(
            req, expected_head=response_head,
            response_delay=0.05, timeout=self.response_timeout,
        )
        if response_head == RESP_HEAD_AUTO_PUSH:
            parsed = parse_auto_push(raw)
            if parsed.error_code != 0:
                raise DeviceError(
                    f"auto-push reg write failed, code 0x{parsed.error_code:02X}",
                    code=parsed.error_code,
                )
            return
        resp = parse_simple_response(raw)
        if resp.func_code != FUNC_WRITE_SIMPLE:
            raise FrameError(f"unexpected response func code 0x{resp.func_code:02X} (wanted write)")
        if resp.data and resp.data[0] != 0:
            raise DeviceError(f"write status nonzero: 0x{resp.data[0]:02X}", code=resp.data[0])

    def read_version(self) -> str:
        data = self.read_register(registers.REG_VERSION, registers.REG_VERSION_LEN)
        return data.decode("ascii", errors="replace").rstrip("\x00 ")

    # ---- Auto-push configuration discovery --------------------------------

    def read_active_modules(self) -> List[int]:
        """Return the sorted list of module indices currently emitting data."""
        bitmap = self.read_register(registers.REG_STATUS_THUMB_INDEX, 4)
        return registers.parse_active_modules_bitmap(bitmap)

    def read_data_type(self) -> int:
        """Return the data-type combination byte (register 0x0016)."""
        return self.read_register(registers.REG_DATA_TYPE, 1)[0]

    def read_distribution_point_count(self, module_index: int) -> int:
        if not (0 <= module_index < registers.MODULE_COUNT):
            raise ValueError(f"module_index out of range: {module_index}")
        addr = registers.REG_DISTRIBUTION_POINTS_BASE + module_index * 2
        data = self.read_register(addr, 2)
        return int.from_bytes(data, "little")

    def read_auto_push_config(self) -> AutoPushConfig:
        """Read 0x0010-0x0013, 0x0016, and 0x0030-0x0067 to assemble an
        AutoPushConfig describing the exact payload shape that
        stream_auto_push will see."""
        active = self.read_active_modules()
        data_type = self.read_data_type()
        # Read all 28 point-count slots at once (56 bytes from 0x0030)
        raw_counts = self.read_register(registers.REG_DISTRIBUTION_POINTS_BASE, 56)
        counts: Dict[int, int] = {}
        for m in active:
            counts[m] = int.from_bytes(raw_counts[m * 2: m * 2 + 2], "little")
        return AutoPushConfig(
            active_modules=active,
            has_resultant=bool(data_type & registers.DATA_TYPE_RESULTANT),
            has_distributed=bool(data_type & registers.DATA_TYPE_DISTRIBUTED),
            point_counts=counts,
        )

    # ---- Auto-push controls -----------------------------------------------

    def enable_auto_push(self) -> None:
        self.write_register(registers.REG_AUTO_PUSH, b"\x01", response_head=RESP_HEAD_AUTO_PUSH)

    def disable_auto_push(self) -> None:
        req = build_simple_request(FUNC_WRITE_SIMPLE, registers.REG_AUTO_PUSH, data=b"\x00")
        try:
            self.transport.write(req)
            time.sleep(0.05)
            try:
                self.transport.read_until_idle(timeout=0.2)
            except PaxiniTimeoutError:
                pass
        except Exception:
            pass

    def calibrate(self) -> None:
        """Trigger sensor calibration on the high-speed board.

        Mirrors the vendor host-app's 标定 (Calibrate) button. Sends the
        custom frame ``55AA001702000100 01 E6`` (FC=0x17, reg=0x0002,
        data=[0x01]); the board zeros its baseline at the currently applied
        load. Vendor UI considers a response data byte of 0x00 as success;
        anything else is an error.

        Authority: vendor Hand_UI.py::start_calibration (lines ~1339-1373),
        which hardcodes this exact frame.
        """
        req = build_simple_request(FUNC_HS_CALIBRATION, 0x0002, data=b"\x01")
        raw = self.transport.transaction(
            req, expected_head=RESP_HEAD_GENERAL,
            response_delay=0.1, timeout=self.response_timeout,
        )
        resp = parse_simple_response(raw)
        if resp.func_code != FUNC_HS_CALIBRATION:
            raise FrameError(
                f"unexpected calibration response func code "
                f"0x{resp.func_code:02X} (wanted 0x17)"
            )
        if resp.data != b"\x00":
            raise DeviceError(
                f"calibration failed, response data {resp.data.hex()}",
                code=resp.data[0] if resp.data else 0xFF,
            )

    def reset_board(self) -> None:
        try:
            req = build_simple_request(FUNC_WRITE_SIMPLE, registers.REG_SYSTEM_RESET, data=b"\x01")
            self.transport.write(req)
        except Exception:
            pass

    # ---- One-shot resultant-force reads -----------------------------------

    def read_resultant_forces(self) -> Dict[str, Tuple[int, int, int]]:
        """Read resultant forces for every active module (one-shot, no auto-push).

        Reads 0x0500 + 6*module_idx for each active module. Returns a dict
        keyed by module name with (Fx, Fy, Fz) LSB counts.
        """
        active = self.read_active_modules()
        out: Dict[str, Tuple[int, int, int]] = {}
        for m in active:
            addr = registers.REG_MODULE_FORCES_BASE + m * 6
            data = self.read_register(addr, 6)
            out[registers.MODULE_NAMES[m]] = _decode_resultant_6bytes(data)
        return out

    def read_resultant_forces_newtons(self) -> Dict[str, Tuple[float, float, float]]:
        return {k: _to_newtons_triple(v) for k, v in self.read_resultant_forces().items()}

    # ---- Auto-push streaming ----------------------------------------------

    def stream_auto_push(
        self,
        *,
        duration: Optional[float] = None,
        max_frames: Optional[int] = None,
        per_frame_timeout: float = 0.5,
        config: Optional[AutoPushConfig] = None,
    ) -> Iterator[AutoPushFrame]:
        """Yield AutoPushFrame objects until duration / max_frames.

        Reads the board's auto-push config once at the start (unless one is
        passed in), then enables auto-push and decodes each frame against it.
        """
        if config is None:
            config = self.read_auto_push_config()
        self.enable_auto_push()
        start = time.monotonic()
        produced = 0
        try:
            while True:
                if duration is not None and time.monotonic() - start >= duration:
                    return
                if max_frames is not None and produced >= max_frames:
                    return
                try:
                    # Length-based read: ~3x faster than read_until_head's
                    # idle-gap framing. See transport.read_auto_push_frame.
                    raw = self.transport.read_auto_push_frame(
                        timeout=per_frame_timeout
                    )
                except PaxiniTimeoutError:
                    continue
                try:
                    parsed = parse_auto_push(raw)
                except FrameError:
                    continue
                produced += 1
                yield AutoPushFrame(
                    config=config,
                    error_code=parsed.error_code,
                    valid_data=parsed.valid_data,
                    raw=parsed.raw,
                )
        finally:
            self.disable_auto_push()


# ---- Backwards-compat aliases for older tests / external callers -----------
# These wrap the new helpers in the older multi-module shape:
#   _decode_module_forces_lowbyte(data) -> [(fx, fy, fz), ...]
#   _to_newtons(list_of_triples)         -> list of newton triples


def _decode_module_forces_lowbyte(data: bytes):
    """Multi-module wrapper around :func:`_decode_resultant_6bytes`.

    Decodes ``min(len(data)//6, MODULE_COUNT)`` consecutive 6-byte blocks,
    each as one module's resultant force per the vendor low-byte rule.

    Useful for tests that assert byte-layout invariants without needing a
    full AutoPushConfig. Production callers should prefer
    :meth:`AutoPushFrame.resultant_forces` because that respects the
    active-modules bitmap and the data-type bits.
    """
    n = min(len(data) // 6, registers.MODULE_COUNT)
    return [_decode_resultant_6bytes(data[i * 6: i * 6 + 6]) for i in range(n)]


def _to_newtons(forces):
    """Apply the 0.1 N/LSB scale to a list of (fx, fy, fz) triples."""
    return [_to_newtons_triple(t) for t in forces]
