"""Verify the hand-only launch using the real remote keyboard program.

Requires mock_hand:=true and hand_dry_run:=false. A pseudo-terminal feeds
z/x/increment keys to the client; the official mock hand controller reports
the measured states. No serial port or arm hardware is opened.
"""

import argparse
import json
import os
import pty
import subprocess
import sys
import time
from pathlib import Path

import rclpy
from rclpy.executors import SingleThreadedExecutor
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory


TOPIC = "/hx5/keyboard_grasp_trajectory"
HAND = tuple(f"finger_l_joint{i}" for i in range(1, 21))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node("omy_hx5_mock_hand_only_probe")
    hand_commands = []
    states = []
    node.create_subscription(JointTrajectory, "/hand_l_controller/joint_trajectory", hand_commands.append, 10)
    node.create_subscription(JointState, "/joint_states", states.append, 10)
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    master, slave = pty.openpty()
    keyboard_script = Path(__file__).resolve().parents[3] / "user_pc/omy_hx5_keyboard.py"
    keyboard = subprocess.Popen(
        [sys.executable, str(keyboard_script), "--topic", TOPIC, "--step", "0.5"],
        stdin=slave, stdout=slave, stderr=slave,
    )
    os.close(slave)

    def send(key: str | None, seconds: float) -> dict[str, float]:
        if key is not None:
            os.write(master, key.encode())
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            executor.spin_once(timeout_sec=0.005)
            time.sleep(0.02)
        if not states:
            raise AssertionError("no hand joint states")
        return dict(zip(states[-1].name, states[-1].position))

    try:
        records = []
        for name, key, value, seconds in (
            ("open", None, 0.0, 2.5),
            ("half", "]", 0.5, 1.8),
            ("close", "x", 1.0, 1.8),
            ("release", "z", 0.0, 3.4),
        ):
            measured = send(key, seconds)
            if keyboard.poll() is not None:
                raise AssertionError(f"keyboard exited early: {keyboard.returncode}")
            if any(name.startswith("joint") for name in measured):
                raise AssertionError("arm joints appeared in hand-only joint states")
            if not all(name in measured for name in HAND):
                raise AssertionError("missing left-hand joint states")
            records.append({"phase": name, "grasp": value, "positions": {
                joint: measured[joint] for joint in HAND
            }})
        if not hand_commands or tuple(hand_commands[-1].joint_names) != HAND:
            raise AssertionError("20-joint hand command missing")

        for joint, half, closed in (
            ("finger_l_joint1", -0.432, -0.864),
            ("finger_l_joint2", 0.432, 0.864),
            ("finger_l_joint3", -0.6, -1.2),
            ("finger_l_joint6", 0.65, 1.3),
        ):
            actual = [record["positions"][joint] for record in records]
            if not (abs(actual[0]) < 0.02 and abs(actual[1] - half) < 0.04
                    and abs(actual[2] - closed) < 0.04 and abs(actual[3]) < 0.02):
                raise AssertionError(f"{joint} did not track: {actual}")
        if args.output_json:
            args.output_json.write_text(json.dumps(records, indent=2) + "\n")
        print("PASS: actual keyboard -> Robot PC bridge -> 20 mock hand joints; no arm hardware", flush=True)
    finally:
        if keyboard.poll() is None:
            os.write(master, b"\x1b")
            try:
                keyboard.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                keyboard.terminate()
                keyboard.wait(timeout=2.0)
        os.close(master)
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
