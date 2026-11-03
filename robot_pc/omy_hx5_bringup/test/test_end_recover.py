"""The interrupted END recovery must be opt-in and verify every saved setting."""

import pytest

from omy_hx5_bringup.end_proxy import EndProxy, EndProxyError
from omy_hx5_bringup.end_recover import STOCK_END, restore_stock
from test_end_proxy import FakePacket


def test_end_recovery_is_read_only_by_default():
    packet = FakePacket()
    packet.end.update({46: 0, 48: 0, 52: 24, 60: 0})
    before, after = restore_stock(EndProxy(None, packet), apply=False)
    assert before == after == packet.end
    assert not packet.writes


def test_end_recovery_restores_stock_without_motor_command():
    packet = FakePacket()
    packet.end.update({46: 0, 48: 0, 52: 24, 60: 0})
    before, after = restore_stock(EndProxy(None, packet, sleep=lambda _: None), apply=True)
    assert before[46] == 0 and before[48] == 0
    assert after == packet.end == STOCK_END
    assert all(address in STOCK_END for address, _, _ in packet.writes)
    assert packet.hand_goals == []


def test_end_recovery_accepts_restored_sizes_with_sync_left_off():
    packet = FakePacket()
    packet.end[46] = 0
    _, after = restore_stock(EndProxy(None, packet, sleep=lambda _: None), apply=True)
    assert after == STOCK_END


def test_end_recovery_accepts_paused_stock_with_hand_tool_id():
    packet = FakePacket()
    packet.end.update({13: 140, 46: 0})
    before, after = restore_stock(EndProxy(None, packet, sleep=lambda _: None), apply=True)
    assert before[13] == 140 and before[46] == 0 and before[60] == 12
    assert after == STOCK_END
    assert packet.writes[0] == (13, 1, (1,))
    assert packet.hand_goals == []


def test_end_recovery_does_not_write_when_two_reads_disagree():
    class UnstablePacket(FakePacket):
        tool_reads = 0

        def readTxRx(self, port, device_id, address, size):
            data, result, error = super().readTxRx(port, device_id, address, size)
            if address == 13:
                self.tool_reads += 1
                if self.tool_reads == 2:
                    data = [140]
            return data, result, error

    packet = UnstablePacket()
    with pytest.raises(EndProxyError, match="readings are inconsistent"):
        restore_stock(EndProxy(None, packet), apply=True)
    assert not packet.writes


def test_end_recovery_restores_observed_hand_read_interruption():
    packet = FakePacket()
    packet.end.update({13: 140, 46: 0, 48: 8, 52: 1, 60: 0})
    interrupted = packet.end.copy()
    before, after = restore_stock(EndProxy(None, packet, sleep=lambda _: None), apply=True)
    assert before == interrupted
    assert after == packet.end == STOCK_END
    assert packet.hand_goals == []


def test_end_recovery_accepts_interrupted_fresh_hand_read():
    packet = FakePacket()
    packet.end.update({13: 140, 46: 0, 48: 0, 50: 100,
                       52: 107, 54: 2, 60: 0})
    _, after = restore_stock(EndProxy(None, packet, sleep=lambda _: None), apply=True)
    assert after == packet.end == STOCK_END
    assert packet.hand_goals == []


def test_end_recovery_rejects_unexpected_active_write_window():
    packet = FakePacket()
    packet.end[13] = 140
    with pytest.raises(EndProxyError, match="recovery requires"):
        restore_stock(EndProxy(None, packet), apply=True)
    assert not packet.writes
