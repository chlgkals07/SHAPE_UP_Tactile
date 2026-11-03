"""Exercise the full END -> HX5 -> five TableSync channels data path offline."""

from pathlib import Path
from math import pi
from types import SimpleNamespace
from struct import pack

import pytest

from omy_hx5_bringup.direct_trajectory import (
    JOINT_NAMES, make_segment, make_trajectory_segment, validate_currents,
)
from omy_hx5_bringup.end_direct_core import (
    EndDirect, MOTOR_IDS, MOTOR_INDIRECT, load_vendor_motor_settings,
)
from omy_hx5_bringup.end_proxy import EndProxyError
from omy_hx5_bringup.end_layout import (
    INDIRECT_TARGETS, POSITION_SCALE, READ_BLOCK_START, WRITE_BLOCK_START,
)

XACRO = (Path(__file__).resolve().parents[3] /
         "third_party/robotis_hand/robotis_hand_description/ros2_control/"
         "hx5_d20_rev2/hx5_d20_left.ros2_control.xacro")


class FakeBus:
    def __init__(self):
        self.end = {13: 1, 46: 1, 48: 634, 50: 0, 52: 16, 54: 0,
                    56: 665, 58: 0, 60: 12, 62: 0}
        self.buffer = bytearray(128)
        self.hand = bytearray(2020)
        self.hand[0:2] = pack("<H", 261)
        self.hand[7] = 140
        self.hand[33] = 1
        self.hand[102:104] = pack("<H", 2368)
        self.motors = {}
        expected = load_vendor_motor_settings(XACRO)
        for motor_id in MOTOR_IDS:
            motor = bytearray(256)
            motor[0:2] = pack("<H", 1710)
            motor[7] = motor_id
            motor[10] = expected[motor_id].drive_mode
            motor[11] = 5
            motor[20:24] = pack("<i", expected[motor_id].homing_offset)
            motor[64] = 1
            motor[168:188] = pack("<10H", *MOTOR_INDIRECT)
            self.motors[motor_id] = motor
        self.goals = {}
        self.end_writes = []
        for channel in range(5):
            base = READ_BLOCK_START + channel * 198
            for joint in range(4):
                self.hand[base + 6 * joint + 4:base + 6 * joint + 6] = pack("<H", 2048)
            self.hand[base + 24:base + 33] = bytes(range(1, 10))

    @staticmethod
    def getTxRxResult(result):
        return "OK" if result == 0 else "failure"

    @staticmethod
    def ping(port, device_id):
        assert device_id == 210
        return 230, 0, 0

    def _device(self):
        selected = self.end[13]
        return self.hand if selected == 140 else self.motors[selected]

    def _read_target(self, address):
        device = self._device()
        if device is self.hand and 634 <= address <= 889:
            alias = int.from_bytes(device[122 + 2 * (address - 634):124 + 2 * (address - 634)], "little")
            return device[alias] if alias < len(device) else 0
        return device[address]

    def _write_target(self, address, value):
        device = self._device()
        if device is self.hand and 634 <= address <= 889:
            address = int.from_bytes(device[122 + 2 * (address - 634):124 + 2 * (address - 634)], "little")
        device[address] = value
        if device is self.hand and self.hand[70] and address >= WRITE_BLOCK_START:
            for finger in range(5):
                base = WRITE_BLOCK_START + finger * 198
                if base <= address < base + 16 and (address - base) % 4 == 3:
                    motor = finger * 4 + (address - base) // 4
                    self.goals[MOTOR_IDS[motor]] = bytes(self.hand[base + 4 * (motor % 4):
                                                                  base + 4 * (motor % 4) + 4])

    def _forward(self):
        if not self.end[46] or not self.end[60] or self.end[13] not in (140, *MOTOR_IDS):
            return
        for offset in range(self.end[60]):
            self._write_target(self.end[56] + offset, self.buffer[offset])

    def readTxRx(self, port, device_id, address, size):
        assert device_id == 210
        if address == 72:
            if self.end[13] == 140 and self.end[48] == 634 and self.end[52] == 90:
                tick = (int.from_bytes(self.hand[100:102], "little") + 1) % 32768
                self.hand[100:102] = pack("<H", tick)
            data = [self._read_target(self.end[48] + i) for i in range(size)]
        elif address == 200:
            data = self.buffer[:size]
        else:
            data = self.end[address].to_bytes(size, "little")
        return list(data), 0, 0

    def writeTxRx(self, port, device_id, address, size, data):
        assert device_id == 210
        self.end_writes.append(address)
        if address == 200:
            self.buffer[:size] = bytes(data)
            self._forward()
        else:
            self.end[address] = int.from_bytes(bytes(data), "little")
            if address == 46:
                self._forward()
        return 0, 0


def test_motor_audit_keeps_one_end_session_and_two_read_windows_per_motor():
    bus = FakeBus()
    original_end = bus.end.copy()
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    assert proxy.audit_motors(load_vendor_motor_settings(XACRO)) == []
    assert bus.end == original_end
    assert bus.end_writes.count(13) == 21  # first motor, 19 switches, restore
    assert bus.end_writes.count(60) == 2   # disable and restore write slot
    assert bus.end_writes.count(48) == 41  # two reads per motor, restore


def test_vendor_configuration_and_20_goal_path_keep_persistent_aliases():
    bus = FakeBus()
    original_end = bus.end.copy()
    original_buffer = bytes(bus.buffer)
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    assert proxy.audit_motors(load_vendor_motor_settings(XACRO)) == []
    mode, changed = proxy.prepare_direct(apply=True)
    assert mode == 1 and changed == [1, 2, 3, 4, 5]
    assert bus.hand[33] == 0
    assert not bus.goals
    proxy.verify_direct_setup()
    with proxy.direct_session() as first:
        assert len(first.positions) == 20
        assert first.pressures[0] == tuple(range(1, 10))
        assert bus.hand[70] == 1
        positions = tuple((i - 10) * 0.02 for i in range(20))
        currents = tuple(300 + i for i in range(20))
        proxy.write_goals(positions, currents)
        assert len(bus.goals) == 20
        for i, motor_id in enumerate(MOTOR_IDS):
            raw = round((positions[i] + pi) / POSITION_SCALE)
            assert bus.goals[motor_id] == pack("<HH", currents[i], raw)
        assert proxy.read_snapshot().tick != first.tick
    assert bus.hand[70] == 0
    assert bytes(bus.hand[122:462]) == pack("<170H", *INDIRECT_TARGETS)
    assert bus.end == original_end
    assert bytes(bus.buffer[:12]) == original_buffer[:12]


def test_direct_launch_sets_watchdog_after_idle_ram_value_resets():
    bus = FakeBus()
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    proxy.prepare_direct(apply=True)
    bus.hand[8] = 0  # RAM can return to its power-on value before launch
    assert proxy.verify_direct_setup() == 0
    with proxy.direct_session():
        assert bus.hand[8] == 100
        assert not bus.goals
    assert bus.hand[70] == 0


def test_direct_verify_reports_unexpected_watchdog_value():
    bus = FakeBus()
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    proxy.prepare_direct(apply=True)
    bus.hand[8] = 255
    with pytest.raises(EndProxyError, match="Bus Watchdog is 255"):
        proxy.verify_direct_setup()
    prior_goals = bus.goals.copy()
    bus.hand[70] = 1  # emulate an interrupted direct launch
    assert proxy.restore_preset_mode() == 0
    assert bus.hand[33] == 1
    assert bus.hand[70] == 0
    assert bus.goals == prior_goals


def test_keyboard_trajectory_limits_and_current_validation():
    segment = make_segment(JOINT_NAMES, (0.0,) * 20, 0.3, (0.0,) * 20, 10.0)
    assert segment.sample(10.1) == (0.0,) * 20
    slowed = make_segment(JOINT_NAMES, (1.0,) + (0.0,) * 19, 0.1,
                          (0.0,) * 20, 10.0)
    assert slowed.duration == 1.0 and slowed.sample(10.5)[0] == 0.5
    assert validate_currents([300.0] * 20) == (300,) * 20
    with pytest.raises(ValueError, match="joint limit"):
        make_segment(JOINT_NAMES, (3.0,) + (0.0,) * 19, 0.3, (0.0,) * 20, 10.0)
    vendor_points = [SimpleNamespace(
        positions=(0.0,) * 20,
        time_from_start=SimpleNamespace(sec=0 if i < 50 else 1,
                                        nanosec=(i % 50) * 20_000_000))
        for i in range(100)]
    accepted = make_trajectory_segment(JOINT_NAMES, vendor_points,
                                       (0.0,) * 20, 10.0)
    assert accepted.duration == 1.98


def test_mismatched_motor_blocks_setup_and_no_goal_is_sent():
    bus = FakeBus()
    bus.motors[146][11] = 3
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    issues = proxy.audit_motors(load_vendor_motor_settings(XACRO))
    assert len(issues) == 1 and "ID 146" in issues[0]
    assert bus.goals == {}
    with pytest.raises(EndProxyError, match="Direct Control Mode"):
        proxy.verify_direct_setup()


def test_interrupted_direct_write_window_must_be_recovered():
    bus = FakeBus()
    bus.hand[33] = 0
    bus.end.update({13: 140, 46: 1, 60: 80})
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    with pytest.raises(EndProxyError, match="active HX5 write window"):
        proxy.verify_direct_setup()
    assert proxy.restore_preset_mode() == 0
    assert bus.end[46] == 0 and bus.end[60] == 0
    assert bus.hand[33] == 1 and bus.hand[70] == 0
