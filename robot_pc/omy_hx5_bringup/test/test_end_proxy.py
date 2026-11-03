"""The END probe must never address the hand directly or leave END reconfigured."""

import pytest
from struct import pack

from omy_hx5_bringup.end_proxy import (
    COMM_RX_TIMEOUT, EndProxy, EndProxyError, SAVED_REGISTERS,
)


class FakePacket:
    def __init__(self, hand_model=261):
        self.hand = {0: hand_model & 255, 1: hand_model >> 8,
                     7: 140, 102: 0x40, 103: 0x09, 106: 0}
        self.motor = {0: 0x34, 1: 0x12, 7: 141, 10: 13, 11: 5, 64: 1,
                      168: 126, 169: 0, 170: 127, 171: 0}
        self.hand_indirect = bytearray(pack("<5H", 634, 635, 636, 637, 638))
        self.high = {1024 + i: 141 + i for i in range(5)}
        self.hand_goals = []
        self.buffer = bytearray(128)
        self.fail_high_read_once = False
        self.end = {13: 1, 46: 1, 48: 634, 50: 0, 52: 16, 54: 0,
                    56: 665, 58: 0, 60: 12, 62: 0}
        self.writes = []

    @staticmethod
    def getTxRxResult(result):
        return "OK" if result == 0 else "failure"

    @staticmethod
    def ping(port, device_id):
        assert device_id == 210
        return 230, 0, 0

    def readTxRx(self, port, device_id, address, size):
        assert device_id == 210
        if address == 72:
            assert self.end[13] in (140, 141) and self.end[46] == 1
            if (self.fail_high_read_once and self.end[48] == 634):
                self.fail_high_read_once = False
                raise EndProxyError("injected high-register read failure")
            device = self.hand if self.end[13] == 140 else self.motor
            data = []
            for i in range(size):
                target = self.end[48] + i
                if self.end[13] == 140 and 122 <= target < 132:
                    data.append(self.hand_indirect[target - 122])
                elif self.end[13] == 140 and 634 <= target < 639:
                    offset = target - 634
                    indirect_target = int.from_bytes(
                        self.hand_indirect[2 * offset:2 * offset + 2], "little")
                    data.append(self.high.get(indirect_target, 0))
                else:
                    data.append(device.get(target, 0))
        elif address == 200:
            data = list(self.buffer[:size])
        else:
            value = self.end[address]
            data = list(value.to_bytes(size, "little"))
        return data, 0, 0

    def writeTxRx(self, port, device_id, address, size, data):
        assert device_id == 210
        self.writes.append((address, size, tuple(data)))
        if address == 200:
            self.buffer[:size] = bytes(data)
        else:
            self.end[address] = int.from_bytes(bytes(data), "little")
            if (address == 46 and self.end[46] == 1
                    and self.end[13] == 140 and self.end[56] == 122
                    and self.end[60] == 10):
                self.hand_indirect[:] = self.buffer[:10]
            if (address == 46 and self.end[46] == 1
                    and self.end[13] == 140 and self.end[56] == 634
                    and self.end[60] == 4):
                goal = bytes(self.buffer[:4])
                self.hand_goals.append(goal)
                for offset, value in enumerate(goal):
                    target = int.from_bytes(
                        self.hand_indirect[2 * offset:2 * offset + 2], "little")
                    self.high[target] = value
        return 0, 0


def test_end_proxy_identifies_left_hand_and_restores_end():
    packet = FakePacket()
    original = packet.end.copy()
    result = EndProxy(None, packet, sleep=lambda _: None).probe()
    assert result == {"end_model": 230, "hand_model": 261,
                      "hand_voltage_centivolts": 2368, "hand_status": 0}
    assert packet.end == original
    assert all(address in {a for a, _ in SAVED_REGISTERS}
               for address, _, _ in packet.writes)
    assert any(address == 60 and data == (0, 0)
               for address, _, data in packet.writes)


def test_end_write_uses_readback_when_only_status_packet_is_lost():
    class LostAckPacket(FakePacket):
        lost_once = False

        def writeTxRx(self, port, device_id, address, size, data):
            result = super().writeTxRx(port, device_id, address, size, data)
            if address == 60 and not self.lost_once:
                self.lost_once = True
                return COMM_RX_TIMEOUT, 0
            return result

    packet = LostAckPacket()
    original = packet.end.copy()
    proxy = EndProxy(None, packet, sleep=lambda _: None)
    assert proxy.probe()["hand_model"] == 261
    assert packet.lost_once
    assert proxy.end_write_ack_timeouts == 1
    assert packet.end == original


def test_end_write_stops_when_timed_out_write_was_not_applied():
    class DroppedWritePacket(FakePacket):
        dropped_once = False

        def writeTxRx(self, port, device_id, address, size, data):
            if address == 60 and not self.dropped_once:
                self.dropped_once = True
                return COMM_RX_TIMEOUT, 0
            return super().writeTxRx(port, device_id, address, size, data)

    packet = DroppedWritePacket()
    original = packet.end.copy()
    with pytest.raises(EndProxyError, match="readback=12, requested=0"):
        EndProxy(None, packet, sleep=lambda _: None).probe()
    assert packet.end == original


def test_end_restoration_continues_after_one_tool_id_write_fails():
    class DroppedRestorePacket(FakePacket):
        def writeTxRx(self, port, device_id, address, size, data):
            if address == 13 and data == [1] and self.end[13] != 1:
                return COMM_RX_TIMEOUT, 0
            return super().writeTxRx(port, device_id, address, size, data)

    packet = DroppedRestorePacket()
    with pytest.raises(EndProxyError, match="END restoration incomplete; TableSync left off"):
        EndProxy(None, packet, sleep=lambda _: None).probe()
    assert packet.end[13] == 140
    assert packet.end[46] == 0
    assert packet.end[48] == 634
    assert packet.end[52] == 16
    assert packet.end[60] == 12


def test_end_restoration_verifies_late_tool_id_write_after_lost_ack():
    class LateReadPacket(FakePacket):
        lost_reads = 0

        def writeTxRx(self, port, device_id, address, size, data):
            result = super().writeTxRx(port, device_id, address, size, data)
            if address == 13 and data == [1]:
                self.lost_reads = 5
                return COMM_RX_TIMEOUT, 0
            return result

        def readTxRx(self, port, device_id, address, size):
            if address == 13 and self.lost_reads:
                self.lost_reads -= 1
                return [], COMM_RX_TIMEOUT, 0
            return super().readTxRx(port, device_id, address, size)

    packet = LateReadPacket()
    original = packet.end.copy()
    assert EndProxy(None, packet, sleep=lambda _: None).probe()["hand_model"] == 261
    assert packet.end == original


def test_end_proxy_restores_end_on_wrong_hand_model():
    packet = FakePacket(hand_model=260)
    original = packet.end.copy()
    with pytest.raises(EndProxyError, match="model"):
        EndProxy(None, packet, sleep=lambda _: None).probe()
    assert packet.end == original


def test_end_proxy_reads_motor_via_end_without_motor_writes():
    packet = FakePacket()
    original = packet.end.copy()
    motor = EndProxy(None, packet, sleep=lambda _: None).probe_motor(141)
    assert motor == {
        "model": 0x1234, "drive_mode": 13, "operating_mode": 5,
        "torque_enabled": 1, "indirect_address_1_2": (126, 127),
    }
    assert packet.end == original
    assert all(address != 7 for address, _, _ in packet.writes)


@pytest.mark.parametrize("mode", [0, 1])
def test_inspect_sync_ids_restores_hand_and_end_eeprom(mode):
    packet = FakePacket()
    packet.hand[33] = mode
    original_end = packet.end.copy()
    original_hand = packet.hand_indirect[:]
    original_buffer = packet.buffer[:]
    observed_mode, ids = EndProxy(None, packet, sleep=lambda _: None).inspect_sync_ids()
    assert observed_mode == mode
    assert ids == (141, 142, 143, 144, 145)
    assert packet.end == original_end
    assert packet.hand_indirect == original_hand
    assert packet.buffer == original_buffer
    assert all(address in {a for a, _ in SAVED_REGISTERS} | {200}
               for address, _, _ in packet.writes)


def test_inspect_sync_ids_restores_after_high_register_failure():
    packet = FakePacket()
    packet.fail_high_read_once = True
    original_end = packet.end.copy()
    original_hand = packet.hand_indirect[:]
    original_buffer = packet.buffer[:]
    with pytest.raises(EndProxyError, match="injected"):
        EndProxy(None, packet, sleep=lambda _: None).inspect_sync_ids()
    assert packet.end == original_end
    assert packet.hand_indirect == original_hand
    assert packet.buffer == original_buffer


def test_preset_session_has_no_startup_motion_and_restores_aliases():
    packet = FakePacket()
    packet.hand[33] = 1
    packet.hand[70] = 0
    original_end = packet.end.copy()
    original_aliases = packet.hand_indirect[:]
    original_buffer = packet.buffer[:]
    proxy = EndProxy(None, packet, sleep=lambda _: None)
    with proxy.preset_session() as state:
        assert state == {"hand_model": 261, "mode": 1,
                         "voltage_centivolts": 2368, "status": 0}
        assert packet.hand_goals == []
        assert packet.hand_indirect == original_aliases
        proxy.send_preset(index=0, percent=5, duration_ms=1000)
        assert packet.hand_goals == [bytes((0, 5, 232, 3))]
        assert packet.end[60] == 0
        with pytest.raises(ValueError, match="preset requires"):
            proxy.send_preset(index=3, percent=5, duration_ms=1000)
    assert packet.end == original_end
    assert packet.hand_indirect == original_aliases
    assert packet.buffer == original_buffer


def test_preset_bringup_without_command_does_not_write_hand_aliases():
    packet = FakePacket()
    packet.hand[33] = 1
    packet.hand[70] = 0
    original_end = packet.end.copy()
    original_aliases = packet.hand_indirect[:]
    with EndProxy(None, packet, sleep=lambda _: None).preset_session():
        assert packet.hand_goals == []
        assert packet.hand_indirect == original_aliases
    assert packet.end == original_end
    assert packet.hand_indirect == original_aliases
    assert all(address != 200 for address, _, _ in packet.writes)


def test_preset_session_rejects_direct_mode_without_motor_command():
    packet = FakePacket()
    packet.hand[33] = 0
    packet.hand[70] = 0
    original_end = packet.end.copy()
    with pytest.raises(EndProxyError, match="not ready for preset"):
        with EndProxy(None, packet, sleep=lambda _: None).preset_session():
            pass
    assert packet.hand_goals == []
    assert packet.end == original_end
