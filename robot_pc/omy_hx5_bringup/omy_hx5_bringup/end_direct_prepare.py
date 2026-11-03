"""Audit the left HX5 and prepare its five TableSync channels through END 210.

Default is read-only except for temporary END/indirect alias setup, which is
restored. --apply writes the HX5 channel configuration and selects mode 0.
No motor goal is sent. Run only with no other owner of /dev/ttyAMA4.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .end_direct_core import EndDirect, load_vendor_motor_settings
from .end_proxy import EndProxyError, acquire_end_bus_lock


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyAMA4")
    parser.add_argument("--baud", type=int, default=4_000_000)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true",
                      help="write HX5 TableSync configuration and select Direct Mode 0")
    mode.add_argument("--restore-preset", action="store_true",
                      help="return HX5 controller to Preset Mode 1 without a goal")
    mode.add_argument("--verify-direct", action="store_true",
                      help="check Direct Mode and persistent aliases without applying them")
    mode.add_argument("--clear-watchdog", action="store_true",
                      help="clear an idle HX5 Bus Watchdog error without a motor goal")
    args = parser.parse_args(argv)
    try:
        from ament_index_python.packages import get_package_share_directory
        from dynamixel_sdk import PacketHandler, PortHandler
    except ModuleNotFoundError as exc:
        parser.exit(1, f"Missing Robot PC dependency: {exc.name}\n")

    xacro = (Path(get_package_share_directory("robotis_hand_description")) /
             "ros2_control/hx5_d20_rev2/hx5_d20_left.ros2_control.xacro")
    expected = load_vendor_motor_settings(xacro)
    try:
        lock_fd = acquire_end_bus_lock()
    except EndProxyError as exc:
        parser.exit(1, f"END direct preparation failed: {exc}\n")
    port = PortHandler(args.port)
    if not port.openPort():
        parser.exit(1, f"Cannot open {args.port}; stop other END owners first\n")
    try:
        if not port.setBaudRate(args.baud):
            raise EndProxyError(f"cannot set {args.port} to {args.baud} baud")
        direct = EndDirect(port, PacketHandler(2.0))
        if args.restore_preset:
            previous = direct.restore_preset_mode()
            print(f"HX5 Preset Motion Mode 1 ready; prior mode={previous}; "
                  "no motor goal sent.")
            if direct.end_write_ack_timeouts:
                print(f"END 210 write status packets missing {direct.end_write_ack_timeouts} "
                      "time(s); each register value was confirmed by readback.")
            return 0
        if args.verify_direct:
            watchdog = direct.verify_direct_setup()
            print(f"HX5 Direct Control Mode 0 and persistent aliases verified; "
                  f"idle Bus Watchdog={watchdog}; "
                  "no motor goal sent.")
            if direct.end_write_ack_timeouts:
                print(f"END 210 write status packets missing {direct.end_write_ack_timeouts} "
                      "time(s); each register value was confirmed by readback.")
            return 0
        if args.clear_watchdog:
            prior, current = direct.clear_idle_watchdog()
            print(f"HX5 idle Bus Watchdog cleared: prior={prior}, current={current}; "
                  "no motor goal sent.")
            if direct.end_write_ack_timeouts:
                print(f"END 210 write status packets missing {direct.end_write_ack_timeouts} "
                      "time(s); each register value was confirmed by readback.")
            return 0
        issues = direct.audit_motors(expected)
        if issues:
            raise EndProxyError("motor configuration differs from ROBOTIS Xacro:\n" +
                                "\n".join(issues))
        print("All 20 HX5 actuators identified and match ROBOTIS setup; no motor goal sent.")
        old_mode, changed = direct.prepare_direct(apply=args.apply)
        if args.apply:
            print(f"HX5 Direct Control Mode 0 ready; prior mode={old_mode}; "
                  f"TableSync channels updated={changed}; no motor goal sent.")
        else:
            print(f"HX5 mode={old_mode}; TableSync channels needing setup={changed}. "
                  "Use --apply to configure after reviewing this result.")
        if direct.end_write_ack_timeouts:
            print(f"END 210 write status packets missing {direct.end_write_ack_timeouts} "
                  "time(s); each register value was confirmed by readback.")
        return 0
    except (EndProxyError, OSError, ValueError) as exc:
        parser.exit(1, f"END direct preparation failed: {exc}\n")
    finally:
        port.closePort()
        import os
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
