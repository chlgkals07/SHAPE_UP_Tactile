"""END 210 transport for the official HX5 left-hand 20-joint command layout.

Configuration and motion are separate. ``prepare_direct`` programs the hand
controller's EEPROM once but sends no motor goal. ``direct_session`` owns the
bus, reads live state, and only forwards goals on an explicit command.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from struct import pack
import time
from xml.etree import ElementTree

from .end_layout import (
    INDIRECT_TARGETS, READ_SIZE, READ_WINDOW, STATE_SIZE, WRITE_WINDOW,
    HandSnapshot, decode_snapshot, encode_command, encode_motor_goal,
    encode_raw_goal, raw_to_position,
)
from .end_proxy import (
    END_ID, END_MODEL, FORWARD_SETTLE, HAND_ID, LEFT_HAND_MODEL, READ_ADDRESS_1,
    READ_BUFFER, READ_SIZE_1, SYNC_ENABLE, TOOL_ID, WRITE_ADDRESS_1, WRITE_SIZE_1,
    WRITE_SIZE_2, EndProxy, EndProxyError,
)

MOTOR_IDS = tuple(141 + 5 * finger + joint for finger in range(5)
                  for joint in range(4))
SENSOR_IDS = (145, 150, 155, 160, 165)
MOTOR_INDIRECT = (126, 127, 128, 129, 132, 133, 102, 103, 116, 117)
HAND_INDIRECT_BASE = 122
HAND_INDIRECT_DATA = 634
CHANNEL_SIZE = 198
CONFIG_SIZE = 54
STARTUP_GOAL_CURRENT = 100
# XM335 RAM items the official driver writes on every init: (address, size).
POSITION_D_GAIN = (80, 2)
POSITION_P_GAIN = (84, 2)
PROFILE_ACCELERATION = (108, 4)
PROFILE_VELOCITY = (112, 4)
MOTOR_RAM_WRITES = ((64, 1), POSITION_D_GAIN, POSITION_P_GAIN, (102, 2),
                    PROFILE_ACCELERATION, PROFILE_VELOCITY, (116, 4))
RAM_NAMES = ("profile_acceleration", "profile_velocity",
             "position_p_gain", "position_d_gain")


@dataclass(frozen=True)
class MotorExpected:
    drive_mode: int
    homing_offset: int
    profile_velocity: int = 100
    profile_acceleration: int = 50
    position_p_gain: int = 500
    position_d_gain: int = 1000
    startup_configuration: int = 2

    def ram_settings(self) -> tuple[tuple[tuple[int, int], int], ...]:
        return ((PROFILE_ACCELERATION, self.profile_acceleration),
                (PROFILE_VELOCITY, self.profile_velocity),
                (POSITION_P_GAIN, self.position_p_gain),
                (POSITION_D_GAIN, self.position_d_gain))


def _register(data: bytes, item: tuple[int, int]) -> int:
    address, size = item
    return int.from_bytes(data[address:address + size], "little")


def load_vendor_motor_settings(xacro_path: Path) -> dict[int, MotorExpected]:
    """Load the rev2 left-hand motor settings from ROBOTIS's vendored Xacro."""
    root = ElementTree.parse(xacro_path).getroot()
    expected = {}
    for gpio in root.iter("gpio"):
        if not gpio.attrib.get("name", "").endswith("_init"):
            continue
        values = {p.attrib["name"]: p.text for p in gpio.iter("param")}
        motor_id = int(values["ID"])
        if motor_id not in MOTOR_IDS:
            continue
        if int(values["Operating Mode"]) != 5:
            raise ValueError(f"vendor motor {motor_id} is not in current-position mode")
        aliases = tuple(int(values[f"Indirect Address {i}"]) for i in range(1, 11))
        if aliases != MOTOR_INDIRECT:
            raise ValueError(f"vendor motor {motor_id} has unexpected indirect map")
        expected[motor_id] = MotorExpected(
            int(values["Drive Mode"]), int(values.get("Homing Offset", "0")),
            int(values["Profile Velocity"]), int(values["Profile Acceleration"]),
            int(values["Position P Gain"]), int(values["Position D Gain"]),
            int(values["Startup Configuration"]))
    if set(expected) != set(MOTOR_IDS):
        raise ValueError("vendor left-hand Xacro does not define all 20 motors")
    return expected


def expected_channel_config(current: bytes, channel: int) -> bytes:
    """Match the vendor's five active slots and disable the unused sixth."""
    if len(current) != CONFIG_SIZE or not 0 <= channel < 5:
        raise ValueError("expected one 54-byte HX5 TableSync channel")
    desired = bytearray(current)
    for slot in range(5):
        desired[slot] = 141 + 5 * channel + slot
        for offset, value in ((6, 224 if slot < 4 else 72),
                              (18, 6 if slot < 4 else 9),
                              (30, 230 if slot < 4 else 0),
                              (42, 4 if slot < 4 else 0)):
            desired[offset + 2 * slot:offset + 2 * slot + 2] = pack("<H", value)
    desired[5] = 255
    for offset in (6, 18, 30, 42):
        desired[offset + 10:offset + 12] = b"\x00\x00"
    return bytes(desired)


class EndDirect(EndProxy):
    def __init__(self, port, packet, *, sleep=time.sleep,
                 allow_active_status32: bool = False, read_only: bool = False):
        super().__init__(port, packet, sleep=sleep)
        self.allow_active_status32 = allow_active_status32
        self.read_only = read_only
        self._active_status32_verified = False
        self._motor_goals: dict[int, tuple[int, int]] | None = None
        self.audit_notes: list[str] = []
        self.hand_firmware: int | None = None
        self.primed_positions: tuple[float, ...] | None = None
        self.primed_currents: tuple[int, ...] | None = None
        self.ram_updated_motors: list[int] = []

    def read_hand(self, address: int, size: int, *, stable: bool = False) -> bytes:
        if self._current.get(TOOL_ID) == HAND_ID:
            return self.read_hand_fresh(address, size, stable=stable)
        return super().read_hand(address, size, stable=stable)

    def diagnose_hand(self) -> dict[str, int]:
        """Read one tick-verified HX5 control-table snapshot, no hand writes."""
        with self.temporary_read_window():
            data = self.read_hand(0, 107)
            model = int.from_bytes(data[0:2], "little")
            hand_id = data[7]
            if model != LEFT_HAND_MODEL or hand_id != HAND_ID:
                raise EndProxyError(
                    f"END did not return the left HX5: model={model}, ID={hand_id}")
            return {
                "model": model,
                "id": hand_id,
                "firmware": data[6],
                "mode": data[33],
                "table_sync": data[70],
                "watchdog": data[8],
                "tick": int.from_bytes(data[100:102], "little"),
                "voltage_centivolts": int.from_bytes(data[102:104], "little"),
                "status": data[106],
                "end_tool_status": self.read(14, 1)[0],
            }

    def compare_indirect_health(self) -> dict[str, object]:
        """Compare the full END indirect read window to direct HX5 health bytes.

        The hand's own TableSync remains off; no hand or motor goal is sent.
        """
        with self.temporary_read_window():
            self._check_hand(required_mode=0)
            indirect = []
            for _ in range(3):
                data = EndProxy.read_hand(self, READ_WINDOW, STATE_SIZE)
                indirect.append({
                    "tick": int.from_bytes(data[READ_SIZE:READ_SIZE + 2], "little"),
                    "voltage_centivolts": int.from_bytes(
                        data[READ_SIZE + 2:READ_SIZE + 4], "little"),
                    "status": data[READ_SIZE + 4],
                })
            direct = self.read_hand(100, 7)
            return {
                "indirect": indirect,
                "direct": {
                    "tick": int.from_bytes(direct[0:2], "little"),
                    "voltage_centivolts": int.from_bytes(direct[2:4], "little"),
                    "status": direct[6],
                },
            }

    def compare_active_health(self) -> list[dict[str, object]]:
        """Compare active TableSync health paths without sending motor goals.

        Enable the hand watchdog and TableSync only while the END tool write
        slot is disabled, after copying the held motor goals into Write Data.
        Always attempt to turn both off before END restore.
        """
        with self.temporary_read_window():
            self._check_hand(required_mode=0)
            if self.read_hand(8, 1)[0] != 0:
                raise EndProxyError("active health probe requires idle watchdog 0")
            samples = []
            try:
                self._prime_write_data()
                self.write_hand(8, b"\x64")
                self.write_hand(70, b"\x01")
                self.sleep(0.2)
                for _ in range(3):
                    indirect = EndProxy.read_hand(self, READ_WINDOW, STATE_SIZE)
                    direct = self.read_hand(100, 7)
                    control = self.read_hand(70, 2)
                    watchdog = self.read_hand(8, 1)[0]
                    samples.append({
                        "indirect": {
                            "tick": int.from_bytes(
                                indirect[READ_SIZE:READ_SIZE + 2], "little"),
                            "voltage_centivolts": int.from_bytes(
                                indirect[READ_SIZE + 2:READ_SIZE + 4], "little"),
                            "status": indirect[READ_SIZE + 4],
                        },
                        "direct": {
                            "tick": int.from_bytes(direct[0:2], "little"),
                            "voltage_centivolts": int.from_bytes(direct[2:4], "little"),
                            "status": direct[6],
                        },
                        "table_sync": control[0],
                        "hardware_error": control[1],
                        "watchdog": watchdog,
                    })
            finally:
                try:
                    self.write_hand(8, b"\x00")  # watchdog first; see direct_session
                finally:
                    self.write_hand(70, b"\x00")
            return samples

    def audit_motors(self, expected: dict[int, MotorExpected], *,
                     runtime: bool = True) -> list[str]:
        """Inspect the 20 actuators through END, without actuator writes.

        ``runtime=False`` checks only persistent identity and configuration,
        so TableSync and mode setup do not depend on torque or RAM values
        that a power cycle clears. A clean runtime audit also records each
        motor's present Goal Current and Goal Position. ``direct_session`` copies exactly those values into the hand's
        TableSync Write Data before enabling it, so enabling TableSync cannot
        send the controller's power-on zeros (current 0, position -pi).
        """
        issues = []
        notes = []
        goals = {}
        self._motor_goals = None
        with self.temporary_read_window(tool_id=MOTOR_IDS[0]):
            for motor_id in MOTOR_IDS:
                if motor_id != MOTOR_IDS[0]:
                    self.write_end(SYNC_ENABLE, 1, 0)
                    self.write_end(TOOL_ID, 1, motor_id)
                first = self.read_hand(0, 120)
                torque = first[64]
                hardware_error = first[70]
                goal_raw = int.from_bytes(first[116:120], "little")
                goal_current = int.from_bytes(first[102:104], "little")
                aliases = self.read_hand(168, 20, stable=True)
                model = int.from_bytes(first[:2], "little")
                actual_id = first[7]
                drive, mode = first[10], first[11]
                homing = int.from_bytes(first[20:24], "little", signed=True)
                mapped = tuple(int.from_bytes(aliases[i:i + 2], "little")
                               for i in range(0, 20, 2))
                item = expected[motor_id]
                ram = {name: _register(first, register)
                       for name, (register, _) in zip(RAM_NAMES, item.ram_settings())}
                wanted_ram = {name: value
                              for name, (_, value) in zip(RAM_NAMES, item.ram_settings())}
                runtime_bad = (goal_raw > 4095 or not 0 <= goal_current <= 910 or
                               torque != 1 or ram != wanted_ram)
                if (model != 1710 or actual_id != motor_id or mode != 5 or
                        (drive & ~8) != (item.drive_mode & ~8) or
                        homing != item.homing_offset or mapped != MOTOR_INDIRECT or
                        hardware_error or (runtime and runtime_bad)):
                    issues.append(
                        f"ID {motor_id}: model={model}, id={actual_id}, drive={drive}, "
                        f"mode={mode}, homing={homing}, torque={torque}, "
                        f"goal_raw={goal_raw}, goal_current={goal_current}, "
                        f"hardware_error={hardware_error}, {ram}, "
                        f"aliases={mapped}; "
                        f"expected model=1710, drive={item.drive_mode} (bit 3 optional), "
                        f"mode=5, homing={item.homing_offset}, torque=1, goal_raw<=4095, "
                        f"goal_current<=910, {wanted_ram}, aliases={MOTOR_INDIRECT}"
                    )
                else:
                    goals[motor_id] = (goal_current, goal_raw)
                startup = _register(first, (60, 2))
                if startup != item.startup_configuration:
                    notes.append(
                        f"ID {motor_id}: Startup Configuration={startup}, official "
                        f"{item.startup_configuration}; power-on behavior differs, "
                        "Direct control is unaffected")
        self.audit_notes = notes
        if runtime and not issues:
            self._motor_goals = goals
        return issues

    def _motor_torque_state(self, motor_id: int, expected: MotorExpected) -> dict[str, int]:
        """Inspect a selected motor before changing its torque."""
        first = self.read_hand(0, 120)
        present = int.from_bytes(self.read_hand(132, 4), "little", signed=True)
        aliases = self.read_hand(168, 20, stable=True)
        model = int.from_bytes(first[:2], "little")
        homing = int.from_bytes(first[20:24], "little", signed=True)
        drive, mode, torque, error = first[10], first[11], first[64], first[70]
        # Motor Bus Watchdog stays 0 on this path, unlike the official 100:
        # the hand's TableSync is off between sessions, so a motor watchdog
        # would latch an error and lock Goal registers while the hand idles.
        watchdog = first[98]
        goal_current = int.from_bytes(first[102:104], "little")
        goal_position = int.from_bytes(first[116:120], "little", signed=True)
        ram = {register: _register(first, register)
               for register, _ in expected.ram_settings()}
        mapped = tuple(int.from_bytes(aliases[i:i + 2], "little")
                       for i in range(0, 20, 2))
        if (model != 1710 or first[7] != motor_id or mode != 5 or
                (drive & ~8) != (expected.drive_mode & ~8) or
                homing != expected.homing_offset or mapped != MOTOR_INDIRECT or
                torque not in (0, 1) or error or watchdog != 0 or
                not 0 <= goal_current <= 910 or
                not 0 <= goal_position <= 4095 or
                not 0 <= present <= 4095 or
                (torque == 0 and drive & 8)):
            raise EndProxyError(
                f"motor {motor_id} is not safe for torque enable: model={model}, "
                f"id={first[7]}, drive={drive}, mode={mode}, homing={homing}, "
                f"torque={torque}, error={error}, watchdog={watchdog}, "
                f"goal_current={goal_current}, goal_position={goal_position}, "
                f"present_position={present}, aliases={mapped}")
        return {"torque": torque, "present": present, "ram": ram,
                "goal_position": goal_position, "goal_current": goal_current}

    def inspect_motor_torques(self) -> dict[int, tuple[int, int]]:
        """Read each motor's torque and hardware error without motor writes."""
        states = {}
        with self.temporary_read_window(tool_id=MOTOR_IDS[0]):
            for motor_id in MOTOR_IDS:
                if motor_id != MOTOR_IDS[0]:
                    self.write_end(SYNC_ENABLE, 1, 0)
                    self.write_end(TOOL_ID, 1, motor_id)
                last_error = None
                for _ in range(3):
                    try:
                        data = self.read_hand(0, 71)
                        model = int.from_bytes(data[:2], "little")
                        if model != 1710 or data[7] != motor_id or data[64] not in (0, 1):
                            raise EndProxyError(
                                f"motor {motor_id} identity/torque mismatch: "
                                f"model={model}, id={data[7]}, torque={data[64]}")
                        states[motor_id] = (data[64], data[70])
                        break
                    except EndProxyError as exc:
                        last_error = exc
                        self.sleep(0.1)
                else:
                    raise EndProxyError(
                        f"motor {motor_id} status could not be verified: {last_error}")
        return states

    def inspect_tactile_sensors(self) -> dict[int, dict[str, object]]:
        """Read five sensor identities and pressure bytes, without motor goals."""
        reports = {}
        with self.temporary_read_window(tool_id=SENSOR_IDS[0]):
            for sensor_id in SENSOR_IDS:
                if sensor_id != SENSOR_IDS[0]:
                    self.write_end(SYNC_ENABLE, 1, 0)
                    self.write_end(TOOL_ID, 1, sensor_id)
                last_error = None
                for _ in range(3):
                    try:
                        identity = self.read_hand(0, 8, stable=True)
                        model = int.from_bytes(identity[:2], "little")
                        if identity[7] != sensor_id or model in (0, 0xFFFF):
                            raise EndProxyError(
                                f"ID {sensor_id} identity mismatch: "
                                f"reported ID={identity[7]}, model={model}")
                        pressures = self.read_hand(72, 9)
                        reports[sensor_id] = {
                            "model": model, "pressures": tuple(pressures)}
                        break
                    except EndProxyError as exc:
                        last_error = exc
                        self.sleep(0.1)
                else:
                    reports[sensor_id] = {"error": str(last_error)}
        return reports

    def _write_selected_motor(self, motor_id: int, address: int, data: bytes) -> None:
        """Forward one verified RAM write to the selected motor via END."""
        if (self._current.get(TOOL_ID) != motor_id or motor_id not in MOTOR_IDS or
                (address, len(data)) not in MOTOR_RAM_WRITES):
            raise EndProxyError("invalid selected motor or torque-start register")
        self.write_end(SYNC_ENABLE, 1, 0)
        self.write_end(READ_ADDRESS_1, 2, address)
        self.write_end(READ_SIZE_1, 2, len(data))
        self.write_end(WRITE_ADDRESS_1, 2, address)
        self.write_end(WRITE_SIZE_1, 2, len(data))
        self.write_end_buffer(data)
        try:
            self.write_end(SYNC_ENABLE, 1, 1)
            self.sleep(FORWARD_SETTLE)
        finally:
            self.write_end(SYNC_ENABLE, 1, 0)
            self.write_end(WRITE_SIZE_1, 2, 0)
        # The END read buffer can contain the preceding forwarding cycle's
        # value. Retry reads only; never repeat an uncertain motor write.
        last_observation = "no readback"
        for _ in range(4):
            try:
                actual = EndProxy.read_hand(self, address, len(data), stable=True)
                if actual == data:
                    return
                last_observation = f"actual={list(actual)}"
            except EndProxyError as exc:
                last_observation = str(exc)
            self.sleep(0.1)
        raise EndProxyError(
            f"motor {motor_id} register {address} did not verify: "
            f"expected={list(data)}, {last_observation}")

    def enable_motor_torque(self, expected: dict[int, MotorExpected],
                            *, motor_id: int | None = None) -> tuple[int, ...]:
        """Apply official RAM settings, prime positions, enable torque.

        Explicitly invoked only. All motors are checked before the first
        write. Every selected motor, including one already holding torque,
        receives the official Profile Acceleration/Velocity and Position P/D
        gains, which the vendor driver writes on each init and a power cycle
        clears. Drive Mode bit 3 must be off so priming cannot itself enable
        torque. The low startup current limits initial holding force. Torque
        rollback covers only motors this call tried to enable.
        """
        selected = (motor_id,) if motor_id is not None else MOTOR_IDS
        if not selected or any(item not in MOTOR_IDS for item in selected):
            raise ValueError("motor_id must be one of the 20 left HX5 motor IDs")
        enabled = []
        self.ram_updated_motors = []
        with self.temporary_read_window():
            self._check_hand(required_mode=0)
            states = {}
            for item in selected:
                self.write_end(SYNC_ENABLE, 1, 0)
                self.write_end(TOOL_ID, 1, item)
                states[item] = self._motor_torque_state(item, expected[item])
            try:
                for item in selected:
                    self.write_end(SYNC_ENABLE, 1, 0)
                    self.write_end(TOOL_ID, 1, item)
                    for (address, size), value in expected[item].ram_settings():
                        if states[item]["ram"][(address, size)] != value:
                            self._write_selected_motor(
                                item, address, value.to_bytes(size, "little"))
                            if item not in self.ram_updated_motors:
                                self.ram_updated_motors.append(item)
                    if states[item]["torque"]:
                        continue
                    before = int.from_bytes(
                        self.read_hand(132, 4), "little", signed=True)
                    self.sleep(0.05)
                    current = int.from_bytes(
                        self.read_hand(132, 4), "little", signed=True)
                    if (not 0 <= current <= 4095 or abs(current - before) > 32):
                        raise EndProxyError(
                            f"motor {item} moved while preparing torque: {before}, {current}")
                    self._write_selected_motor(
                        item, 102, STARTUP_GOAL_CURRENT.to_bytes(2, "little"))
                    self._write_selected_motor(item, 116, current.to_bytes(4, "little"))
                    latest = int.from_bytes(
                        self.read_hand(132, 4), "little", signed=True)
                    if abs(latest - current) > 32:
                        raise EndProxyError(
                            f"motor {item} moved before torque enable: {current}, {latest}")
                    enabled.append(item)  # Include uncertain writes in rollback.
                    self._write_selected_motor(item, 64, b"\x01")
                    after = int.from_bytes(
                        self.read_hand(132, 4), "little", signed=True)
                    if abs(after - current) > 64:
                        raise EndProxyError(
                            f"motor {item} moved unexpectedly after torque enable: "
                            f"{current}, {after}")
            except Exception as exc:
                rollback_errors = []
                for item in reversed(enabled):
                    try:
                        self.write_end(SYNC_ENABLE, 1, 0)
                        self.write_end(TOOL_ID, 1, item)
                        self._write_selected_motor(item, 64, b"\x00")
                    except Exception as rollback_exc:
                        rollback_errors.append(f"{item}: {rollback_exc}")
                raise EndProxyError(
                    f"motor torque enable stopped: {exc}; "
                    f"rollback attempted={enabled}; rollback errors={rollback_errors}"
                ) from exc
        return tuple(enabled)

    def _check_hand(self, *, required_mode: int | None = None,
                    allow_sync: bool = False) -> tuple[int, int]:
        model, result, error = self.packet.ping(self.port, END_ID)
        if result != 0 or error or model != END_MODEL:
            raise EndProxyError("END 210 did not identify as model 230")
        control = self.read_hand(0, 107)
        hand_model = int.from_bytes(control[0:2], "little")
        hand_id = control[7]
        mode = control[33]
        sync = control[70]
        status = control[106]
        self.hand_firmware = control[6]
        if (hand_model != LEFT_HAND_MODEL or hand_id != HAND_ID or status or
                mode not in (0, 1) or sync not in (0, 1)):
            raise EndProxyError(
                f"left HX5 not healthy: model={hand_model}, id={hand_id}, "
                f"mode={mode}, TableSync={sync}, status={status}")
        if required_mode is not None and mode != required_mode:
            raise EndProxyError(f"HX5 mode={mode}; required Direct Control Mode 0")
        if sync != 0 and not allow_sync:
            raise EndProxyError("HX5 TableSync is already enabled; stop its owner first")
        return mode, sync

    def _alias_bytes(self, start: int, size: int) -> bytes:
        chunks = []
        for offset in range(0, size, 126):
            chunks.append(self.read_hand(start + offset, min(126, size - offset)))
        return b"".join(chunks)

    def _set_alias_bytes(self, start: int, data: bytes) -> None:
        for offset in range(0, len(data), 126):
            self.write_hand(start + offset, data[offset:offset + 126])

    def _read_channel_config(self, channel: int) -> bytes:
        aliases = pack("<54H", *(1024 + CHANNEL_SIZE * channel + i
                                   for i in range(CONFIG_SIZE)))
        self.write_hand(HAND_INDIRECT_BASE, aliases)
        return self.read_hand(HAND_INDIRECT_DATA, CONFIG_SIZE, stable=True)

    def prepare_direct(self, *, apply: bool) -> tuple[int, list[int]]:
        """Audit or configure HX5 TableSync, then select mode 0 if requested.

        No actuator goal is written. The caller must separately audit motors.
        """
        with self.temporary_read_window():
            mode, _ = self._check_hand()
            original = self.read_hand(HAND_INDIRECT_BASE, 108, stable=True)
            changed = []
            completed = False
            try:
                for channel in range(5):
                    actual = self._read_channel_config(channel)
                    desired = expected_channel_config(actual, channel)
                    if actual != desired:
                        changed.append(channel + 1)
                        if apply:
                            self.write_hand(HAND_INDIRECT_DATA, desired)
                            if self.read_hand(HAND_INDIRECT_DATA, CONFIG_SIZE,
                                              stable=True) != desired:
                                raise EndProxyError(
                                    f"HX5 TableSync channel {channel + 1} did not verify")
                if apply and mode != 0:
                    self.write_hand(33, b"\x00")
                    if self.read_hand(33, 1, stable=True) != b"\x00":
                        raise EndProxyError("HX5 did not enter Direct Control Mode 0")
                if apply:
                    if self.read_hand(8, 1, stable=True) != b"\x00":
                        self.write_hand(8, b"\x00")  # leave idle watchdog disabled
                    final_aliases = pack(f"<{len(INDIRECT_TARGETS)}H", *INDIRECT_TARGETS)
                    self._set_alias_bytes(HAND_INDIRECT_BASE, final_aliases)
                    if self._alias_bytes(HAND_INDIRECT_BASE, len(final_aliases)) != final_aliases:
                        raise EndProxyError("HX5 persistent direct aliases did not verify")
                else:
                    self.write_hand(HAND_INDIRECT_BASE, original)
                    if self.read_hand(HAND_INDIRECT_BASE, 108,
                                      stable=True) != original:
                        raise EndProxyError("HX5 setup aliases did not restore")
                completed = True
            finally:
                if not completed:
                    self.write_end(SYNC_ENABLE, 1, 0)
                    self.write_end(WRITE_SIZE_1, 2, 0)
                    self.write_hand(HAND_INDIRECT_BASE, original)
        return mode, changed

    def verify_direct_setup(self) -> int:
        """Check persistent Direct configuration; accept an idle watchdog of 0."""
        with self.temporary_read_window():
            self._check_hand(required_mode=0)
            watchdog = self.read_hand(8, 1, stable=True)[0]
            if watchdog not in (0, 100):
                raise EndProxyError(
                    f"HX5 Bus Watchdog is {watchdog}; expected idle 0 or 100")
            expected = pack(f"<{len(INDIRECT_TARGETS)}H", *INDIRECT_TARGETS)
            if self._alias_bytes(HAND_INDIRECT_BASE, len(expected)) != expected:
                raise EndProxyError(
                    "HX5 direct aliases differ; run omy_hx5_end_direct_prepare --apply")
            return watchdog

    def clear_idle_watchdog(self) -> tuple[int, int]:
        """Clear only a stopped HX5 watchdog while its TableSync is idle."""
        with self.temporary_read_window():
            control = self.read_hand(0, 107)
            model = int.from_bytes(control[0:2], "little")
            hand_id = control[7]
            mode, sync, status, prior = control[33], control[70], control[106], control[8]
            if (model != LEFT_HAND_MODEL or hand_id != HAND_ID or
                    mode != 0 or sync != 0 or status & ~0x40):
                raise EndProxyError(
                    f"cannot clear HX5 watchdog: model={model}, id={hand_id}, mode={mode}, "
                    f"TableSync={sync}, status={status}, watchdog={prior}")
            if prior not in (0, 255):
                raise EndProxyError(
                    f"HX5 watchdog is {prior}; only idle 0 or error 255 is allowed")
            if prior == 255 or status:
                self.write_hand(8, b"\x00")
                current = self.read_hand(8, 1, stable=True)[0]
                new_status = self.read_hand(106, 1)[0]
                if current != 0 or new_status:
                    raise EndProxyError(
                        f"HX5 watchdog clear did not verify: "
                        f"watchdog={current}, status={new_status}")
            else:
                current = 0
            return prior, current

    def restore_preset_mode(self) -> int:
        """Switch the controller back to Preset Mode without a motor goal."""
        # A previous process can leave END forwarding its old goal buffer.
        # Neutralize that configuration before temporary_read_window() can
        # restore it at the end of this operation.
        tool_id = self.read(TOOL_ID, 1)[0]
        sync = self.read(SYNC_ENABLE, 1)[0]
        write_1 = int.from_bytes(self.read(WRITE_SIZE_1, 2), "little")
        write_2 = int.from_bytes(self.read(WRITE_SIZE_2, 2), "little")
        if tool_id == HAND_ID and sync == 1 and (write_1 or write_2):
            self._current = {SYNC_ENABLE: 1, WRITE_SIZE_1: write_1,
                             WRITE_SIZE_2: write_2}
            self.write_end(SYNC_ENABLE, 1, 0)
            self.write_end(WRITE_SIZE_1, 2, 0)
            self.write_end(WRITE_SIZE_2, 2, 0)
        with self.temporary_read_window():
            old_mode, sync = self._check_hand(allow_sync=True)
            if sync:
                self.write_hand(70, b"\x00")
            if old_mode != 1:
                self.write_hand(33, b"\x01")
                if self.read_hand(33, 1, stable=True) != b"\x01":
                    raise EndProxyError("HX5 did not enter Preset Motion Mode 1")
            return old_mode

    def _prime_write_data(self) -> None:
        """Copy each motor's held goal into hand Write Data; TableSync must be off."""
        if self._motor_goals is None:
            raise EndProxyError("run a clean audit_motors() before enabling hand TableSync")
        primed = tuple(self._motor_goals[motor_id] for motor_id in MOTOR_IDS)
        self.write_hand(WRITE_WINDOW,
                        b"".join(encode_raw_goal(current, raw) for current, raw in primed))
        self.primed_currents = tuple(current for current, _ in primed)
        self.primed_positions = tuple(raw_to_position(raw) for _, raw in primed)

    @contextmanager
    def direct_session(self):
        """Enable direct state on startup; forward goals only on request.

        Before hand TableSync starts, its Write Data is filled with the goals
        each motor already holds (from ``audit_motors``). Enabling TableSync,
        including in read-only mode, therefore rewrites identical goals.
        """
        if self._motor_goals is None:
            raise EndProxyError("run a clean audit_motors() before a Direct session")
        with self.temporary_read_window():
            self._check_hand(required_mode=0)
            alias_data = pack(f"<{len(INDIRECT_TARGETS)}H", *INDIRECT_TARGETS)
            if self._alias_bytes(HAND_INDIRECT_BASE, len(alias_data)) != alias_data:
                raise EndProxyError("HX5 direct aliases not installed")
            self._direct_active = False
            self._active_status32_verified = False
            try:
                self._prime_write_data()
                watchdog = self.read_hand(8, 1, stable=True)[0]
                if watchdog == 0:
                    self.write_hand(8, b"\x64")
                    watchdog = self.read_hand(8, 1, stable=True)[0]
                if watchdog != 100:
                    raise EndProxyError(
                        f"HX5 Bus Watchdog is {watchdog}; cannot start Direct Mode")
                self.write_hand(70, b"\x01")
                control = self.read_hand(70, 2)
                active_watchdog = self.read_hand(8, 1)[0]
                active_status = self.read_hand(106, 1)[0]
                if control != b"\x01\x00" or active_watchdog != 100:
                    raise EndProxyError(
                        "HX5 active control not healthy: "
                        f"table_sync={control[0]}, hardware_error={control[1]}, "
                        f"watchdog={active_watchdog}")
                if active_status == 32:
                    if not self.allow_active_status32:
                        raise EndProxyError(
                            "HX5 reports undocumented active status 32; "
                            "explicit allow_active_status32 is required")
                    self._active_status32_verified = True
                elif active_status != 0:
                    raise EndProxyError(f"HX5 active status is {active_status}")
                self.write_end(SYNC_ENABLE, 1, 0)
                self.write_end(READ_ADDRESS_1, 2, READ_WINDOW)
                self.write_end(READ_SIZE_1, 2, STATE_SIZE)
                self.write_end(WRITE_SIZE_1, 2, 0)
                self.write_end(SYNC_ENABLE, 1, 1)
                self.sleep(0.2)
                first = self.read_snapshot()
                self.sleep(0.06)
                second = self.read_snapshot()
                if first.tick == second.tick:
                    raise EndProxyError("HX5 state tick did not advance through END")
                self._direct_active = True
                yield second
            finally:
                self._direct_active = False
                self._active_status32_verified = False
                self.write_end(SYNC_ENABLE, 1, 0)
                self.write_end(WRITE_SIZE_1, 2, 0)
                # Disable the hand watchdog while TableSync is still running.
                # The END pauses polling between the following writes; with a
                # missed ACK, a pause can exceed the 2 s watchdog.
                self.write_hand(8, b"\x00")
                self.write_hand(70, b"\x00")
                if self.read_hand(70, 1, stable=True) != b"\x00":
                    raise EndProxyError("HX5 TableSync did not stop on Direct exit")

    def read_snapshot(self) -> HandSnapshot:
        if self._current.get(READ_ADDRESS_1) != READ_WINDOW or \
                self._current.get(READ_SIZE_1) != STATE_SIZE or \
                self._current.get(SYNC_ENABLE) != 1:
            raise EndProxyError("END direct read window is not active")
        try:
            return decode_snapshot(
                self.read(READ_BUFFER, STATE_SIZE),
                allow_active_status32=self._active_status32_verified)
        except ValueError as exc:
            raise EndProxyError(str(exc)) from exc

    def write_goals(self, positions: tuple[float, ...], current: int | tuple[int, ...]) -> None:
        if self.read_only:
            raise EndProxyError("read-only Direct session rejects motor goals")
        if not getattr(self, "_direct_active", False):
            raise EndProxyError("direct session is not active")
        self._write_goal_payload(WRITE_WINDOW, encode_command(positions, current))

    def write_one_goal(self, joint_index: int, position: float, current: int) -> None:
        """Forward only one 4-byte motor slot through the END indirect window."""
        if self.read_only:
            raise EndProxyError("read-only Direct session rejects motor goals")
        if not getattr(self, "_direct_active", False):
            raise EndProxyError("direct session is not active")
        if not isinstance(joint_index, int) or not 0 <= joint_index < 20:
            raise ValueError("HX5 joint index must be 0..19")
        self._write_goal_payload(
            WRITE_WINDOW + 4 * joint_index,
            encode_motor_goal(position, current))

    def _write_goal_payload(self, address: int, payload: bytes) -> None:
        if (self._current.get(SYNC_ENABLE) == 1 and
                self._current.get(WRITE_ADDRESS_1) == address and
                self._current.get(WRITE_SIZE_1) == len(payload)):
            self.write_end_buffer_live(payload)
            return
        self.write_end(SYNC_ENABLE, 1, 0)
        self.write_end(WRITE_SIZE_1, 2, 0)
        self.write_end(WRITE_ADDRESS_1, 2, address)
        self.write_end(WRITE_SIZE_1, 2, len(payload))
        self.write_end_buffer(payload)
        self.write_end(SYNC_ENABLE, 1, 1)
