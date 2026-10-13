"""Loop the measured mock pickup motion in the interactive MuJoCo viewer."""

import argparse
import json
import tempfile
import time
from pathlib import Path

import mujoco
import mujoco.viewer

from render_mock_floor_pick import make_scene


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--visual-urdf", required=True, type=Path)
    parser.add_argument("--states-json", required=True, type=Path)
    args = parser.parse_args()
    samples = json.loads(args.states_json.read_text())["samples"]
    with tempfile.TemporaryDirectory() as tmp:
        model = make_scene(args.visual_urdf, Path(tmp) / "floor_pick_viewer.xml")
    data = mujoco.MjData(model)
    for geom in range(model.ngeom):
        body = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, model.geom_bodyid[geom]) or ""
        if body.startswith("finger_l_") or "hx5" in body:
            model.geom_rgba[geom] = [0.07, 0.7, 0.78, 1]
    with mujoco.viewer.launch_passive(model, data) as viewer:
        viewer.cam.lookat[:] = [0, -0.24, 0.25]
        viewer.cam.distance = 1.0
        viewer.cam.azimuth = 110
        viewer.cam.elevation = -18
        while viewer.is_running():
            for sample in samples:
                if not viewer.is_running():
                    break
                for name, value in sample["positions"].items():
                    joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
                    data.qpos[model.jnt_qposadr[joint]] = value
                mujoco.mj_forward(model, data)
                viewer.sync()
                time.sleep(0.08)


if __name__ == "__main__":
    main()
