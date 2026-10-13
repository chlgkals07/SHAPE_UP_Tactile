"""Execute a floor-object pickup *attempt* through the OMY/HX5 ROS teleop path.

Run only with mock_arm:=true and mock_hand:=true. The poses were solved against
the combined visual URDF for an object near (0, -0.35, 0.04) m in the base
frame. This checks command routing and joint tracking, not force closure.
"""

import argparse
import json
import time
from pathlib import Path

import rclpy
from rclpy.executors import SingleThreadedExecutor
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint


ARM = tuple(f"joint{i}" for i in range(1, 7))
HAND = tuple(f"finger_l_joint{i}" for i in range(1, 21))
LEADER = (*ARM, "rh_r1_joint")
PHASES = (
    ("home", (0.0,) * 6, 0.0, 3.0),
    ("pregrasp", (0.7481, 0.3940, -1.0318, -0.5989, -1.0411, 1.1103), 0.0, 2.5),
    ("above", (0.6748, 0.0581, -1.2780, -0.6676, -0.9804, 1.1125), 0.0, 1.5),
    ("floor", (0.6609, -0.1811, -1.4141, -0.5551, -0.9693, 1.1260), 0.0, 1.5),
    ("close", (0.6609, -0.1811, -1.4141, -0.5551, -0.9693, 1.1260), 1.0, 3.5),
    ("lift", (0.7134, 0.2407, -1.1494, -0.6697, -1.0119, 1.1083), 1.0, 2.5),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", required=True, type=Path)
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node("omy_hx5_mock_floor_pick_probe")
    publisher = node.create_publisher(JointTrajectory, "/leader/joint_trajectory", 10)
    arm_commands = []
    hand_commands = []
    joint_states = []
    node.create_subscription(JointTrajectory, "/arm_controller/joint_trajectory", arm_commands.append, 10)
    node.create_subscription(JointTrajectory, "/hand_l_controller/joint_trajectory", hand_commands.append, 10)
    node.create_subscription(JointState, "/joint_states", joint_states.append, 10)
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    samples = []
    phase_records = []
    last_arm = (0.0,) * 6
    last_trigger = 0.0

    try:
        for phase, target_arm, target_trigger, seconds in PHASES:
            start = time.monotonic()
            last_record = 0.0
            while True:
                elapsed = time.monotonic() - start
                alpha = min(1.0, elapsed / max(seconds - 0.5, 0.1))
                arm = tuple(a + alpha * (b - a) for a, b in zip(last_arm, target_arm))
                trigger = last_trigger + alpha * (target_trigger - last_trigger)
                msg = JointTrajectory()
                msg.joint_names = list(LEADER)
                point = JointTrajectoryPoint()
                point.positions = [*arm, trigger]
                msg.points = [point]
                publisher.publish(msg)
                executor.spin_once(timeout_sec=0.005)
                if joint_states and elapsed - last_record >= 0.1:
                    state = joint_states[-1]
                    positions = dict(zip(state.name, state.position))
                    if all(name in positions for name in (*ARM, *HAND)):
                        samples.append({
                            "phase": phase,
                            "elapsed": round(elapsed, 3),
                            "trigger": round(trigger, 4),
                            "positions": {name: positions[name] for name in (*ARM, *HAND)},
                        })
                        last_record = elapsed
                if elapsed >= seconds:
                    break
                time.sleep(0.02)
            if not joint_states:
                raise AssertionError("joint_state_broadcaster produced no state")
            state = dict(zip(joint_states[-1].name, joint_states[-1].position))
            if not arm_commands or tuple(arm_commands[-1].joint_names) != ARM:
                raise AssertionError("arm bridge output missing or malformed")
            if not hand_commands or tuple(hand_commands[-1].joint_names) != HAND:
                actual = tuple(hand_commands[-1].joint_names) if hand_commands else ()
                raise AssertionError(f"left hand bridge output missing or malformed: {actual}")
            arm_error = max(abs(state[name] - goal) for name, goal in zip(ARM, target_arm))
            if arm_error > 0.025:
                raise AssertionError(f"{phase}: arm tracking error {arm_error:.4f} rad")
            phase_records.append({
                "phase": phase,
                "trigger": target_trigger,
                "arm_error_max_rad": arm_error,
                "index_joint6_rad": state["finger_l_joint6"],
                "thumb_joint1_rad": state["finger_l_joint1"],
                "thumb_joint2_rad": state["finger_l_joint2"],
                "thumb_joint3_rad": state["finger_l_joint3"],
            })
            print(f"{phase}: arm error {arm_error:.4f} rad, "
                  f"index joint6 {state['finger_l_joint6']:.3f} rad", flush=True)
            last_arm, last_trigger = target_arm, target_trigger
        if phase_records[-1]["index_joint6_rad"] < 1.26:
            raise AssertionError("left fingers did not close in the mock controller")
        if not (-0.90 < phase_records[-1]["thumb_joint1_rad"] < -0.82
                and 0.82 < phase_records[-1]["thumb_joint2_rad"] < 0.90):
            raise AssertionError("left thumb did not move into the opposing posture")
        args.output_json.write_text(json.dumps({"phases": phase_records, "samples": samples}, indent=2) + "\n")
        print(f"PASS: {len(samples)} measured states written to {args.output_json}", flush=True)
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
