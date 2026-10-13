"""Exercise left-hand trigger commands on ROBOTIS's official MuJoCo model.

The upstream scene has no tactile sensors. Synthetic pressure frames only let
this test pass the controller's tactile-input gate; they do not test contact
force estimation or physical grasping.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from hx5_teleop.core import Hx5CoreConfig, Hx5GraspCore, TactileFrame, joint_names

mujoco = pytest.importorskip("mujoco")

SCENE = (
    Path(__file__).resolve().parents[3]
    / "third_party/robotis_hand/robotis_hand_description/mujoco/hx5_d20_rev2/scene_left.xml"
)


def _load_left_scene():
    if not SCENE.is_file():
        pytest.skip("official ROBOTIS hand submodule has not been downloaded")
    return mujoco.MjModel.from_xml_path(str(SCENE))


def test_official_left_model_matches_trajectory_joint_order():
    model = _load_left_scene()
    expected = joint_names("left")

    assert (model.nq, model.nv, model.nu) == (20, 20, 20)
    assert tuple(
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
        for index in range(model.njnt)
    ) == expected
    assert tuple(
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, index)
        for index in range(model.nu)
    ) == expected
    assert model.nsensor == 0  # Tactile feedback needs separate synthetic tests or hardware.


def test_trigger_cycle_tracks_in_official_left_scene_without_self_contact():
    model = _load_left_scene()
    data = mujoco.MjData(model)
    config = Hx5CoreConfig(hand_side="left")
    core = Hx5GraspCore(config)

    data.qpos[:] = config.open_positions
    data.ctrl[:] = config.open_positions
    mujoco.mj_forward(model, data)
    assert data.ncon == 0
    core.initialize(tuple(data.qpos), now=0.0)

    zero_pressure = ((0.0,) * 9,) * 5
    elapsed_steps = 0
    max_tracking_error = 0.0
    for grasp, duration_s in ((0.0, 0.8), (0.5, 1.8), (1.0, 2.0), (0.0, 3.4)):
        for _ in range(round(duration_s / 0.02)):
            elapsed_steps += 1
            now = elapsed_steps * 0.02
            previous = np.asarray(core.command)
            frame = TactileFrame(timestamp=now, values=zero_pressure)
            command = np.asarray(core.step(grasp, frame, now))

            # One controller tick is ten 2 ms MuJoCo steps.
            data.ctrl[:] = command
            for _ in range(10):
                mujoco.mj_step(model, data)
                assert data.ncon == 0

            assert np.isfinite(data.qpos).all()
            assert np.isfinite(data.qvel).all()
            assert np.isfinite(command).all()
            assert np.all(command >= model.jnt_range[:, 0] - 1e-9)
            assert np.all(command <= model.jnt_range[:, 1] + 1e-9)
            assert np.max(np.abs(command - previous)) <= config.max_joint_speed_rad_s * 0.02 + 1e-9
            max_tracking_error = max(max_tracking_error, float(np.max(np.abs(data.qpos - command))))

        expected = np.asarray(config.open_positions) + grasp * np.asarray(config.closing_spans)
        np.testing.assert_allclose(command, expected, atol=1e-9)
        np.testing.assert_allclose(data.qpos, command, atol=0.03)

    assert core.baseline_ready
    assert max_tracking_error < 0.1
