"""Record with fake devices -> save -> convert, and check the result against known truth.

The fake devices put the same "tap" pulse into tactile force, hand current and camera
brightness at the same instant. After conversion the pulse must sit on the same dataset steps
in all three. That is the property the whole recorder exists for.
"""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pytest

from tactile_rec import features
from tactile_rec.convert.dataset import LeRobotV21Writer, NpzWriter, convert_many, iter_frames
from tactile_rec.convert.episode import ConvertError, convert_episode
from tactile_rec.convert.load import Episode, find_episodes
from tactile_rec.record.session import Recorder
from tactile_rec.streams.fake import TAP_WIDTH_S, tap_level

from conftest import ManualRig

TAP_PERIOD_S = 4.0


def record(rig, seconds=6.0, success=True, skip=()):
    recorder = Recorder(rig.hub)
    rig.run(1.5)
    recorder.start()
    rig.run(seconds, skip=skip, on_step=recorder.tick)
    recorder.stop()
    return recorder.save(success)


def tap_steps(signal: np.ndarray) -> np.ndarray:
    return np.flatnonzero(signal > (signal.min() + signal.max()) / 2)


def brightness(converted, episode, camera):
    rows = iter_frames(converted, episode, "t")
    return np.array([row[features.KEY_IMAGE + camera][-1, -1].mean() for row in rows])


def test_tap_lands_on_the_same_steps_in_tactile_current_and_video(rig):
    path = record(rig, seconds=6.0)
    episode = Episode(path)
    converted = convert_episode(episode, rig.config.dataset)
    assert converted.report["ok"], converted.report["problems"]
    assert converted.steps == pytest.approx(6.0 * 30, abs=2)

    grid_s = converted.grid_ns / 1e9
    truth = np.array([tap_level(t, TAP_PERIOD_S) for t in grid_s])
    fz = converted.arrays[features.KEY_TACTILE][:, 2]  # thumb_tip fz
    current = converted.arrays[features.KEY_CURRENT][:, 0]
    image = brightness(converted, episode, "cam_ext")
    true_steps = set(np.flatnonzero(truth).tolist())
    assert len(true_steps) >= 4  # two taps in 6 s, each 80 ms tap covers two or three steps
    for name, signal in (("tactile", fz), ("current", current), ("video", image)):
        seen = set(tap_steps(signal).tolist())
        # A step shows the latest sample at or before it. That sample is at most one period of
        # its own stream old (11 ms tactile, 20 ms hand, 33 ms camera), which is at most one
        # dataset step. So the tap may appear up to one step late, never early, never elsewhere.
        assert seen, name
        assert all(s in true_steps or s - 1 in true_steps for s in seen), (name, seen)
        assert all(t in seen or t + 1 in seen for t in true_steps), (name, seen, true_steps)


def test_state_action_units_order_and_names(rig):
    path = record(rig, seconds=1.0)
    episode = Episode(path)
    converted = convert_episode(episode, rig.config.dataset)
    state, action = converted.arrays[features.KEY_STATE], converted.arrays[features.KEY_ACTION]
    assert state.shape == action.shape == (converted.steps, 22) and state.dtype == np.float32
    names = converted.names[features.KEY_STATE]
    assert names[:6] == [f"joint{i}" for i in range(1, 7)]
    assert names[6] == "leap_index_mcp_side" and names[-1] == "leap_thumb_ip_flex"
    # Step 10: hand is recorded in degrees, the dataset is in radians.
    t = converted.grid_ns[10] / 1e9
    hand = np.load(path / "hand.npz")
    k = np.searchsorted(hand["t_src_ns"], converted.grid_ns[10], side="right") - 1
    np.testing.assert_allclose(state[10, 6:], np.deg2rad(hand["pos"][k]), rtol=1e-5)
    np.testing.assert_allclose(action[10, 6:], np.deg2rad(hand["cmd"][k]), rtol=1e-5)
    # Arm: the fake leader runs 50 ms ahead of the follower.
    arm = rig.makers["arm_state"].make(t)["pos"]
    assert np.abs(state[10, :6] - arm).max() < 0.01


def test_tactile_features_have_the_configured_order_and_the_high_rate_window(rig):
    path = record(rig, seconds=1.0)
    converted = convert_episode(Episode(path), rig.config.dataset)
    resultant = converted.arrays[features.KEY_TACTILE]
    distributed = converted.arrays[features.KEY_TACTILE_DIST]
    hr = converted.arrays[features.KEY_TACTILE_HR]
    assert resultant.shape[1] == 8 * 3
    assert distributed.shape[1] == (4 * 52 + 4 * 25) * 3
    assert hr.shape[1] == 3 * 8 * 3
    names = converted.names[features.KEY_TACTILE]
    assert names[:3] == ["thumb_tip.fx", "thumb_tip.fy", "thumb_tip.fz"]
    assert names[-1] == "ring_pad.fz"
    # The last high-rate sample of each step is the step's own value.
    np.testing.assert_array_equal(hr[:, -24:], resultant)
    # Earlier samples in the window come from earlier times, so they differ somewhere.
    assert not np.array_equal(hr[:, :24], resultant)
    assert converted.report["tactile_hr_clamped"] == 0


def test_images_are_rotated_upright_and_frames_reused_only_when_needed(rig):
    path = record(rig, seconds=1.0)
    episode = Episode(path)
    converted = convert_episode(episode, rig.config.dataset)
    assert converted.image_shapes == {"cam_wrist": (64, 48, 3), "cam_ext": (48, 64, 3)}
    row = next(iter_frames(converted, episode, "do it"))
    assert row[features.KEY_IMAGE + "cam_wrist"].shape == (64, 48, 3)
    assert row[features.KEY_IMAGE + "cam_ext"].shape == (48, 64, 3) and row["task"] == "do it"
    assert converted.report["streams"]["cam_ext"]["frames_reused"] <= 1


def test_a_stalled_stream_is_reported_and_the_episode_is_excluded(rig):
    path = record(rig, seconds=3.0, skip=("tactile_b",))  # board B silent while recording
    converted = convert_episode(Episode(path), rig.config.dataset)
    report = converted.report
    assert not report["ok"]
    assert report["streams"]["tactile_b"]["stale_max_ms"] > 2900
    assert any("tactile_b" in p and "old" in p for p in report["problems"])
    assert any("dropped out" in p for p in report["problems"])


def test_camera_latency_setting_shifts_the_video_earlier(rig):
    path = record(rig, seconds=6.0)
    episode = Episode(path)
    base = convert_episode(episode, rig.config.dataset)
    shifted_cfg = dataclasses.replace(rig.config.dataset, latency_ms={"cam_ext": 83.0})
    shifted = convert_episode(episode, shifted_cfg)
    first = tap_steps(brightness(base, episode, "cam_ext"))[0]
    first_shifted = tap_steps(brightness(shifted, episode, "cam_ext"))[0]
    # 83 ms is 2.5 frame periods at 30 fps, so the tap moves two or three steps earlier.
    assert first - first_shifted in (2, 3)


def test_convert_many_filters_failures_and_writes_npz(rig, tmp_path):
    record(rig, seconds=1.0, success=True)
    recorder = Recorder(rig.hub)
    recorder._session_dir = next((rig.config.data_root / "pick_cup").iterdir())
    recorder.start()
    rig.run(1.0)
    recorder.stop()
    recorder.save(False)
    task_dir = rig.config.data_root / "pick_cup"
    assert len(find_episodes(task_dir)) == 2

    lines = []
    out = tmp_path / "out"
    report = convert_many([task_dir], rig.config.dataset, NpzWriter(out), log=lines.append)
    assert (report["found"], report["written"], report["skipped"]) == (2, 1, 1)
    assert report["mount"] == "wrist_flip"
    assert any("labelled failure" in line for line in lines)
    data = np.load(out / "episode_000000.npz")
    assert data[features.KEY_STATE].shape[1] == 22 and "frame_index.cam_wrist" in data.files
    info = json.loads((out / "episode_000000.json").read_text())
    assert info["task"] == "Pick up the cup"

    both = convert_many(
        [task_dir], rig.config.dataset, NpzWriter(tmp_path / "all"), include_failed=True,
        log=lines.append,
    )
    assert both["written"] == 2


def test_episodes_from_different_mounts_are_refused(tmp_path):
    first = ManualRig(tmp_path)
    record(first, seconds=0.5)
    other = ManualRig(tmp_path, rig={"name": "test_rig", "mount": "stock"})
    record(other, seconds=0.5)
    with pytest.raises(ConvertError, match="different mounts"):
        convert_many(
            [first.config.data_root], first.config.dataset, NpzWriter(tmp_path / "o"),
            log=lambda _line: None,
        )


class StubDataset:
    """Stands in for lerobot's LeRobotDataset: records how it was called."""

    created: dict = {}

    def __init__(self):
        self.rows, self.saved = [], 0

    @classmethod
    def create(cls, **kwargs):
        cls.created = kwargs
        cls.instance = cls()
        return cls.instance

    def add_frame(self, frame):
        self.rows.append(frame)

    def save_episode(self):
        self.saved += 1


def test_lerobot_writer_calls_create_add_frame_save_episode(rig, tmp_path):
    record(rig, seconds=1.0)
    writer = LeRobotV21Writer(
        "shape_up/pick_cup", tmp_path / "lerobot", 30, "omy_f3m_leap", dataset_cls=StubDataset
    )
    report = convert_many(
        [rig.config.data_root], rig.config.dataset, writer, log=lambda _line: None
    )
    created = StubDataset.created
    assert created["fps"] == 30 and created["robot_type"] == "omy_f3m_leap"
    feats = created["features"]
    assert feats[features.KEY_STATE] == {
        "dtype": "float32", "shape": (22,), "names": feats[features.KEY_STATE]["names"]
    }
    assert feats["observation.images.cam_wrist"]["shape"] == (64, 48, 3)
    assert feats["observation.images.cam_wrist"]["dtype"] == "image"
    dataset = StubDataset.instance
    assert dataset.saved == 1 and len(dataset.rows) == report["episodes"][0]["steps"]
    assert dataset.rows[0]["task"] == "Pick up the cup"
    assert dataset.rows[0][features.KEY_ACTION].shape == (22,)
