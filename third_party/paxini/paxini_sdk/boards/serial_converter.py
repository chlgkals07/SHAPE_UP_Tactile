"""High-level driver for the single-channel **Serial Converter Board**.

Mirrors the protocol used by the vendor's official ``Read_Single_Sensor_Usb.py``
and ``USB_UI.py`` example programs, but exposes it as a clean object-oriented
API and adds Mac-friendly defaults (cu.* device paths).

The Serial Converter Board carries exactly one PX-6AX GEN3 sensor and speaks
the request/response ("fin_master") protocol of section 3 of the GEN3
Communication Board protocol PDF. Unlike the High-Speed Communication Board it
has **no auto-push mode** (protocol section 3.1: "This protocol can only be
executed through the request -> return mode") and **no point-count register** -
the host must know how many distributed-force points the attached sensor has.
The vendor's ``USB_UI.py`` makes the operator pick the sensor model from a
dropdown and type the byte length by hand for exactly this reason.

Typical use::

    from paxini_sdk import SingleSensorBoard, list_serial_ports

    print("\\n".join(str(p) for p in list_serial_ports()))

    # Tell the board which sensor is attached so distributed-force reads
    # use the right length. Either a vendor part code or an explicit count:
    with SingleSensorBoard("/dev/cu.usbserial-XXXX", sensor="PXSR-STDDP03G") as board:
        board.calibrate()
        fx, fy, fz = board.read_resultant_force()
        print(f"Resultant force: Fx={fx} Fy={fy} Fz={fz}")

        points = board.read_distributed_force()   # length comes from `sensor`
        print(f"Got {len(points)} 3-axis points")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from .. import registers
from ..exceptions import DeviceError, FrameError
from ..protocol import (
    FIN_FUNC_CALIBRATION,
    FIN_FUNC_FORCE,
    build_fin_request,
    fin_error_name,
    parse_fin_response,
    split_force_xyz,
)
from ..transport import SerialTransport


@dataclass
class DistributedPoint:
    """One sample point from the distributed-force grid."""

    fx: int  # signed -128..127
    fy: int
    fz: int  # unsigned 0..255

    def as_tuple(self) -> Tuple[int, int, int]:
        return (self.fx, self.fy, self.fz)


def _resolve_n_points(
    sensor: Optional[Union[str, "object"]],
    n_points: Optional[int],
) -> Optional[int]:
    """Work out the distributed-force point count for the attached sensor.

    Priority: explicit ``n_points`` > ``sensor`` lookup in the registry >
    ``None`` (unknown - read_distributed_force will then require an argument).
    """
    if n_points is not None:
        if n_points <= 0:
            raise ValueError(f"n_points must be positive, got {n_points}")
        return int(n_points)
    if sensor is None:
        return None
    from .. import sensor_registry

    if isinstance(sensor, sensor_registry.SensorVariant):
        return sensor.n_points
    if isinstance(sensor, str):
        variant = sensor_registry.find_by_part_code(sensor)
        if variant is None:
            raise KeyError(
                f"unknown sensor part code {sensor!r}; known codes: "
                f"{[s.vendor_part_code for s in sensor_registry.list_sensors()]}"
            )
        return variant.n_points
    raise TypeError(
        f"sensor must be a part-code str or SensorVariant, got {type(sensor).__name__}"
    )


class SingleSensorBoard:
    """Driver for the Serial Converter Board (one PX-6AX GEN3 sensor)."""

    DEFAULT_BAUDRATE = 921600

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        *,
        device_id: int = 0x01,
        sensor: Optional[Union[str, object]] = None,
        n_points: Optional[int] = None,
        response_timeout: float = 0.5,
    ):
        """
        Parameters
        ----------
        port, baudrate:
            Serial port path and baud rate (vendor default 921600).
        device_id:
            Slave/device address. Per protocol section 3.1 this equals the
            sensor's module number + 1; ``0x01`` is correct for a sensor on
            the default CN1 port with module number 0.
        sensor:
            Optional vendor part code (e.g. ``"PXSR-STDDP03G"``) or a
            ``sensor_registry.SensorVariant``. Used to look up the
            distributed-force point count, since the board cannot report it.
        n_points:
            Explicit distributed-force point count. Overrides ``sensor`` if
            both are given. Leave unset (and omit ``sensor``) only if you
            will always pass ``point_count`` to ``read_distributed_force``.
        response_timeout:
            Per-transaction read timeout in seconds.
        """
        self.transport = SerialTransport(port, baudrate)
        self.device_id = device_id
        self.response_timeout = response_timeout
        self._n_points: Optional[int] = _resolve_n_points(sensor, n_points)
        self._warned_read_status = False

    @property
    def n_points(self) -> Optional[int]:
        """Distributed-force point count this board was configured with, or
        ``None`` if it was not supplied at construction time."""
        return self._n_points

    # ---- lifecycle ---------------------------------------------------------

    def open(self) -> "SingleSensorBoard":
        self.transport.open()
        return self

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> "SingleSensorBoard":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ---- low-level read/write ---------------------------------------------

    def _read(self, addr: int, length: int) -> bytes:
        req = build_fin_request(
            FIN_FUNC_FORCE, addr, read=True, data_len=length, device_id=self.device_id
        )
        raw = self.transport.fin_transaction(req, timeout=self.response_timeout)
        resp = parse_fin_response(raw)
        # The Serial Converter Board firmware stamps ERR_LEN (0x01) on every
        # read response even though the payload is valid - confirmed on
        # hardware (PXSR-STDDP03A, 2026-05-19) and consistent with the vendor
        # USB_UI.py never checking the status byte. So ERR_SUC and ERR_LEN are
        # both accepted; any other status is a genuine failure and raises.
        # verify_lrc() in parse_fin_response still rejects corrupt frames.
        if resp.status not in (0x00, 0x01):
            raise DeviceError(
                f"read at 0x{addr:08X} returned status 0x{resp.status:02X} "
                f"({fin_error_name(resp.status)})",
                code=resp.status,
            )
        if resp.status != 0 and not self._warned_read_status:
            logging.getLogger(__name__).warning(
                "Serial Converter Board read returned status %s (0x%02X); "
                "payload is still used (the vendor host app ignores this "
                "byte). Further occurrences suppressed.",
                fin_error_name(resp.status), resp.status,
            )
            self._warned_read_status = True
        if len(resp.data) < length:
            raise FrameError(
                f"expected {length} data bytes, got {len(resp.data)}"
            )
        return resp.data[:length]

    def _write(self, func_code: int, addr: int, data: bytes) -> None:
        req = build_fin_request(
            func_code, addr, read=False, data=data, device_id=self.device_id
        )
        raw = self.transport.fin_transaction(req, timeout=self.response_timeout)
        resp = parse_fin_response(raw)
        if resp.status != 0:
            raise DeviceError(
                f"write to 0x{addr:08X} returned status 0x{resp.status:02X} "
                f"({fin_error_name(resp.status)})",
                code=resp.status,
            )

    # ---- high-level operations --------------------------------------------

    def calibrate(self) -> None:
        """Trigger sensor calibration. Place the sensor in its zero-load
        condition before calling - readings will be referenced to this state.

        Vendor frame (Read_Single_Sensor_Usb.py / USB_UI.py):
        ``55 AA 0A 00 01 00 79 03 00 00 00 01 00 01 78``."""
        self._write(FIN_FUNC_CALIBRATION, registers.FIN_ADDR_CALIBRATION, b"\x01")

    def read_resultant_force(self) -> Tuple[int, int, int]:
        """Read the 3-byte aggregated (Fx, Fy, Fz) force vector.

        Fx and Fy are signed (two's complement, -128..127). Fz is unsigned
        (0..255). Units are sensor counts; convert to engineering units using
        the per-sensor calibration coefficients from the vendor.

        Vendor frame: ``55 AA 09 00 01 00 FB F0 03 00 00 03 00 06`` -
        read 3 bytes at 0x03F0.
        """
        data = self._read(registers.FIN_ADDR_RESULTANT_FORCE, 3)
        return split_force_xyz(data)

    def read_distributed_force(
        self, point_count: Optional[int] = None
    ) -> List[DistributedPoint]:
        """Read the distributed-force grid.

        Each measurement point is 3 bytes: (Fx, Fy, Fz). Fx/Fy are signed
        int8, Fz is unsigned uint8 - the same convention as
        :meth:`read_resultant_force`.

        Parameters
        ----------
        point_count:
            Number of measurement points to read. If omitted, the count
            supplied at construction (``sensor=`` or ``n_points=``) is used.
            A ``ValueError`` is raised if neither is available - the Serial
            Converter Board has no point-count register, so the count must
            come from the host (see the module docstring).

        Vendor frame: ``55 AA 09 00 01 00 FB 0E 04 00 00 <len_lo> <len_hi> ..``
        - read ``point_count*3`` bytes at 0x040E.
        """
        n = point_count if point_count is not None else self._n_points
        if n is None:
            raise ValueError(
                "distributed-force point count is unknown. Pass point_count=, "
                "or construct SingleSensorBoard(sensor='PXSR-...') or "
                "SingleSensorBoard(n_points=...). The Serial Converter Board "
                "does not report this value."
            )
        if n <= 0:
            raise ValueError(f"point_count must be positive, got {n}")
        n_bytes = n * 3
        data = self._read(registers.FIN_ADDR_DISTRIBUTED_FORCE, n_bytes)
        out: List[DistributedPoint] = []
        for i in range(0, n_bytes, 3):
            fx_raw, fy_raw, fz_raw = data[i], data[i + 1], data[i + 2]
            fx = fx_raw - 256 if fx_raw >= 128 else fx_raw
            fy = fy_raw - 256 if fy_raw >= 128 else fy_raw
            out.append(DistributedPoint(fx=fx, fy=fy, fz=fz_raw))
        return out
