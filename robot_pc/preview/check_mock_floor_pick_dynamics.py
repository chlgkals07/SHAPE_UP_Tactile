"""Approximate free-object check for a recorded ROS mock pickup attempt.

The arm/hand poses are imposed at each sample; only the box is free. The
collision shapes are visual meshes, so this is diagnostic rather than a
validated physics model or a prediction of hardware grasp performance.
"""

import argparse
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco

from render_mock_floor_pick import make_scene


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--visual-urdf", required=True, type=Path)
    parser.add_argument("--states-json", required=True, type=Path)
    parser.add_argument("--output-report", required=True, type=Path)
    args = parser.parse_args()
    samples = json.loads(args.states_json.read_text())["samples"]
    with tempfile.TemporaryDirectory() as tmp:
        scene = Path(tmp) / "dynamic_floor_pick.xml"
        make_scene(args.visual_urdf, scene)
        tree = ET.parse(scene)
        root = tree.getroot()
        box_body = root.find(".//body[@name='floor_object']")
        ET.SubElement(box_body, "freejoint", {"name": "object_free"})
        box_body.find("geom").set("mass", "0.2")
        box_body.find("geom").set("friction", "1 0.05 0.01")
        ET.SubElement(root, "option", {"timestep": "0.005"})
        tree.write(scene, encoding="unicode")
        model = mujoco.MjModel.from_xml_path(str(scene))
        data = mujoco.MjData(model)
        object_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "floor_object")
        free_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "object_free")
        free_qpos = model.jnt_qposadr[free_joint]
        free_dof = model.jnt_dofadr[free_joint]
        object_start = data.qpos[free_qpos:free_qpos + 3].copy()
        heights = {}
        for sample in samples:
            for name, value in sample["positions"].items():
                joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
                data.qpos[model.jnt_qposadr[joint]] = value
            # A recorded sample represents about 0.1 s; impose the robot pose
            # while advancing the free box and contact solver through that span.
            for _ in range(20):
                data.qvel[:free_dof] = 0
                mujoco.mj_step(model, data)
            phase = sample["phase"]
            height = float(data.xpos[object_id, 2])
            value = heights.setdefault(phase, {"max_center_z_m": height, "last_center_z_m": height})
            value["max_center_z_m"] = max(value["max_center_z_m"], height)
            value["last_center_z_m"] = height
        end = data.xpos[object_id].tolist()
    report = {
        "object_initial_center_m": object_start.tolist(),
        "object_final_center_m": end,
        "phase_heights": heights,
        "lifted_over_2cm": bool(end[2] > object_start[2] + 0.02),
        "limitations": "Pose-driven robot, free 0.2 kg box, visual mesh collisions; not validated grasp physics.",
    }
    args.output_report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
