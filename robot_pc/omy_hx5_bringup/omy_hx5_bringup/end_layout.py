"""Compact OMY END window for the official left HX5 TableSync layout.

The hand controller stores five 198-byte TableSync channel blocks above
address 1023. END can forward only addresses <=1023 and read/write at most
128 bytes at a time. HX5's indirect table aliases 85 joint/tactile bytes
and 5 health bytes into one END read window, and its 80 goal bytes into
one END write window. This module only computes addresses; it never writes a
device. Configuration is a separate explicit hardware operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi

CHANNELS = 5
MOTORS_PER_CHANNEL = 4
CHANNEL_STRIDE = 198
READ_BLOCK_START = 1078
WRITE_BLOCK_START = 1150
HAND_INDIRECT_ADDRESS_START = 122
HAND_INDIRECT_DATA_START = 634
POSITION_SCALE = 2 * pi / 4096


def read_targets() -> tuple[int, ...]:
    """Twenty 2-byte positions and five 9-byte tactile arrays (85 bytes)."""
    targets = []
    for channel in range(CHANNELS):
        base = READ_BLOCK_START + channel * CHANNEL_STRIDE
        for motor in range(MOTORS_PER_CHANNEL):
            # Vendor read slot: current 2, velocity 2, position 2.
            targets.extend((base + motor * 6 + 4, base + motor * 6 + 5))
        targets.extend(base + offset for offset in range(24, 33))
    return tuple(targets)


def write_targets() -> tuple[int, ...]:
    """Twenty 2-byte currents and 2-byte positions (80 bytes)."""
    targets = []
    for channel in range(CHANNELS):
        base = WRITE_BLOCK_START + channel * CHANNEL_STRIDE
        for motor in range(MOTORS_PER_CHANNEL):
            targets.extend(base + motor * 4 + offset for offset in range(4))
    return tuple(targets)


READ_TARGETS = read_targets()
WRITE_TARGETS = write_targets()
READ_SIZE = len(READ_TARGETS)
WRITE_SIZE = len(WRITE_TARGETS)
MONITOR_TARGETS = (100, 101, 102, 103, 106)  # tick, voltage, status
STATE_SIZE = READ_SIZE + len(MONITOR_TARGETS)
READ_WINDOW = HAND_INDIRECT_DATA_START
WRITE_WINDOW = READ_WINDOW + STATE_SIZE
INDIRECT_TARGETS = READ_TARGETS + MONITOR_TARGETS + WRITE_TARGETS

assert READ_SIZE == 85 and STATE_SIZE == 90 and WRITE_SIZE == 80
assert len(INDIRECT_TARGETS) <= 256
assert WRITE_WINDOW + WRITE_SIZE <= 890


@dataclass(frozen=True)
class HandSnapshot:
    positions: tuple[float, ...]
    pressures: tuple[tuple[int, ...], ...]
    tick: int
    voltage_centivolts: int
    status: int


def decode_snapshot(data: bytes, *, allow_active_status32: bool = False) -> HandSnapshot:
    if len(data) != STATE_SIZE:
        raise ValueError(f"expected {STATE_SIZE} bytes of HX5 state and health")
    positions, pressures = decode_state(data[:READ_SIZE])
    tick = int.from_bytes(data[READ_SIZE:READ_SIZE + 2], "little")
    voltage = int.from_bytes(data[READ_SIZE + 2:READ_SIZE + 4], "little")
    status = data[READ_SIZE + 4]
    if tick > 32767 or (status and not (allow_active_status32 and status == 32)):
        raise ValueError(f"HX5 health invalid: tick={tick}, status={status}")
    return HandSnapshot(positions, pressures, tick, voltage, status)


def decode_state(data: bytes) -> tuple[tuple[float, ...], tuple[tuple[int, ...], ...]]:
    if len(data) != READ_SIZE:
        raise ValueError(f"expected {READ_SIZE} bytes of HX5 state")
    positions = []
    pressures = []
    for channel in range(CHANNELS):
        base = channel * 17
        for motor in range(MOTORS_PER_CHANNEL):
            raw = int.from_bytes(data[base + 2 * motor:base + 2 * motor + 2], "little")
            if raw > 4095:
                raise ValueError(f"HX5 motor position {raw} is outside 0..4095")
            positions.append(raw * POSITION_SCALE - pi)
        pressures.append(tuple(data[base + 8:base + 17]))
    return tuple(positions), tuple(pressures)


def encode_command(positions: tuple[float, ...], current: int | tuple[int, ...]) -> bytes:
    currents = (current,) * 20 if isinstance(current, int) else tuple(current)
    if (len(positions) != 20 or len(currents) != 20 or
            any(not isinstance(value, int) or not 0 <= value <= 910
                for value in currents)):
        raise ValueError("HX5 command requires 20 positions and currents 0..910")
    data = bytearray()
    for position, motor_current in zip(positions, currents):
        data.extend(encode_motor_goal(position, motor_current))
    return bytes(data)


def encode_motor_goal(position: float, current: int) -> bytes:
    """One HX5 TableSync motor slot: Goal Current, then Goal Position."""
    if not isinstance(current, int) or not 0 <= current <= 910:
        raise ValueError("HX5 motor current must be an integer in 0..910")
    if not isfinite(position) or not -pi <= position <= pi:
        raise ValueError("HX5 goal position must be finite and within +/-pi")
    raw = min(round((position + pi) / POSITION_SCALE), 4095)
    return current.to_bytes(2, "little") + raw.to_bytes(2, "little")
