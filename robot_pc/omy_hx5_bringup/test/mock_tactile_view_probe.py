"""Send synthetic left-hand pressure to the official visualization node.

Use with omy_hx5_tactile_view.launch.py start_rviz:=false
start_heatmap:=false pressure_topic:=/hx5/test_pressures.
"""

import argparse
import json
import math
import time
from pathlib import Path

import rclpy
from rclpy.executors import SingleThreadedExecutor
from robotis_interfaces.msg import HandPressures, TactileSensor
from visualization_msgs.msg import MarkerArray


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node("omy_hx5_mock_tactile_view_probe")
    publisher = node.create_publisher(HandPressures, "/hx5/test_pressures", 10)
    received = []
    node.create_subscription(MarkerArray, "/tactile_force_markers", received.append, 10)
    executor = SingleThreadedExecutor()
    executor.add_node(node)

    def publish(touched: bool, seconds: float) -> None:
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            message = HandPressures()
            message.header.stamp = node.get_clock().now().to_msg()
            message.hand_name = "left"
            for finger in range(1, 6):
                sensor = TactileSensor()
                sensor.sensor_name = f"finger_l_sensor{finger}"
                sensor.pressure_names = [f"Present Pressure {i}" for i in range(1, 10)]
                values = [0.0] * 9
                if touched and finger == 1:
                    values[4] = 100.0
                if touched and finger == 2:
                    values[0] = 80.0
                sensor.pressure_values = values
                message.sensors.append(sensor)
            publisher.publish(message)
            executor.spin_once(timeout_sec=0.01)
            time.sleep(0.04)

    try:
        publish(False, 1.8)
        if not received:
            raise AssertionError("official tactile_rviz published no MarkerArray")
        received.clear()
        publish(True, 1.2)
        if not received:
            raise AssertionError("no marker update after synthetic contact")
        markers = received[-1].markers
        arrows = {m.id: m for m in markers if m.ns == "tactile_force"}
        dots = {m.id: m for m in markers if m.ns == "tactile_force_cop"}
        if set(arrows) != set(range(5)) or set(dots) != set(range(5)):
            raise AssertionError("expected five tactile arrows and five CoP dots")
        if not all(arrows[index].header.frame_id == f"finger_end_l_link{index + 1}"
                   for index in range(5)):
            raise AssertionError("markers do not use left fingertip frames")
        if not (arrows[0].color.a > 0.0 and arrows[1].color.a > 0.0
                and all(arrows[index].color.a == 0.0 for index in (2, 3, 4))):
            raise AssertionError("marker visibility did not follow touched fingertips")

        # The official marker stores its displayed arrow from points[0] to points[1].
        # Start-minus-end is the source's computed vector in each fingertip frame.
        vectors = {}
        lengths = {}
        for finger in (0, 1):
            marker = arrows[finger]
            if len(marker.points) != 2:
                raise AssertionError("tactile arrow has no start/end points")
            start, end = marker.points
            vector = [start.x - end.x, start.y - end.y, start.z - end.z]
            vectors[finger + 1] = vector
            lengths[finger + 1] = math.sqrt(sum(component ** 2 for component in vector))
        if not (0.04 < lengths[1] <= 0.051 and 0.03 < lengths[2] < lengths[1]):
            raise AssertionError(f"arrow lengths did not scale with pressure: {lengths}")
        if not (abs(vectors[1][0]) < 1e-5 and abs(vectors[1][1]) < 1e-5
                and vectors[1][2] > 0.0):
            raise AssertionError(f"center thumb taxel changed arrow direction: {vectors[1]}")
        if not (vectors[2][0] > 0.0 and vectors[2][1] < 0.0
                and vectors[2][2] > 0.0):
            raise AssertionError(f"index corner taxel did not tilt arrow: {vectors[2]}")
        summary = {
            "source": "synthetic 0..255 pressure counts, not measured force",
            "arrow_frames": [arrows[index].header.frame_id for index in range(5)],
            "visible_arrows": [index + 1 for index in range(5) if arrows[index].color.a > 0.0],
            "visible_cop_dots": [index + 1 for index in range(5) if dots[index].color.a > 0.0],
            "start_minus_end_vectors_m": vectors,
            "arrow_lengths_m": lengths,
        }
        if args.output_json:
            args.output_json.write_text(json.dumps(summary, indent=2) + "\n")
        print("PASS: synthetic pressure -> official left RViz arrow visibility, length, direction, and CoP", flush=True)
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
