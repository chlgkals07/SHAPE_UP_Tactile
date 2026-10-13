"""Render ROBOTIS's actual 3x3 heatmap code with synthetic left-hand data.

The official script uses TkAgg for its live window. This test substitutes
Agg only while importing it, so a headless CI/container can save one frame.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import rclpy  # noqa: E402
from robotis_interfaces.msg import HandPressures, TactileSensor  # noqa: E402


OFFICIAL = (
    Path(__file__).resolve().parents[3]
    / "third_party/robotis_hand/robotis_hand_playground/scripts/matplot_visualize_tactile.py"
)


def load_official_module():
    original_use = matplotlib.use
    matplotlib.use = lambda backend: None
    try:
        spec = importlib.util.spec_from_file_location("official_hx5_heatmap", OFFICIAL)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        matplotlib.use = original_use


def sample(touched: bool) -> HandPressures:
    msg = HandPressures()
    msg.hand_name = "left"
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
        msg.sensors.append(sensor)
    return msg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-png", required=True, type=Path)
    args = parser.parse_args()
    official = load_official_module()
    rclpy.init(args=["--ros-args", "-p", "hand_side:=left"])
    viz = official.PressureViz()
    try:
        if viz.cfg.hand_side != "left":
            raise AssertionError("official heatmap did not select the left hand")
        for _ in range(viz._baseline_frames + 5):
            viz._cb(sample(False))
        if not viz._baseline_ready:
            raise AssertionError("synthetic no-contact baseline was not collected")
        for _ in range(16):
            viz._cb(sample(True))
        if not (viz._pressure[0, 4] > 90.0 and viz._pressure[1, 0] > 70.0):
            raise AssertionError("thumb/index taxels did not update")
        if viz._pressure[2:].any():
            raise AssertionError("untouched fingers have nonzero pressure")
        viz._update_plot(None)
        # A single saved Agg frame bypasses FuncAnimation's normal GUI draw.
        viz.ani._draw_was_started = True
        args.output_png.parent.mkdir(parents=True, exist_ok=True)
        viz.fig.savefig(args.output_png, dpi=140)
        print(f"PASS: official left-hand heatmap rendered synthetic 3x3 pressure to {args.output_png}")
    finally:
        plt.close(viz.fig)
        viz.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
