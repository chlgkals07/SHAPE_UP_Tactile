"""Nothing recorded is lost without an explicit discard: chunks on disk while recording,
episodes left unsaved when the program ends, and episodes cut off by a crash."""

from __future__ import annotations

import json

import numpy as np
import pytest
from conftest import ManualRig, fake_config_dict
from fastapi.testclient import TestClient

from tactile_rec.convert.episode import convert_episode
from tactile_rec.convert.load import Episode
from tactile_rec.record import recover, session
from tactile_rec.record.session import IDLE, REVIEW, Recorder, RecorderError, list_episodes
from tactile_rec.ui.server import create_app


def started(rig, seconds=1.0):
    recorder = Recorder(rig.hub)
    rig.run(1.5)  # warm up: every stream healthy, pre-roll buffer filled
    recorder.start()
    rig.run(seconds, on_step=recorder.tick)
    return recorder


def cut_off(rig, on_disk_s=1.0, lost_s=0.5):
    """An episode whose recorder died: `on_disk_s` reached the disk, `lost_s` did not."""
    recorder = started(rig, on_disk_s)
    recorder._writer.flush()
    rig.run(lost_s)
    recorder._writer.abort()  # stands in for the process ending: threads stop, nothing is joined
    return recorder._tmp_dir


def test_rows_reach_the_disk_in_chunks_while_recording(rig):
    recorder = started(rig, 1.0)
    tmp_dir = recorder._tmp_dir
    assert json.loads((tmp_dir / "recording.json").read_text())["episode"] == 1  # from the start
    recorder._writer.flush()
    part = np.load(tmp_dir / "parts" / "hand.part000000.npz")
    assert 95 <= len(part["seq"]) <= 105 and part["cmd"].shape[1] == 16  # 1 s pre-roll + 1 s
    index = np.load(tmp_dir / "parts" / "cam_wrist.part000000.npz")
    on_disk = (tmp_dir / "cam_wrist.mjpeg").stat().st_size
    assert index["offset"][-1] + index["size"][-1] <= on_disk  # the index never runs ahead
    rig.run(1.0, on_step=recorder.tick)
    recorder._writer.flush()
    rig.run(0.5, on_step=recorder.tick)
    recorder.stop()
    path = recorder.save(True)
    assert not (path / "parts").exists() and not (path / "recording.json").exists()
    hand = np.load(path / "hand.npz")
    assert np.all(np.diff(hand["seq"]) == 1)  # the chunks join without a gap or a repeat
    assert 170 <= len(hand["seq"]) <= 180  # 1 s pre-roll + 2.5 s at 50 Hz


def test_an_episode_cut_off_by_a_crash_is_recovered_up_to_the_last_chunk(rig):
    tmp_dir = cut_off(rig, on_disk_s=1.0, lost_s=0.5)
    assert not (tmp_dir / "episode.json").exists()
    assert recover.pending_episodes(tmp_dir.parent) == [tmp_dir]

    path = recover.keep(tmp_dir, "success")
    assert path.name == "ep_0001" and list_episodes(path.parent) == [path]
    meta = json.loads((path / "episode.json").read_text())
    assert meta["flags"]["recovered"] and meta["flags"]["write_errors"] == {}
    assert meta["duration_s"] == pytest.approx(1.0, abs=0.05)  # the lost half second is not there
    assert meta["streams"]["hand"]["stats"]["hz"] == pytest.approx(50, abs=1)
    index = np.load(path / "cam_ext.npz")
    assert 58 <= len(index["offset"]) <= 62
    episode = Episode(path)
    assert episode.frame("cam_ext", len(index["offset"]) - 1).shape == (48, 64, 3)
    converted = convert_episode(episode, rig.config.dataset)
    assert converted.steps == pytest.approx(30, abs=2)
    assert any("recovered" in problem for problem in converted.report["problems"])


def test_closing_the_program_while_recording_keeps_the_episode_unsaved(rig):
    recorder = started(rig, 1.0)
    kept = recorder.close()
    assert recorder.state == REVIEW and kept is not None and kept.name == "ep_0001.tmp"
    meta = json.loads((kept / "episode.json").read_text())
    assert meta["result"] is None and meta["duration_s"] == pytest.approx(1.0, abs=0.05)

    again = Recorder(rig.hub)  # the program is started again
    again.start()
    rig.run(0.3)
    again.stop()
    assert again.save(True).name == "ep_0002"  # the unsaved one keeps its number
    assert recover.keep(kept, "failure").name == "ep_0001"


def test_an_episode_that_cannot_be_finished_stays_on_disk(rig, monkeypatch):
    recorder = started(rig, 0.5)
    tmp_dir = recorder._tmp_dir
    real = session.write_json

    def no_episode_file(path, data):
        if path.name == "episode.json":
            raise OSError(28, "No space left on device")
        real(path, data)

    monkeypatch.setattr(session, "write_json", no_episode_file)
    with pytest.raises(RecorderError, match="kept in"):
        recorder.stop()
    monkeypatch.undo()
    assert recorder.state == IDLE and (tmp_dir / "hand.npz").is_file()
    assert recorder.start() == 2  # recording works again
    recorder.discard()
    assert recover.keep(tmp_dir, "success").name == "ep_0001"


def test_recording_stops_before_the_disk_is_full(tmp_path, monkeypatch):
    rig = ManualRig(tmp_path, record={"preroll_s": 1.0, "min_free_gb": 5})
    recorder = Recorder(rig.hub)
    seen = []
    recorder.add_listener(lambda kind, _detail: seen.append(kind))
    free = {"gb": 50.0}
    monkeypatch.setattr(recorder, "_free_gb", lambda: free["gb"])
    rig.run(1.5)
    recorder.start()
    rig.run(0.5, on_step=recorder.tick)
    assert recorder.state == "recording"
    free["gb"] = 4.0
    rig.run(0.2, on_step=recorder.tick)
    assert recorder.state == REVIEW and "disk_low" in seen
    assert recorder.status()["summary"]["flags"]["disk_low"]
    recorder.discard()

    recorder.start(force=True)  # the operator starts although the disk is already low
    rig.run(0.5, on_step=recorder.tick)
    assert recorder.state == "recording"  # not stopped again at once
    recorder.discard()


def test_unsaved_episodes_are_listed_kept_and_deleted_through_the_web_api(rig):
    first = cut_off(rig, on_disk_s=0.5, lost_s=0.2)
    recorder = Recorder(rig.hub)  # the program is started again
    with TestClient(create_app(rig.hub, recorder)) as client:
        recorder.start()
        rig.run(0.5)
        recorder.stop()  # ep_0002.tmp is in review: the recorder's own, not listed
        rows = client.get("/api/episodes").json()["episodes"]
        assert [(r["episode"], r["pending"], r["cut_off"]) for r in rows] == [
            ("ep_0001.tmp", True, True)
        ]
        session_name = rows[0]["session"]
        in_use = {"session": session_name, "episode": "ep_0002.tmp", "result": "success"}
        assert client.post("/api/episodes/label", json=in_use).status_code == 409
        assert client.delete(f"/api/episodes/{session_name}/ep_0002.tmp").status_code == 409
        recorder.discard()

        keep = {"session": session_name, "episode": "ep_0001.tmp", "result": "success"}
        assert client.post("/api/episodes/label", json=keep).json() == {"episode": "ep_0001"}
        rows = client.get("/api/episodes").json()["episodes"]
        assert [(r["episode"], r["pending"], r["recovered"]) for r in rows] == [
            ("ep_0001", False, True)
        ]
        assert not first.exists()

        recorder.start()
        rig.run(0.3)
        left = recorder.close()  # closed with the episode unsaved, then deleted from the list
        recorder.state, recorder._tmp_dir = IDLE, None  # as after a restart
        assert client.delete(f"/api/episodes/{session_name}/{left.name}").status_code == 200
        assert not left.exists()


def test_flush_period_comes_from_the_config(tmp_path):
    from tactile_rec.config import ConfigError, parse_config

    raw = fake_config_dict(tmp_path, record={"flush_s": 2.0})
    assert parse_config(raw).record.flush_s == 2.0
    with pytest.raises(ConfigError, match="flush_s"):
        parse_config(fake_config_dict(tmp_path, record={"flush_s": 0}))
