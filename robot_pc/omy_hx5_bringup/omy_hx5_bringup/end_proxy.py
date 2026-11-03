"""HX5 access through the OMY END (ID 210) Table Sync buffer.

The END controller is the only device directly addressed on /dev/ttyAMA4.
Its Tool ID selects the downstream HX5 controller (ID 140). The probe entry
point never sends a motor goal. END settings are restored after a session.
Do not run while another process owns the END serial port.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import time
from contextlib import contextmanager
from struct import pack

END_ID = 210
HAND_ID = 140
END_MODEL = 230
LEFT_HAND_MODEL = 261

# END control-table addresses (ROBOTIS OMY Unit Control Table).
TOOL_ID = 13
SYNC_ENABLE = 46
READ_ADDRESS_1 = 48
READ_ADDRESS_2 = 50
READ_SIZE_1 = 52
READ_SIZE_2 = 54
WRITE_ADDRESS_1 = 56
WRITE_ADDRESS_2 = 58
WRITE_SIZE_1 = 60
WRITE_SIZE_2 = 62
READ_BUFFER = 72
WRITE_BUFFER = 200
COMM_RX_TIMEOUT = -3001

SAVED_REGISTERS = (
    (TOOL_ID, 1), (SYNC_ENABLE, 1),
    (READ_ADDRESS_1, 2), (READ_ADDRESS_2, 2),
    (READ_SIZE_1, 2), (READ_SIZE_2, 2),
    (WRITE_ADDRESS_1, 2), (WRITE_ADDRESS_2, 2),
    (WRITE_SIZE_1, 2), (WRITE_SIZE_2, 2),
)


class EndProxyError(RuntimeError):
    """A serial or proxy read did not return a valid response."""


def acquire_end_bus_lock() -> int:
    """Prevent this package's probes and hand controllers sharing the END port."""
    fd = os.open("/tmp/omy_hx5_end_210.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise EndProxyError("END 210 port is owned by another OMY/HX5 process") from exc
    return fd


class EndProxy:
    def __init__(self, port, packet, *, sleep=time.sleep):
        self.port = port
        self.packet = packet
        self.sleep = sleep
        self._current = {}
        self._original_write_buffer = None
        self.end_write_ack_timeouts = 0

    def read(self, address: int, size: int, *, device_id: int = END_ID) -> bytes:
        data, result, error = self.packet.readTxRx(self.port, device_id, address, size)
        if result != 0 or error or len(data) != size:
            raise EndProxyError(
                f"ID {device_id} read {address}+{size} failed: "
                f"result={self.packet.getTxRxResult(result)}, error={error}, "
                f"received={len(data)} bytes"
            )
        return bytes(data)

    def write_end(self, address: int, size: int, value: int) -> None:
        if self._current.get(address) == value:
            return
        result, error = self.packet.writeTxRx(
            self.port, END_ID, address, size, list(value.to_bytes(size, "little"))
        )
        if result == COMM_RX_TIMEOUT and not error:
            # An END register write can complete even if its status packet is lost.
            # Never retry an uncertain write: read the actual register first.
            self.sleep(0.05)
            try:
                actual = int.from_bytes(self.read(address, size), "little")
            except EndProxyError as exc:
                raise EndProxyError(
                    f"END 210 write {address} had no status packet and "
                    f"readback failed: {exc}"
                ) from exc
            if actual == value:
                self._current[address] = value
                self.end_write_ack_timeouts += 1
                return
            raise EndProxyError(
                f"END 210 write {address} had no status packet; "
                f"readback={actual}, requested={value}"
            )
        if result != 0 or error:
            raise EndProxyError(
                f"END 210 write {address} failed: "
                f"result={self.packet.getTxRxResult(result)}, error={error}"
            )
        self._current[address] = value

    def write_end_buffer(self, data: bytes) -> None:
        """Fill END's local buffer while forwarding is disabled."""
        if not 1 <= len(data) <= 128 or self._current.get(SYNC_ENABLE) != 0:
            raise ValueError("END write buffer requires disabled Table Sync and 1..128 bytes")
        if self._original_write_buffer is None:
            self._original_write_buffer = self.read(WRITE_BUFFER, 128)
        result, error = self.packet.writeTxRx(
            self.port, END_ID, WRITE_BUFFER, len(data), list(data)
        )
        if result != 0 or error:
            raise EndProxyError(
                f"END write buffer failed: result={self.packet.getTxRxResult(result)}, "
                f"error={error}"
            )

    def write_end_buffer_live(self, data: bytes) -> None:
        """Update an already configured END forwarding window."""
        if (self._original_write_buffer is None or
                self._current.get(SYNC_ENABLE) != 1 or
                self._current.get(WRITE_SIZE_1) != len(data) or
                not 1 <= len(data) <= 128):
            raise EndProxyError("END live write window is not prepared")
        result, error = self.packet.writeTxRx(
            self.port, END_ID, WRITE_BUFFER, len(data), list(data)
        )
        if result != 0 or error:
            raise EndProxyError(
                f"END live write failed: result={self.packet.getTxRxResult(result)}, "
                f"error={error}"
            )

    @contextmanager
    def temporary_read_window(self, *, tool_id: int = HAND_ID):
        """Save END settings; disable its write slots; always restore them."""
        if not 0 <= tool_id <= 252:
            raise ValueError("tool_id must be a valid DYNAMIXEL ID")
        original = {
            address: int.from_bytes(self.read(address, size), "little")
            for address, size in SAVED_REGISTERS
        }
        if (original[TOOL_ID] == HAND_ID and original[SYNC_ENABLE] == 1 and
                (original[WRITE_SIZE_1] or original[WRITE_SIZE_2])):
            raise EndProxyError(
                "END 210 has an active HX5 write window from a prior run; "
                "recover it before probing or launching")
        self._current = original.copy()
        self._original_write_buffer = None
        try:
            self.write_end(SYNC_ENABLE, 1, 0)
            self.write_end(WRITE_SIZE_1, 2, 0)
            self.write_end(WRITE_SIZE_2, 2, 0)
            self.write_end(TOOL_ID, 1, tool_id)
            self.write_end(READ_SIZE_2, 2, 0)
            yield
        finally:
            # Disable forwarding first. Restore addresses and sizes while off.
            self.write_end(SYNC_ENABLE, 1, 0)
            if self._original_write_buffer is not None:
                self.write_end_buffer(self._original_write_buffer)
            for address, size in SAVED_REGISTERS:
                if address != SYNC_ENABLE:
                    self.write_end(address, size, original[address])
            self.write_end(SYNC_ENABLE, 1, original[SYNC_ENABLE])

    def read_hand(self, address: int, size: int, *, stable: bool = False) -> bytes:
        """Read the selected END tool ID through its read-only buffer."""
        if not (0 <= address <= 1023 and 1 <= size <= 128
                and address + size <= 1024):
            raise ValueError("END can proxy only 1..128 bytes within hand address 0..1023")
        self.write_end(SYNC_ENABLE, 1, 0)
        self.write_end(READ_ADDRESS_1, 2, address)
        self.write_end(READ_SIZE_1, 2, size)
        self.write_end(SYNC_ENABLE, 1, 1)
        # END Table Sync is asynchronous. Permit at least one refresh cycle.
        self.sleep(0.15)
        first = self.read(READ_BUFFER, size)
        self.sleep(0.05)
        second = self.read(READ_BUFFER, size)
        if stable and first != second:
            raise EndProxyError("END proxy read was unstable; no hand state accepted")
        return second

    def write_hand(self, address: int, data: bytes) -> None:
        """Forward a bounded write to the selected tool, then read it back.

        The caller must hold temporary_read_window(). This is for explicit
        configuration and must never be called for a motor goal on startup.
        """
        if not (0 <= address <= 1023 and 1 <= len(data) <= 128
                and address + len(data) <= 1024):
            raise ValueError("END can proxy only 1..128 bytes within address 0..1023")
        self.write_end(SYNC_ENABLE, 1, 0)
        self.write_end(READ_ADDRESS_1, 2, address)
        self.write_end(READ_SIZE_1, 2, len(data))
        self.write_end(WRITE_ADDRESS_1, 2, address)
        self.write_end(WRITE_SIZE_1, 2, len(data))
        self.write_end_buffer(data)
        try:
            self.write_end(SYNC_ENABLE, 1, 1)
            self.sleep(0.20)
            self.read(READ_BUFFER, len(data))
            self.sleep(0.05)
            echoed = self.read(READ_BUFFER, len(data))
        finally:
            self.write_end(SYNC_ENABLE, 1, 0)
            self.write_end(WRITE_SIZE_1, 2, 0)
        if echoed != data:
            raise EndProxyError(
                f"ID {self._current[TOOL_ID]} write {address}+{len(data)} "
                f"did not verify: {echoed.hex()} != {data.hex()}"
            )

    def probe(self) -> dict[str, int]:
        model, result, error = self.packet.ping(self.port, END_ID)
        if result != 0 or error or model != END_MODEL:
            raise EndProxyError(
                f"END 210 did not identify as model {END_MODEL}: "
                f"model={model}, result={self.packet.getTxRxResult(result)}, error={error}"
            )
        with self.temporary_read_window():
            model = int.from_bytes(self.read_hand(0, 2, stable=True), "little")
            if model != LEFT_HAND_MODEL:
                raise EndProxyError(
                    f"END 210 did not forward left HX5 model {LEFT_HAND_MODEL}; "
                    f"read model={model}"
                )
            voltage = int.from_bytes(self.read_hand(102, 2), "little")
            status = self.read_hand(106, 1)[0]
        return {"end_model": END_MODEL, "hand_model": model,
                "hand_voltage_centivolts": voltage, "hand_status": status}

    def probe_motor(self, motor_id: int) -> dict[str, int | tuple[int, int]]:
        """Check one internal hand actuator with no actuator register writes."""
        if motor_id != 141:
            raise ValueError("only motor ID 141 is allowed in this one-time probe")
        model, result, error = self.packet.ping(self.port, END_ID)
        if result != 0 or error or model != END_MODEL:
            raise EndProxyError("END 210 did not respond before motor probe")
        with self.temporary_read_window(tool_id=motor_id):
            returned_id = self.read_hand(7, 1, stable=True)[0]
            model = int.from_bytes(self.read_hand(0, 2, stable=True), "little")
            if returned_id != motor_id or model in (0, LEFT_HAND_MODEL, 0xFFFF):
                raise EndProxyError(
                    f"motor ID {motor_id} did not reply through END: "
                    f"read ID={returned_id}, model={model}"
                )
            drive_mode, operating_mode = self.read_hand(10, 2, stable=True)
            torque = self.read_hand(64, 1)[0]
            indirect = self.read_hand(168, 4, stable=True)
        return {
            "model": model,
            "drive_mode": drive_mode,
            "operating_mode": operating_mode,
            "torque_enabled": torque,
            "indirect_address_1_2": (
                int.from_bytes(indirect[:2], "little"),
                int.from_bytes(indirect[2:], "little"),
            ),
        }

    def _write_hand_indirect(self, data: bytes) -> None:
        """Write five HX5 indirect aliases through END, then verify them."""
        if len(data) != 10:
            raise ValueError("only five 2-byte indirect addresses are allowed")
        self.write_end(SYNC_ENABLE, 1, 0)
        self.write_end(READ_ADDRESS_1, 2, 122)
        self.write_end(READ_SIZE_1, 2, 10)
        self.write_end(WRITE_ADDRESS_1, 2, 122)
        self.write_end(WRITE_SIZE_1, 2, 10)
        self.write_end_buffer(data)
        self.write_end(SYNC_ENABLE, 1, 1)
        self.sleep(0.2)
        forwarded = self.read(READ_BUFFER, 10)
        self.write_end(SYNC_ENABLE, 1, 0)
        self.write_end(WRITE_SIZE_1, 2, 0)
        if forwarded != data:
            raise EndProxyError(
                f"HX5 indirect address write did not verify: {forwarded.hex()} "
                f"!= {data.hex()}"
            )

    @contextmanager
    def preset_session(self):
        """Own the END port for HX5 preset commands, restoring both devices on exit.

        Entering this session changes only END configuration. The five HX5
        indirect aliases are installed lazily on the first motion request.
        """
        model, result, error = self.packet.ping(self.port, END_ID)
        if result != 0 or error or model != END_MODEL:
            raise EndProxyError("END 210 did not respond before preset bringup")
        with self.temporary_read_window():
            hand_model = int.from_bytes(self.read_hand(0, 2, stable=True), "little")
            mode = self.read_hand(33, 1, stable=True)[0]
            table_sync = self.read_hand(70, 1, stable=True)[0]
            voltage = int.from_bytes(self.read_hand(102, 2), "little")
            status = self.read_hand(106, 1)[0]
            if hand_model != LEFT_HAND_MODEL or mode != 1 or table_sync != 0 or status:
                raise EndProxyError(
                    f"left HX5 is not ready for preset control: model={hand_model}, "
                    f"mode={mode}, TableSync Enable={table_sync}, status={status}"
                )
            self._preset_original_aliases = None
            try:
                self._preset_active = True
                yield {"hand_model": hand_model, "mode": mode,
                       "voltage_centivolts": voltage, "status": status}
            finally:
                self._preset_active = False
                if self._preset_original_aliases is not None:
                    self._write_hand_indirect(self._preset_original_aliases)
                    if self.read_hand(122, 10, stable=True) != self._preset_original_aliases:
                        raise EndProxyError("HX5 preset alias restoration did not verify")
                self._preset_original_aliases = None

    def send_preset(self, *, index: int, percent: int, duration_ms: int) -> None:
        """Forward one bounded preset request through END to HX5 ID 140."""
        if not getattr(self, "_preset_active", False):
            raise EndProxyError("preset session is not active")
        if not 0 <= index <= 2 or not 0 <= percent <= 100 or not 1 <= duration_ms <= 32737:
            raise ValueError("preset requires index 0..2, percent 0..100, time 1..32737 ms")
        if self._preset_original_aliases is None:
            self._preset_original_aliases = self.read_hand(122, 10, stable=True)
            preset_aliases = pack("<5H", 2016, 2017, 2018, 2019, 100)
            self._write_hand_indirect(preset_aliases)
            if self.read_hand(122, 10, stable=True) != preset_aliases:
                raise EndProxyError("HX5 preset aliases did not verify")
        data = bytes((index, percent)) + duration_ms.to_bytes(2, "little")
        self.write_end(SYNC_ENABLE, 1, 0)
        self.write_end(READ_ADDRESS_1, 2, 634)
        self.write_end(READ_SIZE_1, 2, 4)
        self.write_end(WRITE_ADDRESS_1, 2, 634)
        self.write_end(WRITE_SIZE_1, 2, 4)
        self.write_end_buffer(data)
        try:
            self.write_end(SYNC_ENABLE, 1, 1)
            self.sleep(0.15)
        finally:
            # Never leave a repeating goal write in END's Table Sync loop.
            self.write_end(SYNC_ENABLE, 1, 0)
            self.write_end(WRITE_SIZE_1, 2, 0)
        self.write_end(SYNC_ENABLE, 1, 1)
        if self.read(READ_BUFFER, 4) != data:
            raise EndProxyError("HX5 preset registers did not echo the requested values")

    def inspect_sync_ids(self) -> tuple[int, tuple[int, ...]]:
        """Read high TableSync IDs without changing the hand's operating mode."""
        model, result, error = self.packet.ping(self.port, END_ID)
        if result != 0 or error or model != END_MODEL:
            raise EndProxyError("END 210 did not respond before TableSync inspection")
        with self.temporary_read_window():
            model = int.from_bytes(self.read_hand(0, 2, stable=True), "little")
            if model != LEFT_HAND_MODEL:
                raise EndProxyError(f"expected left HX5 model 261, got {model}")
            mode = self.read_hand(33, 1)[0]
            enabled = self.read_hand(70, 1)[0]
            if mode not in (0, 1) or enabled != 0:
                raise EndProxyError(
                    f"hand is not idle for TableSync inspection: mode={mode}, "
                    f"TableSync Enable={enabled}"
                )
            original = self.read_hand(122, 10, stable=True)
            mapped = pack("<5H", 1024, 1025, 1026, 1027, 1028)
            try:
                self._write_hand_indirect(mapped)
                ids = tuple(self.read_hand(634, 5, stable=True))
            finally:
                self._write_hand_indirect(original)
                restored = self.read_hand(122, 10, stable=True)
                if restored != original:
                    raise EndProxyError("HX5 indirect address restoration did not verify")
        return mode, ids


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyAMA4")
    parser.add_argument("--baud", type=int, default=4_000_000)
    parser.add_argument("--motor-id", type=int, choices=(141,),
                        help="read only the left thumb actuator ID 141 through END")
    parser.add_argument("--inspect-sync-ids", action="store_true",
                        help="temporarily map five hand EEPROM aliases to read high TableSync IDs")
    args = parser.parse_args(argv)
    if args.motor_id is not None and args.inspect_sync_ids:
        parser.error("choose only one inspection mode")

    try:
        from dynamixel_sdk import PacketHandler, PortHandler
    except ModuleNotFoundError as exc:
        if exc.name == "serial":
            parser.exit(1, "Missing pyserial in the Robot PC container; "
                        "install python3-serial, then retry\n")
        raise

    try:
        lock_fd = acquire_end_bus_lock()
    except EndProxyError as exc:
        parser.exit(1, f"END proxy probe failed: {exc}\n")
    port = PortHandler(args.port)
    if not port.openPort():
        parser.exit(1, f"Cannot open {args.port}; stop other END owners first\n")
    try:
        if not port.setBaudRate(args.baud):
            parser.exit(1, f"Cannot set {args.port} to {args.baud} baud\n")
        proxy = EndProxy(port, PacketHandler(2.0))
        if args.inspect_sync_ids:
            mode, ids = proxy.inspect_sync_ids()
            print(f"HX5 mode {mode}; TableSync1 IDs via END 210: {list(ids)}. "
                  "Five indirect addresses restored; no motor command sent.")
        elif args.motor_id is None:
            result = proxy.probe()
            print(
                f"END {END_ID}: model {result['end_model']} OK; "
                f"left HX5 via END: ID {HAND_ID}, model {result['hand_model']} OK; "
                f"voltage {result['hand_voltage_centivolts'] / 100:.2f} V; "
                f"status {result['hand_status']}. No hand command sent."
            )
        else:
            motor = proxy.probe_motor(args.motor_id)
            print(f"END {END_ID} -> motor ID {args.motor_id}: "
                  f"model {motor['model']}, drive mode {motor['drive_mode']}, "
                  f"operating mode {motor['operating_mode']}, "
                  f"torque {motor['torque_enabled']}, "
                  f"indirect address 1/2 {motor['indirect_address_1_2']}. "
                  "No hand command sent.")
        return 0
    except EndProxyError as exc:
        parser.exit(1, f"END proxy probe failed: {exc}\n")
    finally:
        port.closePort()
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
