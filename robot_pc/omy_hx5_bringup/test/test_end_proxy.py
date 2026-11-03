"""The END probe must never address the hand directly or leave END reconfigured."""

import pytest
from struct import pack

from omy_hx5_bringup.end_proxy import EndProxy, EndProxyError, SAVED_REGISTERS


class FakePacket:
    def __init__(self, hand_model=261):
        self.hand = {0: hand_model & 255, 1: hand_model >> 8,
                     7: 140, 102: 0x40, 103: 0x09, 106: 0}
        self.motor = {0: 0x34, 1: 0x12, 7: 141, 10: 13, 11: 5, 64: 1,
                      168: 126, 169: 0, 170: 127, 171: 0}
        self.hand_indirect = bytearray(pack("<5H", 634, 635, 636, 637, 638))
        self.high = {1024 + i: 141 + i for i in range(5)}
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
