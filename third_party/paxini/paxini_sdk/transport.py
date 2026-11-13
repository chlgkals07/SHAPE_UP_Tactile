"""Serial transport layer.

Wraps :mod:`pyserial` with helpers for the read patterns the GEN3 boards
require (idle-based framing, head-based seeking) and provides cross-platform
port discovery suitable for macOS.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

try:
    import serial  # type: ignore[import-not-found]
    import serial.tools.list_ports  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover - import guidance
    raise ImportError(
        "pyserial is required for transport. Install with: pip install pyserial"
    ) from exc

from .exceptions import TimeoutError as PaxiniTimeoutError


@dataclass
class PortInfo:
    device: str
    description: str
    hwid: str

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.device} — {self.description} [{self.hwid}]"


def list_serial_ports() -> List[PortInfo]:
    """Enumerate serial ports visible to the OS.

    On macOS, USB-serial bridges (CH34x / CP210x / FTDI) typically appear as
    ``/dev/tty.usbserial-XXXX`` or ``/dev/cu.usbserial-XXXX``. Both forms are
    returned; prefer ``cu.*`` for outgoing connections (it does not block on
    DCD), but ``tty.*`` works fine for the Paxini boards.
    """
    ports: List[PortInfo] = []
    for p in serial.tools.list_ports.comports():
        ports.append(PortInfo(device=p.device, description=p.description or "", hwid=p.hwid or ""))
    return ports


def find_port(query: str) -> Optional[str]:
    """Return the first port whose device path or description matches *query*.

    Useful for picking the Paxini board by hint, e.g. ``find_port("usbserial")``.
    """
    q = query.lower()
    for p in list_serial_ports():
        if q in p.device.lower() or q in p.description.lower() or q in p.hwid.lower():
            return p.device
    return None


class SerialTransport:
    """Thin context-managed wrapper around :class:`serial.Serial`.

    Implements:

    * Idle-based bursty read (``read_until_idle``) — required by the GEN3
      examples since the board uses inter-byte gaps to delimit frames.
    * Head-locked read (``read_until_head``) — buffers until the requested
      frame head appears, then waits for the burst to finish.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 921600,
        *,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: int = 1,
        timeout: float = 1.0,
        write_timeout: float = 0.5,
        inter_byte_timeout: Optional[float] = 0.001,
        rtscts: bool = False,
        xonxoff: bool = False,
    ):
        self.port = port
        self.baudrate = baudrate
        self._kwargs = dict(
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=timeout,
            write_timeout=write_timeout,
            inter_byte_timeout=inter_byte_timeout,
            rtscts=rtscts,
            xonxoff=xonxoff,
        )
        self._ser: Optional[serial.Serial] = None

    # ---- lifecycle ---------------------------------------------------------

    def open(self) -> "SerialTransport":
        if self._ser is not None and self._ser.is_open:
            return self
        self._ser = serial.Serial(self.port, self.baudrate, **self._kwargs)
        if not self._ser.is_open:
            self._ser.open()
        # Drain anything left in the OS buffer (the high-speed board may still
        # be auto-pushing from a previous session).
        try:
            self._ser.reset_input_buffer()
            self._ser.reset_output_buffer()
        except Exception:
            pass
        return self

    def close(self) -> None:
        if self._ser is not None and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None

    def __enter__(self) -> "SerialTransport":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def ser(self) -> serial.Serial:
        if self._ser is None or not self._ser.is_open:
            raise RuntimeError("transport not open — call .open() first")
        return self._ser

    # ---- I/O ---------------------------------------------------------------

    def write(self, data: bytes) -> int:
        n = self.ser.write(data)
        if n != len(data):
            raise IOError(f"short write: {n}/{len(data)} bytes")
        return n

    def reset_input(self) -> None:
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass

    def read_until_idle(self, timeout: float = 0.5, idle_gap: float = 0.005) -> bytes:
        """Accumulate bytes until ``idle_gap`` seconds elapse with no new data,
        or *timeout* total elapses.

        Raises :class:`PaxiniTimeoutError` if nothing arrives at all.
        """
        ser = self.ser
        deadline = time.monotonic() + timeout
        last_rx = time.monotonic()
        buf = bytearray()
        while time.monotonic() < deadline:
            n = ser.in_waiting
            if n:
                buf += ser.read(n)
                last_rx = time.monotonic()
            elif buf and time.monotonic() - last_rx >= idle_gap:
                return bytes(buf)
            else:
                time.sleep(0.001)
        if not buf:
            raise PaxiniTimeoutError(f"no bytes received within {timeout}s")
        return bytes(buf)


    def read_auto_push_frame(self, timeout: float = 1.0) -> bytes:
        """Fast path for High-Speed-board auto-push frames.

        Length-based read: scan for the ``AA 56`` head, parse the
        ``valid_frame_len`` field out of bytes 3-4, then read *exactly* the
        remaining bytes the frame needs. No inter-byte idle gap, no fixed
        polling sleep — pyserial's own blocking read drives the wait.

        Frame layout (per protocol PDF section 4.4.2):
            AA 56 RR FL_lo FL_hi EC | valid_data[FL-1 bytes] | LRC

        Total size = 6 + (valid_frame_len - 1) + 1 = valid_frame_len + 6.

        Returns the complete frame including head and LRC.
        Raises PaxiniTimeoutError if the head doesn't appear or the body
        does not complete in time.
        """
        ser = self.ser
        head = b"\xAA\x56"
        deadline = time.monotonic() + timeout

        # Phase 1: align on head. Read whatever's in the buffer in chunks
        # and scan for the head; discard anything before it.
        buf = bytearray()
        while time.monotonic() < deadline:
            n_waiting = ser.in_waiting
            if n_waiting:
                buf += ser.read(n_waiting)
                idx = buf.find(head)
                if idx >= 0:
                    buf = bytearray(buf[idx:])
                    break
                # Trim the buffer: keep only last byte in case head straddles reads
                if len(buf) > 1:
                    buf = bytearray(buf[-1:])
            else:
                # Use pyserial's blocking read for 1 byte instead of a Python
                # polling sleep. pyserial blocks at the OS level so this
                # doesn't burn CPU and isn't subject to Windows 15.6 ms
                # scheduler granularity.
                b = ser.read(1)
                if b:
                    buf += b
                    if buf.endswith(head):
                        buf = bytearray(head)
                        break
                    if len(buf) > 1:
                        buf = bytearray(buf[-1:])
                else:
                    # ser.read timed out without delivering a byte
                    pass
        else:
            raise PaxiniTimeoutError(
                f"auto-push head AA 56 not found within {timeout}s"
            )

        # Phase 2: read the remaining 4 bytes of the 6-byte header
        # (reserved, valid_frame_len[2], error_code).
        while len(buf) < 6 and time.monotonic() < deadline:
            need = 6 - len(buf)
            chunk = ser.read(need)
            if chunk:
                buf += chunk
        if len(buf) < 6:
            raise PaxiniTimeoutError(
                f"auto-push header truncated: got {len(buf)} of 6 bytes"
            )

        # Phase 3: parse the declared length and read the body.
        valid_frame_len = int.from_bytes(buf[3:5], "little")
        total = 6 + (valid_frame_len - 1) + 1  # header + valid_data + LRC
        if valid_frame_len <= 0 or total > 8192:
            # Sanity bound; valid_frame_len > 8 KB is implausible for any GEN3 config
            raise PaxiniTimeoutError(
                f"implausible valid_frame_len={valid_frame_len} in auto-push header"
            )

        while len(buf) < total and time.monotonic() < deadline:
            need = total - len(buf)
            chunk = ser.read(need)
            if chunk:
                buf += chunk
        if len(buf) < total:
            raise PaxiniTimeoutError(
                f"auto-push body truncated: got {len(buf)} of {total} bytes "
                f"(valid_frame_len={valid_frame_len})"
            )

        return bytes(buf[:total])

    def read_fin_response(self, timeout: float = 1.0) -> bytes:
        """Fast path for Serial Converter Board (fin_master) responses.

        Length-based read: scan for the ``AA 55`` head, parse the 2-byte
        frame-length field at bytes 2-3, then read *exactly* the rest of the
        frame. No fixed response delay and no inter-byte idle gap -- pyserial's
        OS-level blocking read drives the wait, so the call returns the instant
        the declared frame is complete.

        Frame layout (protocol PDF section 3.2)::

            AA 55 | LEN_lo LEN_hi | ... body ... | LRC

        Total size = frame_length_field + 5. Verified on hardware
        (PXSR-STDDP03A, 2026-05-19): 18-byte read response -> len field 13;
        15-byte write response -> 10; 420-byte distributed response -> 415.

        Raises PaxiniTimeoutError if the head never appears or the body does
        not complete within *timeout*.
        """
        ser = self.ser
        head = b"\xAA\x55"
        deadline = time.monotonic() + timeout

        # Phase 1: align on the AA 55 head, discarding anything before it.
        buf = bytearray()
        while time.monotonic() < deadline:
            n_waiting = ser.in_waiting
            if n_waiting:
                buf += ser.read(n_waiting)
                idx = buf.find(head)
                if idx >= 0:
                    buf = bytearray(buf[idx:])
                    break
                if len(buf) > 1:
                    buf = bytearray(buf[-1:])
            else:
                b = ser.read(1)
                if b:
                    buf += b
                    if buf.endswith(head):
                        buf = bytearray(head)
                        break
                    if len(buf) > 1:
                        buf = bytearray(buf[-1:])
        else:
            raise PaxiniTimeoutError(
                f"fin response head AA 55 not found within {timeout}s"
            )

        # Phase 2: read the rest of the 4-byte head + frame-length prefix.
        while len(buf) < 4 and time.monotonic() < deadline:
            chunk = ser.read(4 - len(buf))
            if chunk:
                buf += chunk
        if len(buf) < 4:
            raise PaxiniTimeoutError(
                f"fin response length field truncated: got {len(buf)} of 4 bytes"
            )

        # Phase 3: parse the declared length and read the remaining body.
        frame_length = int.from_bytes(buf[2:4], "little")
        total = frame_length + 5
        if frame_length <= 0 or total > 8192:
            raise PaxiniTimeoutError(
                f"implausible frame_length={frame_length} in fin response header"
            )
        while len(buf) < total and time.monotonic() < deadline:
            chunk = ser.read(total - len(buf))
            if chunk:
                buf += chunk
        if len(buf) < total:
            raise PaxiniTimeoutError(
                f"fin response body truncated: got {len(buf)} of {total} bytes "
                f"(frame_length={frame_length})"
            )
        return bytes(buf[:total])

    def fin_transaction(self, request: bytes, *, timeout: float = 1.0) -> bytes:
        """Send a fin_master request and read the length-prefixed response.

        Unlike :meth:`transaction`, there is no fixed ``response_delay`` sleep:
        :meth:`read_fin_response` blocks on pyserial's OS-level read and
        returns as soon as the declared frame length is satisfied. This is
        what lets the Serial Converter Board poll well above the ~16 Hz a
        50 ms fixed delay imposes.
        """
        self.reset_input()
        self.write(request)
        return self.read_fin_response(timeout=timeout)

    def read_until_head(
        self,
        head: bytes,
        timeout: float = 1.0,
        idle_gap: float = 0.005,
    ) -> bytes:
        """Read until *head* appears in the stream, then keep reading until
        an inter-byte idle gap. Returns bytes starting at the head.

        Useful for the High-Speed board where auto-push frames may interleave
        with command responses.
        """
        ser = self.ser
        deadline = time.monotonic() + timeout
        last_rx = time.monotonic()
        buf = bytearray()
        head_idx = -1
        while time.monotonic() < deadline:
            n = ser.in_waiting
            if n:
                buf += ser.read(n)
                last_rx = time.monotonic()
                if head_idx < 0:
                    head_idx = buf.find(head)
                if head_idx >= 0 and time.monotonic() - last_rx >= idle_gap:
                    return bytes(buf[head_idx:])
            else:
                if head_idx >= 0 and buf and time.monotonic() - last_rx >= idle_gap:
                    return bytes(buf[head_idx:])
                time.sleep(0.001)
        raise PaxiniTimeoutError(
            f"frame head {head.hex()} not found within {timeout}s "
            f"(buffered {len(buf)} bytes)"
        )

    def transaction(
        self,
        request: bytes,
        *,
        expected_head: bytes,
        response_delay: float = 0.05,
        timeout: float = 1.0,
        idle_gap: float = 0.005,
    ) -> bytes:
        """Send a frame and wait for a response that begins with *expected_head*."""
        self.reset_input()
        self.write(request)
        if response_delay > 0:
            time.sleep(response_delay)
        return self.read_until_head(expected_head, timeout=timeout, idle_gap=idle_gap)


def chunked_hex(data: Iterable[int], width: int = 16) -> str:
    """Format a byte sequence as space-separated hex with line wrapping."""
    bs = list(data)
    lines = []
    for i in range(0, len(bs), width):
        line = " ".join(f"{b:02X}" for b in bs[i : i + width])
        lines.append(f"  {i:04d}: {line}")
    return "\n".join(lines)
