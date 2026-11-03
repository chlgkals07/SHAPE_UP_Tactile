"""The END probe must never address the hand directly or leave END reconfigured."""

import pytest

from omy_hx5_bringup.end_proxy import EndProxy, EndProxyError, SAVED_REGISTERS


class FakePacket:
    def __init__(self, hand_model=261):
        self.hand = {0: hand_model & 255, 1: hand_model >> 8,
                     102: 0x40, 103: 0x09, 106: 0}
        self.end = {13: 1, 46: 1, 48: 634, 50: 0, 52: 16, 54: 0,
                    60: 12, 62: 0}
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
            assert self.end[13] == 140 and self.end[46] == 1
            data = [self.hand.get(self.end[48] + i, 0) for i in range(size)]
        else:
            value = self.end[address]
            data = list(value.to_bytes(size, "little"))
        return data, 0, 0

    def writeTxRx(self, port, device_id, address, size, data):
        assert device_id == 210
        self.writes.append((address, size, tuple(data)))
        self.end[address] = int.from_bytes(bytes(data), "little")
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
