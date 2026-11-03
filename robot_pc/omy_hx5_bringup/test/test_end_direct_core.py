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
    EndDirect, MOTOR_IDS, MOTOR_INDIRECT, SENSOR_IDS, load_vendor_motor_settings,
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
        self.end = {13: 1, 14: 0, 46: 1, 48: 634, 50: 0, 52: 16, 54: 0,
                    56: 665, 58: 0, 60: 12, 62: 0}
        self.buffer = bytearray(128)
        self.hand = bytearray(2020)
        self.hand[0:2] = pack("<H", 261)
        self.hand[7] = 140
        self.hand[33] = 1
        self.hand[102:104] = pack("<H", 2368)
        self.motors = {}
        self.sensors = {}
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
        for sensor_id in SENSOR_IDS:
            sensor = bytearray(96)
            sensor[0:2] = pack("<H", 6000 + sensor_id - 140)
            sensor[7] = sensor_id
            sensor[72:81] = bytes(range(1, 10))
            self.sensors[sensor_id] = sensor
        self.goals = {}
        self.end_writes = []
        self.freeze_hand_tick = False
        self.hand_reads_with_write_slot = 0
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
        if selected == 140:
            return self.hand
        return self.motors[selected] if selected in self.motors else self.sensors[selected]

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
            if self.end[13] == 140 and self.end[60]:
                self.hand_reads_with_write_slot += 1
            if self.end[13] == 140 and self.end[46] and not self.freeze_hand_tick:
                tick = (int.from_bytes(self.hand[100:102], "little") + 1) % 32768
                self.hand[100:102] = pack("<H", tick)
            first_size = self.end[52]
            data = [self._read_target(self.end[48] + i)
                    if i < first_size else self._read_target(self.end[50] + i - first_size)
                    for i in range(size)]
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


def test_torque_on_primes_goal_at_measured_position_and_restores_end():
    bus = FakeBus()
    bus.hand[33] = 0
    original_end = bus.end.copy()
    original_buffer = bytes(bus.buffer)
    for motor_id in MOTOR_IDS:
        motor = bus.motors[motor_id]
        motor[10] &= ~8  # Physical hand: goal updates do not turn torque on.
        motor[64] = 0
        motor[102:104] = pack("<H", 300)
        motor[116:120] = pack("<I", 1500)
        motor[132:136] = pack("<I", 1600 + motor_id)
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    enabled = proxy.enable_motor_torque(load_vendor_motor_settings(XACRO))
    assert enabled == MOTOR_IDS
    for motor_id in MOTOR_IDS:
        motor = bus.motors[motor_id]
        assert motor[64] == 1
        assert motor[102:104] == pack("<H", 100)
        assert motor[116:120] == motor[132:136]
    assert bus.end == original_end
    assert bytes(bus.buffer[:12]) == original_buffer[:12]
    assert bus.goals == {}


def test_torque_status_reads_all_motors_without_motor_writes():
    bus = FakeBus()
    for motor_id, motor in bus.motors.items():
        motor[64] = int(motor_id == 141)
    original_end = bus.end.copy()
    original_motors = {motor_id: bytes(motor)
                       for motor_id, motor in bus.motors.items()}
    states = EndDirect(None, bus, sleep=lambda _: None).inspect_motor_torques()
    assert states == {motor_id: (int(motor_id == 141), 0)
                      for motor_id in MOTOR_IDS}
    assert bus.end == original_end
    assert {motor_id: bytes(motor) for motor_id, motor in bus.motors.items()} == original_motors


def test_tactile_probe_checks_all_five_ids_without_goals_and_reports_bad_id():
    bus = FakeBus()
    original_end = bus.end.copy()
    bus.sensors[155][7] = 0
    result = EndDirect(None, bus, sleep=lambda _: None).inspect_tactile_sensors()
    assert set(result) == set(SENSOR_IDS)
    assert result[145]["model"] == 6005
    assert result[145]["pressures"] == tuple(range(1, 10))
    assert "error" in result[155]
    assert all("error" not in result[sensor_id] for sensor_id in SENSOR_IDS if sensor_id != 155)
    assert bus.end == original_end
    assert bus.goals == {}


def test_torque_write_verification_retries_a_stale_end_read_without_rewriting():
    class StaleOnceBus(FakeBus):
        stale_reply = False
        stale_reads = 0

        def writeTxRx(self, port, device_id, address, size, data):
            result, error = super().writeTxRx(port, device_id, address, size, data)
            if (address == 46 and data == [1] and self.end[13] == 141
                    and self.end[60] == 2 and self.end[56] == 102):
                self.stale_reply = True
            return result, error

        def readTxRx(self, port, device_id, address, size):
            data, result, error = super().readTxRx(port, device_id, address, size)
            if address == 72 and self.end[48] == 102 and self.stale_reply:
                self.stale_reply = False
                self.stale_reads += 1
                return [0, 0], result, error
            return data, result, error

    bus = StaleOnceBus()
    bus.motors[141][64] = 0
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    with proxy.temporary_read_window(tool_id=141):
        proxy._write_selected_motor(141, 102, pack("<H", 100))
        assert bus.end_writes.count(200) == 1
    assert bus.stale_reads == 1
    assert bus.motors[141][102:104] == pack("<H", 100)
    assert bus.end_writes.count(200) == 2  # Saved END buffer restoration.


def test_torque_on_aborts_before_any_write_if_a_motor_watchdog_is_active():
    bus = FakeBus()
    bus.hand[33] = 0
    for motor in bus.motors.values():
        motor[10] &= ~8
        motor[64] = 0
        motor[132:136] = pack("<I", 2048)
    bus.motors[164][98] = 100
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    with pytest.raises(EndProxyError, match="watchdog=100"):
        proxy.enable_motor_torque(load_vendor_motor_settings(XACRO))
    assert all(motor[64] == 0 for motor in bus.motors.values())
    assert all(motor[102:104] == b"\x00\x00" for motor in bus.motors.values())


def test_torque_on_rolls_back_motors_after_a_failed_enable():
    class FaultBus(FakeBus):
        def _write_target(self, address, value):
            if self.end[13] == 143 and address == 64 and value == 1:
                return  # Simulate a motor that never accepts Torque Enable.
            super()._write_target(address, value)

    bus = FaultBus()
    bus.hand[33] = 0
    for motor in bus.motors.values():
        motor[10] &= ~8
        motor[64] = 0
        motor[132:136] = pack("<I", 2048)
    original_end = bus.end.copy()
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    with pytest.raises(EndProxyError, match="motor 143 register 64 did not verify"):
        proxy.enable_motor_torque(load_vendor_motor_settings(XACRO))
    assert all(motor[64] == 0 for motor in bus.motors.values())
    assert bus.end == original_end


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
    assert bus.hand_reads_with_write_slot == 0
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
    assert bus.hand[8] == 0
    assert bytes(bus.hand[122:462]) == pack("<170H", *INDIRECT_TARGETS)
    assert bus.end == original_end
    assert bytes(bus.buffer[:12]) == original_buffer[:12]


def test_direct_launch_sets_watchdog_only_while_active():
    bus = FakeBus()
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    proxy.prepare_direct(apply=True)
    assert proxy.verify_direct_setup() == 0
    with proxy.direct_session():
        assert bus.hand[8] == 100
        assert not bus.goals
    assert bus.hand[70] == 0
    assert bus.hand[8] == 0


def test_direct_verify_reports_unexpected_watchdog_value():
    bus = FakeBus()
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    proxy.prepare_direct(apply=True)
    bus.hand[8] = 255
    with pytest.raises(EndProxyError, match="Bus Watchdog is 255"):
        proxy.verify_direct_setup()


def test_indirect_health_probe_exposes_corrupt_full_window_without_hand_goals():
    class CorruptLongReadBus(FakeBus):
        def readTxRx(self, port, device_id, address, size):
            data, result, error = super().readTxRx(port, device_id, address, size)
            if address == 72 and self.end[48] == 634 and size == 90:
                data[89] = 32
            return data, result, error

    bus = CorruptLongReadBus()
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    proxy.prepare_direct(apply=True)
    original_end = bus.end.copy()
    result = proxy.compare_indirect_health()
    assert [item["status"] for item in result["indirect"]] == [32] * 3
    assert result["direct"]["status"] == 0
    assert bus.end == original_end
    assert bus.goals == {}


def test_active_health_probe_compares_paths_and_disables_hand_sync():
    class CorruptOnlyWhenActiveBus(FakeBus):
        def readTxRx(self, port, device_id, address, size):
            data, result, error = super().readTxRx(port, device_id, address, size)
            if (address == 72 and self.end[48] == 634 and size == 90
                    and self.hand[70] == 1):
                data[89] = 32
            return data, result, error

    bus = CorruptOnlyWhenActiveBus()
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    proxy.prepare_direct(apply=True)
    original_end = bus.end.copy()
    samples = proxy.compare_active_health()
    assert len(samples) == 3
    assert [sample["indirect"]["status"] for sample in samples] == [32] * 3
    assert [sample["direct"]["status"] for sample in samples] == [0] * 3
    assert all(sample["table_sync"] == 1 and sample["hardware_error"] == 0
               and sample["watchdog"] == 100 for sample in samples)
    assert bus.hand[70] == 0 and bus.hand[8] == 0
    assert bus.end == original_end
    assert bus.goals == {}


def test_direct_read_rejects_stale_end_buffer_and_restores_end():
    bus = FakeBus()
    bus.hand[33] = 0
    bus.freeze_hand_tick = True
    original_end = bus.end.copy()
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    with pytest.raises(EndProxyError, match="did not receive a fresh HX5 response"):
        proxy.verify_direct_setup()
    assert bus.end == original_end


def test_direct_hand_read_uses_only_bounded_first_slot():
    class FirstSlotOnlyBus(FakeBus):
        def readTxRx(self, port, device_id, address, size):
            if address == 72 and self.end[13] == 140:
                assert self.end[52] <= 16
                assert self.end[54] == 0
            return super().readTxRx(port, device_id, address, size)

    bus = FirstSlotOnlyBus()
    bus.hand[33] = 0
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    assert proxy.diagnose_hand()["model"] == 261
    assert proxy.diagnose_hand()["tick"] > 0
    assert not bus.goals


def test_direct_diagnosis_uses_fresh_hand_tick_without_hand_writes():
    bus = FakeBus()
    original_end = bus.end.copy()
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    state = proxy.diagnose_hand()
    assert state["model"] == 261 and state["id"] == 140
    assert state["mode"] == 1 and state["watchdog"] == 0
    assert state["tick"] > 0 and state["voltage_centivolts"] == 2368
    assert state["status"] == 0
    assert state["end_tool_status"] == 0
    assert bus.end == original_end
    assert not bus.goals


def test_clear_idle_watchdog_writes_only_error_reset_without_motor_goal():
    bus = FakeBus()
    original_end = bus.end.copy()
    bus.hand[33] = 0
    bus.hand[8] = 255
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    assert proxy.clear_idle_watchdog() == (255, 0)
    assert bus.hand[8] == 0
    assert bus.hand[70] == 0
    assert not bus.goals
    assert bus.end == original_end


def test_clear_idle_watchdog_rejects_active_hand_tablesync():
    bus = FakeBus()
    bus.hand[33] = 0
    bus.hand[70] = 1
    bus.hand[8] = 255
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    with pytest.raises(EndProxyError, match="cannot clear HX5 watchdog"):
        proxy.clear_idle_watchdog()
    assert bus.hand[8] == 255
    assert not bus.goals


def test_clear_idle_watchdog_accepts_official_status_bit_and_verifies_clear():
    class WatchdogBus(FakeBus):
        def _write_target(self, address, value):
            super()._write_target(address, value)
            if self._device() is self.hand and address == 8 and value == 0:
                self.hand[106] = 0

    bus = WatchdogBus()
    bus.hand[33] = 0
    bus.hand[8] = 255
    bus.hand[106] = 64
    proxy = EndDirect(None, bus, sleep=lambda _: None)
    assert proxy.clear_idle_watchdog() == (255, 0)
    assert bus.hand[106] == 0
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
