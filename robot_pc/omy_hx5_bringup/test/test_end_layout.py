"""Check the END layout against the vendored ROBOTIS left-hand Xacro."""

from math import isclose
from pathlib import Path
from xml.etree import ElementTree

import pytest

from omy_hx5_bringup.end_layout import (
    INDIRECT_TARGETS, READ_SIZE, READ_TARGETS, WRITE_SIZE, WRITE_TARGETS,
    WRITE_WINDOW, decode_state, encode_command,
)


def test_compact_layout_matches_vendor_table_sync_channels():
    path = (Path(__file__).resolve().parents[3] / "third_party/robotis_hand"
            / "robotis_hand_description/ros2_control/hx5_d20_rev2"
            / "hx5_d20_left.joints.xacro")
    root = ElementTree.parse(path).getroot()
    controller = next(g for g in root.iter("gpio")
                      if g.attrib.get("name") == "hand_l_controller")
    values = {p.attrib["name"]: int(p.text) for p in controller.iter("param")
              if p.attrib["name"] not in ("type",)}
    for channel in range(5):
        finger = channel + 1
        for motor in range(4):
            slot = motor + 1
            prefix = f"SyncTable {finger}"
            assert values[f"{prefix} Read Address {slot}"] == 224
            assert values[f"{prefix} Read Size {slot}"] == 6
            assert values[f"{prefix} Write Address {slot}"] == 230
            assert values[f"{prefix} Write Size {slot}"] == 4
            base = 17 * channel + 2 * motor
            assert READ_TARGETS[base:base + 2] == (
                1078 + 198 * channel + 6 * motor + 4,
                1078 + 198 * channel + 6 * motor + 5,
            )
        assert values[f"SyncTable {finger} Read Address 5"] == 72
        assert values[f"SyncTable {finger} Read Size 5"] == 9
        assert values[f"SyncTable {finger} Write Size 5"] == 0
        assert values[f"SyncTable {finger} ID 5"] == 140 + 5 * finger
    assert READ_SIZE == 85 and WRITE_SIZE == 80
    assert WRITE_WINDOW == 719
    assert len(INDIRECT_TARGETS) == 165


def test_state_and_goal_byte_layout():
    state = bytearray()
    for channel in range(5):
        for _ in range(4):
            state.extend((2048).to_bytes(2, "little"))
        state.extend([channel] * 9)
    positions, pressures = decode_state(bytes(state))
    assert len(positions) == 20
    assert all(isclose(position, 0.0, abs_tol=1e-12) for position in positions)
    assert pressures == tuple((channel,) * 9 for channel in range(5))
    command = encode_command(positions, 300)
    assert len(command) == 80
    assert command[:4] == bytes((44, 1, 0, 8))
    with pytest.raises(ValueError):
        encode_command((float("nan"),) * 20, 300)
