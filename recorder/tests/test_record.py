from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from tactile_rec.record.session import (
    IDLE,
    RECORDING,
    REVIEW,
    Recorder,
    RecorderError,
    list_episodes,
)
from tactile_rec.types import NO_TIME


def recorded_episode(rig, seconds=2.0, success=True):
    recorder = Recorder(rig.hub)
    rig.run(1.5)  # warm up: every stream healthy, pre-roll buffer filled
    recorder.start()
    rig.run(seconds, on_step=recorder.tick)
    recorder.stop()
    return recorder, recorder.save(success)


def test_refuses_to_start_until_every_required_stream_is_healthy(rig):
    recorder = Recorder(rig.hub)
    with pytest.raises(RecorderError) as error:
        recorder.start()
    assert any("arm_state: off" in p for p in error.value.problems)
    assert not any(p.startswith("glove") for p in error.value.problems)  # optional stream
    assert recorder.state == IDLE
    rig.run(1.5)
    assert recorder.preflight() == []


def test_refuses_to_start_while_teleop_is_holding(rig):
    rig.run(1.5)
    held = rig.makers["hand"].make(0.0)
    held["mode"] = np.int8(1)
    rig.streams["hand"].push(held)
    assert any("not live" in p for p in Recorder(rig.hub).preflight())


def test_saved_episode_has_every_stream_with_preroll_and_stats(rig):
    recorder, path = recorded_episode(rig, seconds=2.0)
    assert path.name == "ep_0001" and path.parent.name.endswith("_tester")
    assert path.parent.parent.name == "pick_cup"
    assert not list(path.parent.glob("*.tmp"))
    meta = json.loads((path / "episode.json").read_text())
    assert meta["result"] == "success" and meta["mount"] == "wrist_flip"
    assert meta["duration_s"] == pytest.approx(2.0, abs=0.02)
    start_ns = meta["start"]["mono_ns"]

    tactile = np.load(path / "tactile_a.npz")
    # 1 s pre-roll + 2 s recording at 90 Hz
    assert 265 <= len(tactile["t_recv_ns"]) <= 275
    assert tactile["t_recv_ns"][0] == pytest.approx(start_ns - 1e9, abs=2e7)
    layout = meta["streams"]["tactile_a"]["meta"]["layout"]
    assert tactile["payload"].shape[1] == layout["payload_size"]
    assert np.all(np.diff(tactile["seq"]) == 1)
    stats = meta["streams"]["tactile_a"]["stats"]
    assert stats["hz"] == pytest.approx(90, abs=1) and stats["missed"] == 0

    hand = np.load(path / "hand.npz")
    assert hand["cmd"].shape == (len(hand["seq"]), 16) and hand["mode"].dtype == np.int8
    assert (hand["t_src_ns"] != NO_TIME).all()

    session = json.loads((path.parent / "session.json").read_text())
    assert session["task"] == "pick_cup" and "streams" in session["config"]


def test_video_frames_can_be_read_back_by_offset(rig):
    _, path = recorded_episode(rig, seconds=1.0)
    index = np.load(path / "cam_wrist.npz")
    frames = len(index["offset"])
    assert 58 <= frames <= 62  # 1 s pre-roll + 1 s at 30 fps
    blob = (path / "cam_wrist.mjpeg").read_bytes()
    assert index["offset"][-1] + index["size"][-1] == len(blob)
    k = frames // 2
    raw = blob[index["offset"][k] : index["offset"][k] + index["size"][k]]
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    assert image.shape == (48, 64, 3)  # stored as captured, not rotated
    meta = json.loads((path / "episode.json").read_text())
    assert meta["streams"]["cam_wrist"]["meta"]["rotation_deg"] == 90
    assert meta["streams"]["cam_wrist"]["stats"]["dropped_write"] == 0


def test_discard_removes_everything_and_reuses_the_number(rig):
    recorder = Recorder(rig.hub)
    rig.run(1.5)
    assert recorder.start() == 1
    rig.run(0.5)
    recorder.stop()
    assert recorder.state == REVIEW
    recorder.discard()
    session_dir = next((rig.config.data_root / "pick_cup").iterdir())
    assert list_episodes(session_dir) == [] and not list(session_dir.glob("ep_*"))
    assert recorder.start() == 1  # same number again
    rig.run(0.3)
    recorder.discard()  # abort while recording
    assert recorder.state == IDLE and not list(session_dir.glob("ep_*"))


def test_failure_is_kept_and_counted_separately(rig):
    recorder, _ = recorded_episode(rig, seconds=0.5, success=False)
    recorder.start()
    rig.run(0.5)
    recorder.stop()
    second = recorder.save(True)
    assert second.name == "ep_0002"
    assert recorder.status()["counts"] == {"success": 1, "failure": 1}
    first = json.loads((second.parent / "ep_0001" / "episode.json").read_text())
    assert first["result"] == "failure"


def test_dropout_during_recording_is_flagged_and_recovery_is_logged(rig):
    recorder = Recorder(rig.hub)
    seen = []
    recorder.add_listener(lambda kind, detail: seen.append((kind, detail.get("stream"))))
    rig.run(1.5)
    recorder.start()
    rig.run(0.5, on_step=recorder.tick)
    rig.run(1.0, skip=("tactile_b",), on_step=recorder.tick)  # board B goes silent
    assert recorder.status()["down"] == ["tactile_b"]
    rig.run(0.5, on_step=recorder.tick)
    summary = recorder.stop()
    assert summary["flags"]["dropouts"] == {"tactile_b": 1}
    assert ("dropout", "tactile_b") in seen and ("recovered", "tactile_b") in seen
    path = recorder.save(True)
    events = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
    kinds = [e["type"] for e in events]
    assert kinds.index("dropout") < kinds.index("recovered") < kinds.index("record_stop")
    assert json.loads((path / "episode.json").read_text())["streams"]["tactile_b"]["stats"][
        "max_gap_ms"
    ] > 900


def test_time_limit_stops_the_episode(rig):
    recorder = Recorder(rig.hub)
    recorder.set_time_limit(1.0)
    rig.run(1.5)
    recorder.start()
    rig.run(2.0, on_step=recorder.tick)
    assert recorder.state == REVIEW
    assert recorder.status()["summary"]["duration_s"] == pytest.approx(1.0, abs=0.05)


def test_commands_are_rejected_in_the_wrong_state(rig):
    recorder = Recorder(rig.hub)
    for command in (recorder.stop, lambda: recorder.save(True), recorder.discard, recorder.mark):
        with pytest.raises(RecorderError):
            command()
    rig.run(1.5)
    recorder.start()
    assert recorder.state == RECORDING
    for command in (recorder.start, recorder.zero_tactile, lambda: recorder.save(True)):
        with pytest.raises(RecorderError):
            command()
    with pytest.raises(RecorderError):
        recorder.set_session("other", "", "me")
    recorder.discard()


def test_changing_the_task_starts_a_new_session_folder(rig):
    recorder, first = recorded_episode(rig, seconds=0.3)
    recorder.set_session("open_drawer", "Open the drawer", "hamin")
    recorder.start()
    rig.run(0.3)
    recorder.stop()
    second = recorder.save(True)
    assert second.parent.parent.name == "open_drawer" and second.name == "ep_0001"
    assert second.parent.name.endswith("_hamin") and first.parent != second.parent
    with pytest.raises(RecorderError):
        recorder.set_session("bad name/../x", "", "hamin")


def test_marker_and_zero_are_written_to_the_event_log(rig):
    recorder = Recorder(rig.hub)
    rig.run(1.5)
    assert recorder.zero_tactile() == []  # passive test streams have no zero(); still logged
    recorder.start()
    rig.run(0.2)
    recorder.mark("contact")
    rig.run(0.2)
    recorder.stop()
    path = recorder.save(True)
    events = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
    assert [e for e in events if e["type"] == "mark"][0]["label"] == "contact"
    assert any(e["type"] == "tactile_zero" for e in events)
