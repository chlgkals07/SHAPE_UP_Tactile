"""Run against omy_hx5_teleop.launch.py with both buses mocked.

Uses the actual ROBOTIS pressure broadcaster and both ROS controllers. No
serial device is opened. Leader endpoints 0/1 are synthetic test values only.
"""

import argparse
import json
import time
from pathlib import Path

import rclpy
from rclpy.executors import SingleThreadedExecutor
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node("omy_hx5_mock_probe")
    leader = node.create_publisher(JointTrajectory, "/leader/joint_trajectory", 10)
    arm_commands = []
    hand_commands = []
    hand_states = []
    node.create_subscription(
        JointTrajectory, "/arm_controller/joint_trajectory", arm_commands.append, 10
    )
    node.create_subscription(
        JointTrajectory, "/hand_l_controller/joint_trajectory", hand_commands.append, 10
    )
    node.create_subscription(JointState, "/joint_states", hand_states.append, 10)
    executor = SingleThreadedExecutor()
    executor.add_node(node)

    def send(value: float, arm: tuple[float, ...], seconds: float) -> None:
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            msg = JointTrajectory()
            msg.joint_names = [*(f"joint{i}" for i in range(1, 7)), "rh_r1_joint"]
            point = JointTrajectoryPoint()
            point.positions = [*arm, value]
            msg.points = [point]
            leader.publish(msg)
            executor.spin_once(timeout_sec=0.005)
            time.sleep(0.02)

    def measured() -> dict[str, float]:
        if not hand_states:
            raise AssertionError("joint state broadcaster produced no messages")
        state = hand_states[-1]
        return dict(zip(state.name, state.position))

    def check_arm(target: tuple[float, ...], state: dict[str, float]) -> None:
        if not arm_commands or arm_commands[-1].joint_names != [f"joint{i}" for i in range(1, 7)]:
            raise AssertionError("arm command is missing or includes a non-arm joint")
        for index, expected in enumerate(target, 1):
            name = f"joint{index}"
            if abs(state[name] - expected) > 0.02:
                raise AssertionError(f"{name} did not track: {state[name]} vs {expected}")

    phases = []
    zero_arm = (0.0,) * 6
    moved_arm = (0.08, -0.10, 0.12, -0.07, 0.05, -0.04)
    second_arm = (-0.06, 0.07, -0.09, 0.06, -0.04, 0.03)

    def record(name: str, target_arm: tuple[float, ...], trigger: float) -> dict[str, float]:
        state = measured()
        check_arm(target_arm, state)
        phases.append({
            "phase": name,
            "trigger": trigger,
            "arm_target": list(target_arm),
            "positions": {joint: state[joint] for joint in
                          [*(f"joint{i}" for i in range(1, 7)),
                           *(f"finger_l_joint{i}" for i in range(1, 21))]},
        })
        return state

    try:
        send(0.0, zero_arm, 2.5)
        if not arm_commands or not hand_commands:
            raise AssertionError(
                f"missing output: arm={len(arm_commands)} hand={len(hand_commands)}"
            )
        if hand_commands[-1].joint_names != [f"finger_l_joint{i}" for i in range(1, 21)]:
            raise AssertionError("hand command is not the ordered left 20-joint trajectory")
        opened = record("open", zero_arm, 0.0)
        send(0.5, moved_arm, 1.8)
        half = record("half", moved_arm, 0.5)
        send(1.0, second_arm, 1.8)
        closed = record("closed", second_arm, 1.0)
        send(0.0, zero_arm, 3.4)
        released = record("released", zero_arm, 0.0)
        for joint in ("finger_l_joint6", "finger_l_joint10", "finger_l_joint14", "finger_l_joint18"):
            values = (opened[joint], half[joint], closed[joint], released[joint])
            if not (abs(values[0]) < 0.02 and 0.61 < values[1] < 0.69
                    and 1.26 < values[2] < 1.34 and abs(values[3]) < 0.02):
                raise AssertionError(f"{joint} did not open/close/release: {values}")
        for joint, half_target, full_target in (
            ("finger_l_joint1", -0.432, -0.864),
            ("finger_l_joint2", 0.432, 0.864),
            ("finger_l_joint3", -0.6, -1.2),
            ("finger_l_joint4", -0.6, -1.2),
        ):
            values = (opened[joint], half[joint], closed[joint], released[joint])
            if not (abs(values[0]) < 0.02
                    and abs(values[1] - half_target) < 0.04
                    and abs(values[2] - full_target) < 0.04
                    and abs(values[3]) < 0.02):
                raise AssertionError(f"{joint} did not open/close/release: {values}")
        if args.output_json:
            args.output_json.write_text(json.dumps(phases, indent=2) + "\n")
        print(
            "PASS: leader 7 -> arm 6 and HX5 20; "
            "arm tracked two targets; "
            "index state "
            f"{opened['finger_l_joint6']:.3f}->"
            f"{half['finger_l_joint6']:.3f}->"
            f"{closed['finger_l_joint6']:.3f}->"
            f"{released['finger_l_joint6']:.3f}",
            flush=True,
        )
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
