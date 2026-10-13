"""Exercise the actual keyboard CLI through a pseudo terminal and ROS 2."""

import os
import pty
import subprocess
import sys
import time
from pathlib import Path

import pytest


rclpy = pytest.importorskip("rclpy")
JointTrajectory = pytest.importorskip("trajectory_msgs.msg").JointTrajectory
SCRIPT = Path(__file__).resolve().parents[1] / "omy_hx5_keyboard.py"
TOPIC = "/hx5/keyboard_grasp_test"


def test_keyboard_x_z_publish_only_one_hand_grasp_value():
    rclpy.init()
    node = rclpy.create_node("omy_hx5_keyboard_pty_test")
    messages = []
    node.create_subscription(JointTrajectory, TOPIC, messages.append, 10)
    master, slave = pty.openpty()
    process = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--topic", TOPIC, "--rate-hz", "20"],
        stdin=slave, stdout=slave, stderr=slave,
    )
    os.close(slave)

    def await_value(expected: float) -> None:
        end = time.monotonic() + 5.0
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
            if any(msg.points and tuple(msg.points[0].positions) == (expected,) for msg in messages):
                return
        os.set_blocking(master, False)
        try:
            output = os.read(master, 4096)
        except BlockingIOError:
            output = b""
        raise AssertionError(
            f"keyboard never published {expected}; process={process.poll()}; "
            f"publishers={node.count_publishers(TOPIC)}; received={len(messages)}; output={output!r}"
        )

    try:
        await_value(0.0)
        messages.clear()
        os.write(master, b"x")
        await_value(1.0)
        messages.clear()
        os.write(master, b"z")
        await_value(0.0)
        assert all(msg.joint_names == ["rh_r1_joint"] for msg in messages)
        os.write(master, b"\x1b")
        assert process.wait(timeout=3.0) == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=3.0)
        os.close(master)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
