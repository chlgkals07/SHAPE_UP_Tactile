"""Inspect or restore the stock OMY 3M END settings after an interrupted probe.

The target values come from the ROBOTIS omy_3m_end_unit ROS 2 control Xacro.
Only the observed interrupted state (tool 1, sync off, write slots off) may be
restored automatically. This command never writes a hand or motor goal.
"""

from __future__ import annotations

import argparse
import os

from .end_proxy import (
    END_ID, END_MODEL, EndProxy, EndProxyError, SAVED_REGISTERS,
    SYNC_ENABLE, TOOL_ID, WRITE_SIZE_1, WRITE_SIZE_2, acquire_end_bus_lock,
)


STOCK_END = {
    13: 1, 46: 1, 48: 634, 50: 0, 52: 16, 54: 0,
    56: 665, 58: 0, 60: 12, 62: 0,
}


def read_end_settings(proxy: EndProxy) -> dict[int, int]:
    return {
        address: int.from_bytes(proxy.read(address, size), "little")
        for address, size in SAVED_REGISTERS
    }


def restore_stock(proxy: EndProxy, *, apply: bool) -> tuple[dict[int, int], dict[int, int]]:
    model, result, error = proxy.packet.ping(proxy.port, END_ID)
    if result != 0 or error or model != END_MODEL:
        raise EndProxyError("END 210 did not identify as model 230")
    before = read_end_settings(proxy)
    if not apply:
        return before, before.copy()
    if (before[TOOL_ID] != 1 or before[SYNC_ENABLE] != 0 or
            before[WRITE_SIZE_1] not in (0, STOCK_END[WRITE_SIZE_1]) or
            before[WRITE_SIZE_2] != 0):
        raise EndProxyError(
            "recovery requires the observed interrupted state: "
            "Tool ID=1, TableSync=0, Write Size 1=0 or 12, Write Size 2=0; "
            f"actual={before}"
        )
    proxy._current = before.copy()
    for address, size in SAVED_REGISTERS:
        if address == SYNC_ENABLE:
            continue
        proxy.write_end(address, size, STOCK_END[address])
    checked = read_end_settings(proxy)
    mismatches = {
        address: (checked[address], desired)
        for address, desired in STOCK_END.items()
        if address != SYNC_ENABLE and checked[address] != desired
    }
    if mismatches:
        raise EndProxyError(f"END settings still differ; TableSync remains off: {mismatches}")
    proxy.write_end(SYNC_ENABLE, 1, STOCK_END[SYNC_ENABLE])
    after = read_end_settings(proxy)
    if after != STOCK_END:
        raise EndProxyError(f"END restore did not verify: {after}; expected={STOCK_END}")
    return before, after


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyAMA4")
    parser.add_argument("--baud", type=int, default=4_000_000)
    parser.add_argument("--apply", action="store_true",
                        help="restore the stock OMY END values after inspecting them")
    args = parser.parse_args(argv)
    try:
        from dynamixel_sdk import PacketHandler, PortHandler
    except ModuleNotFoundError as exc:
        parser.exit(1, f"Missing Robot PC dependency: {exc.name}\n")
    try:
        lock_fd = acquire_end_bus_lock()
    except EndProxyError as exc:
        parser.exit(1, f"END recovery failed: {exc}\n")
    port = PortHandler(args.port)
    try:
        if not port.openPort():
            raise EndProxyError(f"cannot open {args.port}; stop other END owners first")
        if not port.setBaudRate(args.baud):
            raise EndProxyError(f"cannot set {args.port} to {args.baud} baud")
        proxy = EndProxy(port, PacketHandler(2.0))
        before, after = restore_stock(proxy, apply=args.apply)
        print(f"END 210 before: {before}")
        print(f"END 210 after:  {after}")
        if args.apply:
            print("Stock OMY END settings verified. No hand or motor goal sent.")
        else:
            print(f"Stock OMY END target: {STOCK_END}. Read only; no write sent.")
        if proxy.end_write_ack_timeouts:
            print(f"END write ACK timeouts confirmed by readback: "
                  f"{proxy.end_write_ack_timeouts}; inspect communication before launch.")
        return 0
    except (EndProxyError, OSError, ValueError) as exc:
        parser.exit(1, f"END recovery failed: {exc}\n")
    finally:
        port.closePort()
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
