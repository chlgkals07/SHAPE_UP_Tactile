"""Run real ROS controllers from a packed mock arm and verify unpack + hand.

Run in the sourced Jazzy workspace, with no other controller manager in the
same ROS domain. Only this fixture changes mock initial values; runtime Xacro
and its physical hardware settings are untouched.
"""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from ament_index_python.packages import get_package_share_directory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--use-launch", action="store_true")
    args = parser.parse_args()
    share = Path(get_package_share_directory("omy_hx5_bringup"))
    xml = subprocess.check_output([
        "xacro", str(share / "urdf/omy_f3m_hx5_left.urdf.xacro"),
        "mock_arm:=true", "mock_hand:=true",
    ], text=True)
    robot = ET.fromstring(xml)
    systems = robot.findall("ros2_control")
    assert len(systems) == 2 and all(
        system.find("hardware/plugin").text == "mock_components/GenericSystem"
        for system in systems
    ), "fixture must never start real hardware"
    arm = next(system for system in systems if system.attrib["name"] == "OMYF3MSystem")
    packed = (0.0, 0.0, -2.61799, -0.52360, 0.0, 0.0)
    for joint, value in zip(arm.findall("joint"), packed):
        state = joint.find("state_interface[@name='position']")
        ET.SubElement(state, "param", name="initial_value").text = str(value)

    processes = []
    with tempfile.TemporaryDirectory(prefix="hx5-unpack-check-") as temp:
        params = Path(temp) / "description.json"
        params.write_text(json.dumps({"/**": {"ros__parameters": {
            "robot_description": ET.tostring(robot, encoding="unicode"),
        }}}))
        with open(Path(temp) / "nodes.log", "w+") as log:
            def start(command):
                child = subprocess.Popen(command, stdout=log, stderr=log,
                                         start_new_session=True)
                processes.append(child)
                return child

            try:
                probe_command = [
                    sys.executable, str(Path(__file__).with_name("mock_hand_only_probe.py")),
                    "--require-blocked-start", "--switch-from-dry-run",
                    "--output-json", str(args.output_json.resolve()),
                ]
                if args.use_launch:
                    probe = start(probe_command)
                    start(["ros2", "launch", "omy_hx5_bringup", "omy_hx5_hand_only.launch.py",
                           "mock_arm:=true", "mock_hand:=true", "hand_dry_run:=true",
                           "arm_unpack_duration:=3.0"])
                else:
                    start(["ros2", "run", "robot_state_publisher", "robot_state_publisher",
                           "--ros-args", "--params-file", str(params)])
                    start(["ros2", "run", "controller_manager", "ros2_control_node", "--ros-args",
                           "--params-file", str(share / "config/hand_only_controller_manager.yaml"),
                           "--params-file", str(params)])
                    spawner = start([
                        "ros2", "run", "controller_manager", "spawner",
                        "joint_state_broadcaster", "arm_controller", "hand_l_controller",
                        "pressure_l_broadcaster",
                    ])
                    if spawner.wait(timeout=45) != 0:
                        raise RuntimeError("mock controller startup failed")
                    probe = start(probe_command + ["--require-arm-motion"])
                    start(["ros2", "run", "omy_hx5_bringup", "omy_hx5_hand_bridge", "--dry-run",
                           "--leader-topic", "/hx5/keyboard_grasp_trajectory",
                           "--leader-open", "0", "--leader-closed", "1",
                           "--arm-ready-topic", "/hx5/arm_unpack_ready"])
                    start(["ros2", "run", "omy_hx5_bringup", "omy_hx5_unpack_and_hold",
                           "--ros-args", "-p", "unpack_duration:=3.0"])
                if probe.wait(timeout=60) != 0:
                    raise RuntimeError("mock unpack/hand probe failed")
                print("PASS: unpack -> sustained hold -> dry-run/live transition -> keyboard hand motion")
            except Exception:
                log.flush()
                log.seek(0)
                print(log.read())
                raise
            finally:
                for child in reversed(processes):
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGINT)
                for child in processes:
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                log.seek(0)
                print(log.read()[-14000:])


if __name__ == "__main__":
    main()
