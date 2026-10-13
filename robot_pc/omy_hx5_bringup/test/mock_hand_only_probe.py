"""Verify the hand-only launch using the real remote keyboard program.

Requires mock_arm:=true mock_hand:=true and hand_dry_run:=false. A pseudo-terminal feeds
z/x/increment keys to the client; the official mock hand controller reports
the measured states while the arm's controller holds the unpack pose.
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
from rclpy.parameter import Parameter
from rclpy.parameter_client import AsyncParameterClient
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from std_msgs.msg import Bool


TOPIC = "/hx5/keyboard_grasp_trajectory"
HAND = tuple(f"finger_l_joint{i}" for i in range(1, 21))
ARM = tuple(f"joint{i}" for i in range(1, 7))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--require-blocked-start", action="store_true")
    parser.add_argument("--require-arm-motion", action="store_true")
    parser.add_argument("--switch-from-dry-run", action="store_true")
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node("omy_hx5_mock_hand_only_probe")
    hand_commands = []
    states = []
    ready = []
    node.create_subscription(JointTrajectory, "/hand_l_controller/joint_trajectory", hand_commands.append, 10)
    node.create_subscription(JointState, "/joint_states", states.append, 10)
    node.create_subscription(Bool, "/hx5/arm_unpack_ready", ready.append, 10)
    # A leader stream must have no effect on this hand-only launch's arm.
    leader = node.create_publisher(JointTrajectory, "/leader/joint_trajectory", 10)
    ignored = JointTrajectory(joint_names=list(ARM) + ["rh_r1_joint"])
    ignored.points = [JointTrajectoryPoint(positions=[0.6] * 7)]
    node.create_timer(0.05, lambda: leader.publish(ignored))
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    parameters = AsyncParameterClient(node, "/hx5_left_omy_teleop")
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
        if not states:
            raise AssertionError("no hand joint states")
        return dict(zip(states[-1].name, states[-1].position))

    try:
        deadline = time.monotonic() + 45.0
        saw_blocked = False
        unpack_samples = []
        rejected_enable = None
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.05)
            if ready and not ready[-1].data:
                saw_blocked = True
                if states:
                    measured = dict(zip(states[-1].name, states[-1].position))
                    if all(joint in measured for joint in ARM):
                        unpack_samples.append([measured[joint] for joint in ARM])
                if hand_commands:
                    raise AssertionError("hand command published before unpack ready")
                if (args.switch_from_dry_run and rejected_enable is None
                        and parameters.services_are_ready()):
                    rejected_enable = parameters.set_parameters([
                        Parameter("command_enabled", value=True)])
            if ready and ready[-1].data:
                break
        else:
            raise AssertionError("arm never became ready")
        if args.require_blocked_start and not saw_blocked:
            raise AssertionError("unpack blocking phase was not observed")
        if args.require_arm_motion and not any(abs(sample[2]) > 1.0 for sample in unpack_samples):
            raise AssertionError("nonzero arm posture was not observed during unpack")
        def set_enabled(value):
            deadline = time.monotonic() + 5.0
            reason = "service timed out"
            while time.monotonic() < deadline:
                future = parameters.set_parameters([Parameter("command_enabled", value=value)])
                while not future.done() and time.monotonic() < deadline:
                    executor.spin_once(timeout_sec=0.05)
                if not future.done():
                    break
                response = future.result().results[0]
                if response.successful:
                    return
                reason = response.reason
                # The first ready heartbeat can reach this probe before it
                # reaches the hand bridge. Keep the keyboard released and retry.
                send(None, 0.15)
            raise AssertionError(f"could not set command_enabled={value}: {reason}")

        if args.switch_from_dry_run:
            if rejected_enable is None or not rejected_enable.done():
                raise AssertionError("early enable rejection was not observed")
            if rejected_enable.result().results[0].successful:
                raise AssertionError("hand command enable accepted before unpack complete")
            if hand_commands:
                raise AssertionError("dry-run hand command leaked")
            set_enabled(True)
        if node.get_node_names().count("controller_manager") != 1:
            raise AssertionError("expected exactly one controller manager")
        if node.count_publishers("/arm_controller/joint_trajectory"):
            raise AssertionError("unexpected arm teleoperation publisher")
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
            if not all(joint in measured and abs(measured[joint]) < 0.02 for joint in ARM):
                raise AssertionError(f"arm did not hold unpack pose: {measured}")
            if not ready[-1].data:
                raise AssertionError("arm ready signal lost during keyboard test")
            if not all(name in measured for name in HAND):
                raise AssertionError("missing left-hand joint states")
            records.append({"phase": name, "grasp": value, "positions": {
                joint: measured[joint] for joint in HAND
            }, "arm_positions": {joint: measured[joint] for joint in ARM}})
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
            args.output_json.write_text(json.dumps({
                "unpack_arm_samples": unpack_samples, "keyboard_phases": records,
                "dry_run_to_live_without_arm_restart": args.switch_from_dry_run,
            }, indent=2) + "\n")
        if args.switch_from_dry_run:
            set_enabled(False)
            send(None, 0.2)
            command_count = len(hand_commands)
            measured = send("x", 0.4)
            if len(hand_commands) != command_count or abs(measured["finger_l_joint6"]) > 0.02:
                raise AssertionError("disabled hand still received closure commands")
        print("PASS: unpack gates hand commands; keyboard moves 20 mock hand joints; "
              "arm holds zero despite unrelated leader stream", flush=True)
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
