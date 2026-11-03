"""Enable HX5 motor torque through OMY END after matching goals to positions.

The command writes the official Profile Acceleration/Velocity and Position
P/D gains (RAM, cleared by a power cycle), then Goal Current, Goal Position,
and Torque Enable for motors whose torque is off.
It never sends a grasp or teleoperation trajectory. Stop other END owners.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .end_direct_core import (
    EndDirect, MOTOR_IDS, STARTUP_GOAL_CURRENT, load_vendor_motor_settings,
)
from .end_proxy import EndProxyError, acquire_end_bus_lock, make_fresh_rx_port
from .end_recover import STOCK_END, read_end_settings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyAMA4")
    parser.add_argument("--baud", type=int, default=4_000_000)
    parser.add_argument("--motor-id", type=int, choices=MOTOR_IDS,
                        help="enable only one motor first; default enables all 20")
    args = parser.parse_args(argv)

    from ament_index_python.packages import get_package_share_directory
    from dynamixel_sdk import PacketHandler

    xacro = (Path(get_package_share_directory("robotis_hand_description")) /
             "ros2_control/hx5_d20_rev2/hx5_d20_left.ros2_control.xacro")
    expected = load_vendor_motor_settings(xacro)
    try:
        lock_fd = acquire_end_bus_lock()
    except EndProxyError as exc:
        parser.exit(1, f"HX5 torque enable failed: {exc}\n")
    port = make_fresh_rx_port(args.port)
    try:
        if not port.openPort() or not port.setBaudRate(args.baud):
            raise EndProxyError(f"cannot open {args.port} at {args.baud} baud")
        direct = EndDirect(port, PacketHandler(2.0))
        end_settings = read_end_settings(direct)
        if end_settings != STOCK_END:
            raise EndProxyError(
                "END 210 is not at stock OMY settings; inspect and recover "
                f"before enabling torque: {end_settings}")
        enabled = direct.enable_motor_torque(expected, motor_id=args.motor_id)
        count = 1 if args.motor_id is not None else len(MOTOR_IDS)
        print(f"HX5 motor torque ON verified: {count} selected, "
              f"{len(enabled)} newly enabled. Goal Position was set to each "
              "newly enabled motor's measured position and startup Goal "
              f"Current to {STARTUP_GOAL_CURRENT}. Official Profile/P/D RAM "
              f"settings written to {direct.ram_updated_motors or 'none (already set)'}. "
              "No grasp trajectory sent.")
        return 0
    except (EndProxyError, OSError, ValueError) as exc:
        parser.exit(1, f"HX5 torque enable failed: {exc}\n")
    finally:
        if port.is_open:
            port.closePort()
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
