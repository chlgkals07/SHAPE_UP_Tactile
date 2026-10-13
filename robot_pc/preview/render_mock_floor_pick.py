"""Render the measured ROS mock floor-pick attempt in MuJoCo.

The object is fixed to the floor. Robot geometry comes from visual meshes, so
contacts here are qualitative and cannot establish physical grasp success.
"""

import argparse
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
from PIL import Image, ImageDraw


def make_scene(visual_urdf: Path, scene_path: Path) -> mujoco.MjModel:
    model = mujoco.MjModel.from_xml_path(str(visual_urdf))
    mujoco.mj_saveLastXML(str(scene_path), model)
    tree = ET.parse(scene_path)
    world = tree.getroot().find("worldbody")
    ET.SubElement(world, "geom", {
        "name": "floor", "type": "plane", "pos": "0 0 0", "size": "2 2 0.02",
        "rgba": "0.45 0.49 0.54 1", "contype": "1", "conaffinity": "1",
    })
    ET.SubElement(world, "light", {
        "name": "scene_light", "pos": "0 -0.3 1.4", "dir": "0 0 -1",
        "diffuse": "0.9 0.9 0.9", "specular": "0.15 0.15 0.15",
    })
    object_body = ET.SubElement(world, "body", {"name": "floor_object", "pos": "0 -0.35 0.04"})
    ET.SubElement(object_body, "geom", {
        "name": "floor_object_geom", "type": "box", "size": "0.04 0.04 0.04",
        "rgba": "1 0.35 0.08 1", "contype": "1", "conaffinity": "1",
    })
    tree.write(scene_path, encoding="unicode")
    return mujoco.MjModel.from_xml_path(str(scene_path))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--visual-urdf", required=True, type=Path)
    parser.add_argument("--states-json", required=True, type=Path)
    parser.add_argument("--output-gif", required=True, type=Path)
    parser.add_argument("--output-png", required=True, type=Path)
    parser.add_argument("--output-report", required=True, type=Path)
    args = parser.parse_args()
    recorded = json.loads(args.states_json.read_text())
    with tempfile.TemporaryDirectory() as tmp:
        model = make_scene(args.visual_urdf, Path(tmp) / "floor_pick_scene.xml")
        for geom in range(model.ngeom):
            body = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, model.geom_bodyid[geom]) or ""
            if body.startswith("finger_l_") or "hx5" in body:
                model.geom_rgba[geom] = [0.07, 0.7, 0.78, 1]
        data = mujoco.MjData(model)
        renderer = mujoco.Renderer(model, width=640, height=480)
        camera = mujoco.MjvCamera()
        camera.lookat[:] = [0, -0.24, 0.25]
        camera.distance = 1.0
        camera.azimuth = 110
        camera.elevation = -18
        object_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor_object_geom")
        phase_results = {}
        frames = []
        for index, sample in enumerate(recorded["samples"]):
            for name, value in sample["positions"].items():
                joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
                data.qpos[model.jnt_qposadr[joint]] = value
            mujoco.mj_forward(model, data)
            object_contacts = [data.contact[i] for i in range(data.ncon)
                               if object_geom in (data.contact[i].geom1, data.contact[i].geom2)]
            touch = len(object_contacts)
            phase = sample["phase"]
            result = phase_results.setdefault(phase, {
                "samples": 0, "max_object_contacts": 0, "last_object_contacts": 0,
                "max_visual_penetration_m": 0.0,
            })
            result["samples"] += 1
            result["max_object_contacts"] = max(result["max_object_contacts"], touch)
            result["last_object_contacts"] = touch
            result["max_visual_penetration_m"] = max(
                result["max_visual_penetration_m"],
                max((-contact.dist for contact in object_contacts), default=0.0),
            )
            if index % 4 and index != len(recorded["samples"]) - 1:
                continue
            renderer.update_scene(data, camera=camera)
            frame = Image.fromarray(renderer.render())
            draw = ImageDraw.Draw(frame)
            draw.rectangle((0, 0, 640, 36), fill=(12, 18, 25))
            draw.text((15, 11), f"ROS mock: {phase} | trigger {sample['trigger']:.2f} | object contacts {touch}",
                      fill=(235, 240, 245))
            frames.append(frame)
        renderer.close()
    if not frames:
        raise RuntimeError("no measured ROS states were recorded")
    args.output_gif.parent.mkdir(parents=True, exist_ok=True)
    frames[-1].save(args.output_png)
    frames[0].save(args.output_gif, save_all=True, append_images=frames[1:],
                   duration=125, loop=0, optimize=True)
    report = {
        "object": {"center_m": [0, -0.35, 0.04], "half_size_m": [0.04, 0.04, 0.04]},
        "phase_contacts": phase_results,
        "limitations": "Visual-mesh contacts and fixed floor object; no dynamics, force, or grasp proof.",
    }
    args.output_report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
