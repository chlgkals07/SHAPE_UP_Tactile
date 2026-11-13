"""Web API, live values and the command line tools."""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tactile_rec import features, live
from tactile_rec.cli import main
from tactile_rec.convert.load import Episode
from tactile_rec.record.session import Recorder
from tactile_rec.tools import check, inspect, tap
from tactile_rec.types import NO_TIME, SRC_MONO, SRC_REMOTE_WALL, Sample
from tactile_rec.ui.server import build_live, build_state, create_app

MS = 1_000_000


@pytest.fixture
def client(rig):
    rig.run(1.5)
    recorder = Recorder(rig.hub)
    with TestClient(create_app(rig.hub, recorder)) as test_client:
        test_client.rig, test_client.recorder = rig, recorder
        yield test_client


# ---- web API -----------------------------------------------------------------------------------


def test_a_full_episode_through_the_web_api(client):
    assert client.get("/").status_code == 200
    assert "Tactile Recorder" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/state").json()["recorder"]["state"] == "idle"

    assert client.post("/api/record/start", json={}).json() == {"episode": 1}
    client.rig.run(1.0)
    assert client.post("/api/record/mark", json={"label": "contact"}).status_code == 200
    summary = client.post("/api/record/stop", json={}).json()["summary"]
    assert summary["duration_s"] == pytest.approx(1.0, abs=0.05)
    path = client.post("/api/record/save", json={"success": True}).json()["path"]
    assert path.endswith("ep_0001")

    rows = client.get("/api/episodes").json()["episodes"]
    assert [(r["episode"], r["result"]) for r in rows] == [("ep_0001", "success")]
    session = rows[0]["session"]
    relabel = {"session": session, "episode": "ep_0001", "result": "failure"}
    assert client.post("/api/episodes/label", json=relabel).status_code == 200
    assert client.get("/api/episodes").json()["episodes"][0]["result"] == "failure"
    assert client.delete(f"/api/episodes/{session}/ep_0001").status_code == 200
    assert client.get("/api/episodes").json()["episodes"] == []


def test_commands_in_the_wrong_state_return_the_reasons(client):
    response = client.post("/api/record/save", json={"success": True})
    assert response.status_code == 409
    assert response.json()["detail"]["problems"] == ["cannot save while idle"]
    response = client.post("/api/session", json={"task": "bad name", "operator": "x"})
    assert response.status_code == 409 and "letters" in response.json()["detail"]["message"]


def test_not_ready_start_lists_problems_and_force_overrides(rig):
    recorder = Recorder(rig.hub)  # no data yet: every stream is off
    with TestClient(create_app(rig.hub, recorder)) as client:
        response = client.post("/api/record/start", json={})
        assert response.status_code == 409
        assert any("arm_state" in p for p in response.json()["detail"]["problems"])
        assert client.get("/api/state").json()["problems"]
        assert client.post("/api/record/start", json={"force": True}).status_code == 200
        summary = client.post("/api/record/stop", json={}).json()["summary"]
        assert summary["flags"]["forced_start"] is True


def test_episode_paths_cannot_escape_the_task_folder(client):
    assert client.delete("/api/episodes/..%2F..%2Fetc/passwd").status_code in (400, 404)
    bad = {"session": "../x", "episode": "ep_0001", "result": "success"}
    assert client.post("/api/episodes/label", json=bad).status_code == 400
    assert client.get("/api/stream/arm_state").status_code == 404  # not a camera


def test_session_change_through_the_api(client):
    body = {"task": "open_drawer", "text": "Open it", "operator": "hamin", "time_limit_s": 20}
    status = client.post("/api/session", json=body).json()
    assert status["task"] == "open_drawer" and status["time_limit_s"] == 20
    assert status["task_dir"].endswith("open_drawer")


def test_describe_lists_cameras_and_tactile_places_with_taxel_positions(client):
    info = client.get("/api/describe").json()
    assert info["cameras"] == [
        {"name": "cam_wrist", "rotation_deg": 90}, {"name": "cam_ext", "rotation_deg": 0}
    ]
    assert set(info["tactile"]) == set(info["tactile_order"])
    tip, pad = info["tactile"]["index_tip"], info["tactile"]["index_pad"]
    assert (tip["points"], len(tip["xy"])) == (52, 52) and len(pad["xy"]) == 25
    assert tip["board"] == "tactile_a" and tip["module"] == "Index-Tip"


def test_state_and_live_messages_are_json_and_carry_the_panels_data(client):
    state = build_state(client.rig.hub, client.recorder)
    json.dumps(state)
    assert state["streams"]["tactile_a"]["status"] == "ok"
    assert state["streams"]["glove"]["required"] is False
    message = build_live(client.rig.hub)
    json.dumps(message)
    assert len(message["tactile"]) == 8 and len(message["tactile"]["thumb_tip"]["fz"]) == 52
    assert len(message["hand"]["cmd"]) == 16 and len(message["arm"]["state"]) == 6


# ---- live values -------------------------------------------------------------------------------


def test_preview_is_upright_and_scaled(rig):
    import cv2

    rig.run(0.2)
    seq, jpeg = live.preview_jpeg(rig.hub, "cam_wrist", width=24)
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert image.shape[:2] == (32, 24)  # stored 48x64, rotated to 64x48, scaled to width 24
    assert seq == rig.streams["cam_wrist"].latest().seq
    assert live.preview_jpeg(rig.hub, "nope", 100) is None


def test_live_observation_matches_what_the_converter_would_write(rig):
    assert live.observe(rig.hub) is None  # nothing received yet
    rig.run(0.5)
    obs = live.observe(rig.hub)
    hand, arm = rig.streams["hand"].latest(), rig.streams["arm_state"].latest()
    np.testing.assert_allclose(obs[features.KEY_STATE][:6], arm.data["pos"], rtol=1e-6)
    np.testing.assert_allclose(obs[features.KEY_STATE][6:], np.deg2rad(hand.data["pos"]), rtol=1e-5)
    assert obs[features.KEY_TACTILE].shape == (24,)
    assert obs[features.KEY_TACTILE_DIST].shape == (924,)
    assert obs["observation.images.cam_wrist"].shape == (64, 48, 3)


def test_taxel_positions_come_from_the_vendor_files_or_a_grid():
    assert len(live.taxel_xy(52)) == 52 and len(live.taxel_xy(25)) == 25
    grid = live.taxel_xy(7)  # no sensor has 7 points: plain grid
    assert len(grid) == 7 and grid[0] == [0.0, 0.0]


# ---- tools -------------------------------------------------------------------------------------


def test_onsets_find_each_event_once():
    times = np.arange(0, 10, 0.01)
    activity = np.full(times.size, 2.0) + 0.01 * np.sin(times * 50)
    for start in (1.0, 4.0, 7.5):
        activity[(times >= start) & (times < start + 0.08)] = 30.0
    np.testing.assert_allclose(tap.onsets(times, activity), [1.0, 4.0, 7.5], atol=0.011)
    assert tap.onsets(times, np.full(times.size, 2.0)).size == 0  # nothing happened


def test_pair_offsets_ignores_unmatched_events():
    offsets = tap.pair_offsets(np.array([1.0, 4.0, 7.5]), np.array([1.03, 4.02, 9.9]))
    np.testing.assert_allclose(offsets, [0.03, 0.02], atol=1e-9)


def test_tap_tool_measures_a_known_delay_between_streams(rig, capsys):
    recorder = Recorder(rig.hub)
    rig.run(1.5)
    recorder.start()
    rig.run(13.0)
    recorder.stop()
    path = recorder.save(True)
    # Make tactile board B arrive 40 ms late, as a slow USB path would.
    late = dict(np.load(path / "tactile_b.npz"))
    late["t_recv_ns"] = late["t_recv_ns"] + 40 * MS
    np.savez(path / "tactile_b.npz", **late)

    episode = Episode(path)
    result = tap.analyse(episode, "tactile_a.force")
    episode.close()
    signals = result["signals"]
    assert signals["tactile_a.force"]["events"] >= 3
    assert signals["tactile_b.force"]["offset_ms"] == pytest.approx(40, abs=1)
    assert abs(signals["hand.current"]["offset_ms"]) <= 20  # one hand period
    assert abs(signals["cam_ext"]["offset_ms"]) <= 34  # one camera period
    assert signals["arm_state"]["events"] == 0  # smooth motion has no sharp event

    assert tap.run(str(path), "tactile_a.force") == 0
    assert "tactile_b.force" in capsys.readouterr().out
    assert tap.run(str(path), "no_such_signal") == 2


def test_check_summary_reports_rate_gaps_and_delay():
    samples = [
        Sample(t_recv_ns=k * 10 * MS + 3 * MS, seq=k, data={}, t_src_ns=k * 10 * MS, src_seq=s)
        for k, s in enumerate([0, 1, 2, 5, 6])
    ]
    summary = check.summarise(samples, SRC_MONO, {"mono_ns": 0, "wall_ns": 0})
    assert summary["count"] == 5 and summary["hz"] == pytest.approx(100)
    assert summary["missed"] == 2 and summary["delay_ms"]["median"] == pytest.approx(3.0)
    remote = check.summarise(samples, SRC_REMOTE_WALL, {"mono_ns": 0, "wall_ns": 0})
    assert "delay_ms" not in remote and remote["delay_jitter_ms"] == 0.0  # offset is unknown
    bare = [Sample(t_recv_ns=k * MS, seq=k, data={}) for k in range(3)]
    assert check.summarise(bare, SRC_MONO, {"mono_ns": 0, "wall_ns": 0})["source_stamps"] == "0/3"
    assert samples[0].src_seq != NO_TIME


def test_inspect_and_cli_convert_on_a_recorded_episode(rig, tmp_path, capsys):
    import yaml
    from conftest import fake_config_dict

    recorder = Recorder(rig.hub)
    rig.run(1.5)
    recorder.start()
    rig.run(1.0)
    recorder.stop()
    path = recorder.save(True)
    assert inspect.run(str(path)) == 0
    out = capsys.readouterr().out
    assert "tactile_a" in out and "success" in out and "1 episode(s)" in out
    assert inspect.run(str(tmp_path / "nothing")) == 2

    config_path = tmp_path / "rig.yaml"
    config_path.write_text(yaml.safe_dump(fake_config_dict(tmp_path)))
    out_dir = tmp_path / "npz_out"
    args = ["convert", "--config", str(config_path), "--in", str(path), "--out", str(out_dir),
            "--format", "npz"]
    assert main(args) == 0
    assert (out_dir / "episode_000000.npz").is_file()
    report = json.loads((tmp_path / "npz_out.conversion_report.json").read_text())
    assert report["written"] == 1 and report["episodes"][0]["ok"]
    assert main(args) == 2  # output exists and --overwrite was not given
    assert main([*args, "--overwrite"]) == 0
    assert main(["convert", "--config", str(tmp_path / "missing.yaml"), "--in", str(path),
                 "--out", str(out_dir)]) == 2


def test_check_command_passes_on_a_healthy_fake_stream(tmp_path, capsys):
    import yaml
    from conftest import fake_config_dict

    config_path = tmp_path / "rig.yaml"
    config_path.write_text(yaml.safe_dump(fake_config_dict(tmp_path)))
    assert main(["check", "tactile_a", "--config", str(config_path), "--seconds", "2"]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "payload" in out
    assert main(["check", "nope", "--config", str(config_path)]) == 2
