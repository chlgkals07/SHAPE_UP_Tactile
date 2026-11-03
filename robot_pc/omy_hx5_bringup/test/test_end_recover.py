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


def test_end_recovery_rejects_unexpected_active_write_window():
    packet = FakePacket()
    packet.end[13] = 140
    with pytest.raises(EndProxyError, match="recovery requires"):
        restore_stock(EndProxy(None, packet), apply=True)
    assert not packet.writes
