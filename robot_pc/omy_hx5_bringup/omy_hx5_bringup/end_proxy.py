"""Read-only HX5 checks through the OMY END (ID 210) Table Sync buffer.

The END controller is the only device directly addressed on /dev/ttyAMA4.
Its Tool ID selects the downstream HX5 controller (ID 140). This probe never
writes a hand register or sends a goal position. END settings are restored even
if a read fails. Do not run while another process owns the END serial port.
"""

from __future__ import annotations

import argparse
import time
from contextlib import contextmanager

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
WRITE_SIZE_1 = 60
WRITE_SIZE_2 = 62
READ_BUFFER = 72

SAVED_REGISTERS = (
    (TOOL_ID, 1), (SYNC_ENABLE, 1),
    (READ_ADDRESS_1, 2), (READ_ADDRESS_2, 2),
    (READ_SIZE_1, 2), (READ_SIZE_2, 2),
    (WRITE_SIZE_1, 2), (WRITE_SIZE_2, 2),
)


class EndProxyError(RuntimeError):
    """A serial or proxy read did not return a valid response."""


class EndProxy:
    def __init__(self, port, packet, *, sleep=time.sleep):
        self.port = port
        self.packet = packet
        self.sleep = sleep
        self._current = {}

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
        if result != 0 or error:
            raise EndProxyError(
                f"END 210 write {address} failed: "
                f"result={self.packet.getTxRxResult(result)}, error={error}"
            )
        self._current[address] = value

    @contextmanager
    def temporary_read_window(self):
        """Save END settings; disable its write slots; always restore them."""
        original = {
            address: int.from_bytes(self.read(address, size), "little")
            for address, size in SAVED_REGISTERS
        }
        self._current = original.copy()
        try:
            self.write_end(SYNC_ENABLE, 1, 0)
            self.write_end(WRITE_SIZE_1, 2, 0)
            self.write_end(WRITE_SIZE_2, 2, 0)
            self.write_end(TOOL_ID, 1, HAND_ID)
            self.write_end(READ_SIZE_2, 2, 0)
            yield
        finally:
            # Disable forwarding first. Restore addresses and sizes while off.
            self.write_end(SYNC_ENABLE, 1, 0)
            for address, size in SAVED_REGISTERS:
                if address != SYNC_ENABLE:
                    self.write_end(address, size, original[address])
            self.write_end(SYNC_ENABLE, 1, original[SYNC_ENABLE])

    def read_hand(self, address: int, size: int, *, stable: bool = False) -> bytes:
        """Map one HX5 control-table read into END's read-only buffer."""
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyAMA4")
    parser.add_argument("--baud", type=int, default=4_000_000)
    args = parser.parse_args(argv)

    try:
        from dynamixel_sdk import PacketHandler, PortHandler
    except ModuleNotFoundError as exc:
        if exc.name == "serial":
            parser.exit(1, "Missing pyserial in the Robot PC container; "
                        "install python3-serial, then retry\n")
        raise

    port = PortHandler(args.port)
    if not port.openPort():
        parser.exit(1, f"Cannot open {args.port}; stop other END owners first\n")
    try:
        if not port.setBaudRate(args.baud):
            parser.exit(1, f"Cannot set {args.port} to {args.baud} baud\n")
        result = EndProxy(port, PacketHandler(2.0)).probe()
        print(
            f"END {END_ID}: model {result['end_model']} OK; "
            f"left HX5 via END: ID {HAND_ID}, model {result['hand_model']} OK; "
            f"voltage {result['hand_voltage_centivolts'] / 100:.2f} V; "
            f"status {result['hand_status']}. No hand command sent."
        )
        return 0
    except EndProxyError as exc:
        parser.exit(1, f"END proxy probe failed: {exc}\n")
    finally:
        port.closePort()


if __name__ == "__main__":
    raise SystemExit(main())
