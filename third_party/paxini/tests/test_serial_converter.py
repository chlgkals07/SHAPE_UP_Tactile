"""Offline tests for the Serial Converter Board driver.

No hardware required. Covers the 0x040E address fix and the point-count
resolution that replaced the hardcoded 77.
"""

import pytest

from paxini_sdk import registers
from paxini_sdk.boards.serial_converter import SingleSensorBoard, _resolve_n_points
from paxini_sdk.protocol import FIN_FUNC_FORCE, build_fin_request


def test_distributed_force_address_is_040e():
    # Both vendor reference programs address the distributed-force region at
    # 0x040E ("0E 04 00 00" little-endian). Regression guard for the old
    # 0x04E7 mis-parse.
    assert registers.FIN_ADDR_DISTRIBUTED_FORCE == 0x040E


def test_distributed_request_matches_vendor_frame():
    # Vendor: "55 AA 09 00 01 00 FB 0E 04 00 00 E7 00 03" (231 bytes @ 0x040E)
    frame = build_fin_request(
        FIN_FUNC_FORCE, registers.FIN_ADDR_DISTRIBUTED_FORCE,
        read=True, data_len=0x00E7, device_id=0x01,
    )
    assert frame.hex().upper().startswith("55AA09000100FB0E040000E700")
    assert frame[-1] == 0x03  # vendor LRC


def test_resolve_n_points_explicit():
    assert _resolve_n_points(None, 52) == 52


def test_resolve_n_points_from_part_code():
    # PXSR-STDDP03G is the DP-S2015-Elite fingertip: 52 points.
    assert _resolve_n_points("PXSR-STDDP03G", None) == 52


def test_resolve_n_points_explicit_overrides_sensor():
    assert _resolve_n_points("PXSR-STDDP03G", 99) == 99


def test_resolve_n_points_unknown_part_code_raises():
    with pytest.raises(KeyError):
        _resolve_n_points("PXSR-NOPE", None)


def test_resolve_n_points_none_when_nothing_supplied():
    assert _resolve_n_points(None, None) is None


def test_resolve_n_points_rejects_nonpositive():
    with pytest.raises(ValueError):
        _resolve_n_points(None, 0)


def test_board_exposes_n_points():
    board = SingleSensorBoard("/dev/fake-port", sensor="PXSR-STDDP03G")
    assert board.n_points == 52


def test_read_distributed_force_raises_without_count():
    # No sensor / n_points given and no point_count arg -> clear error
    # raised before any serial I/O is attempted.
    board = SingleSensorBoard("/dev/fake-port")
    assert board.n_points is None
    with pytest.raises(ValueError, match="point count"):
        board.read_distributed_force()
