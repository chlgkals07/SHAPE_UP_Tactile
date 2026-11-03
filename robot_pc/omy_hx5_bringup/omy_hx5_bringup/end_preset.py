"""ROS 2 preset control for a left HX5 reached through OMY END ID 210.

The node only opens the END bus and verifies the hand at startup. It never
sends a motion request until an Int32 percentage arrives on the preset topic.
"""

from __future__ import annotations

import argparse

from .end_proxy import EndProxy, EndProxyError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyAMA4")
    parser.add_argument("--baud", type=int, default=4_000_000)
    parser.add_argument("--preset-index", type=int, choices=range(3), default=0)
    parser.add_argument("--motion-time-ms", type=int, default=1000)
    args, ros_args = parser.parse_known_args(argv)
    if ros_args and ros_args[0] != "--ros-args":
        parser.error(f"unrecognized arguments: {' '.join(ros_args)}")
    if not 1 <= args.motion_time_ms <= 32737:
        parser.error("--motion-time-ms must be 1..32737")

    try:
        import rclpy
        from rclpy.executors import ExternalShutdownException
        from dynamixel_sdk import PacketHandler, PortHandler
        from std_msgs.msg import Int32
    except ModuleNotFoundError as exc:
        parser.exit(1, f"Missing Robot PC dependency: {exc.name}\n")

    port = PortHandler(args.port)
    if not port.openPort():
        parser.exit(1, f"Cannot open {args.port}; stop other END owners first\n")
    try:
        if not port.setBaudRate(args.baud):
            raise EndProxyError(f"cannot set {args.port} to {args.baud} baud")
        proxy = EndProxy(port, PacketHandler(2.0))
        with proxy.preset_session() as state:
            rclpy.init(args=ros_args)
            node = rclpy.create_node("omy_hx5_end_preset")
            callback_error = None

            def on_percent(message):
                nonlocal callback_error
                if not 0 <= message.data <= 100:
                    node.get_logger().error("Preset percentage must be 0..100; command ignored")
                    return
                try:
                    proxy.send_preset(index=args.preset_index, percent=message.data,
                                      duration_ms=args.motion_time_ms)
                    node.get_logger().info(
                        f"END 210 -> HX5 140 preset {args.preset_index}: "
                        f"{message.data}% in {args.motion_time_ms} ms; register echo OK. "
                        "Observe the physical hand to verify motion.")
                except (EndProxyError, OSError) as exc:
                    callback_error = exc
                    node.get_logger().error(f"END preset command failed: {exc}")
                    rclpy.shutdown()

            node.create_subscription(Int32, "/omy_hx5/preset_percent", on_percent, 10)
            node.get_logger().info(
                f"END 210 -> left HX5 140 ready: model {state['hand_model']}, "
                f"Preset Mode {state['mode']}, {state['voltage_centivolts']/100:.2f} V, "
                f"status {state['status']}. No motion command sent. "
                "Publish std_msgs/Int32 on /omy_hx5/preset_percent to move.")
            try:
                rclpy.spin(node)
            except (KeyboardInterrupt, ExternalShutdownException):
                pass
            finally:
                node.destroy_node()
                if rclpy.ok():
                    rclpy.shutdown()
            if callback_error is not None:
                raise callback_error
        return 0
    except (EndProxyError, OSError) as exc:
        parser.exit(1, f"END preset bringup failed: {exc}\n")
    finally:
        port.closePort()


if __name__ == "__main__":
    raise SystemExit(main())
