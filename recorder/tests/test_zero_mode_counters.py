"""Things that used to pass silently: a tactile zero that did not happen, a hand that the
teleop was not driving, readings that were thrown away, and where a conversion's settings
came from."""

from __future__ import annotations

import json
import threading

import numpy as np
import pytest
from conftest import ManualRig, fake_config_dict, numeric_stream, value
from fastapi.testclient import TestClient

from tactile_rec.clock import FakeClock
from tactile_rec.config import ConfigError, parse_config
from tactile_rec.convert.dataset import NpzWriter, convert_many
from tactile_rec.convert.episode import convert_episode
from tactile_rec.convert.load import Episode
from tactile_rec.record.session import Recorder
from tactile_rec.stream import Stream, Zeroable
from tactile_rec.types import NO_TIME, STATUS_ERROR
from tactile_rec.ui.server import build_state, create_app

MS = 1_000_000


class Board(Zeroable, Stream):
    """A passive tactile stream whose zero finishes at once, with the error it is given."""

    def __init__(self, spec, clock, error=""):
        super().__init__(spec, clock)
        self._init_zero()
        self.error = error

    def zero(self):
        super().zero()
        if self.error is not None:  # None: the board never answers
            assert self._take_zero_request()
            self._zero_finished(self.error)


def with_boards(rig, **errors):
    for name, error in errors.items():
        rig.streams[name] = Board(rig.streams[name].spec, rig.clock, error)


# ---- tactile zero ------------------------------------------------------------------------------


def test_zero_is_done_by_the_reader_thread_and_the_caller_gets_the_outcome():
    clock = FakeClock()
    board = Board(numeric_stream().spec, clock, error=None)
    assert board.last_zero is None
    board.zero()
    assert board.wait_zero(0.01) == {
        "ok": False, "t_ns": NO_TIME, "error": "no answer within 0.01 s (is the board connected?)",
    }

    def reader():
        if board._take_zero_request():
            clock.set_ns(clock.now_ns() + 300 * MS)
            board._zero_finished()

    thread = threading.Thread(target=reader)
    thread.start()
    thread.join()
    assert not board._take_zero_request()  # taken once
    assert board.last_zero == {"ok": True, "error": "", "t_ns": clock.now_ns()}  # late, but known


def test_zero_reports_each_board_and_the_episode_records_its_baseline(rig):
    with_boards(rig, tactile_a="", tactile_b="CalibrationError: no ack")
    recorder = Recorder(rig.hub)
    rig.run(1.5)
    results = recorder.zero_tactile()
    assert results["tactile_a"]["ok"] and not results["tactile_b"]["ok"]
    assert "no ack" in results["tactile_b"]["error"]
    zero_ns = results["tactile_a"]["t_ns"]
    rig.run(0.4)  # the zero is inside the 1 s pre-roll
    recorder.start()
    rig.run(0.5)
    recorder.stop()
    path = recorder.save(True)
    meta = json.loads((path / "episode.json").read_text())
    assert meta["tactile_zero"]["tactile_a"] == results["tactile_a"]
    assert not meta["tactile_zero"]["tactile_b"]["ok"]
    start_ns = meta["start"]["mono_ns"]
    tactile = np.load(path / "tactile_a.npz")["t_recv_ns"]
    assert zero_ns < tactile[0] <= zero_ns + 12 * MS  # nothing from before the zero
    hand = np.load(path / "hand.npz")["t_recv_ns"]
    assert hand[0] == pytest.approx(start_ns - 1000 * MS, abs=21 * MS)  # others: full pre-roll
    events = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
    logged = [e for e in events if e["type"] == "tactile_zero"][0]["streams"]
    assert logged["tactile_b"]["error"] == results["tactile_b"]["error"]


def test_a_board_that_does_not_answer_is_a_failed_zero(tmp_path):
    rig = ManualRig(tmp_path, record={"preroll_s": 1.0, "min_free_gb": 0, "zero_timeout_s": 0.05})
    with_boards(rig, tactile_a=None)
    recorder = Recorder(rig.hub)
    result = recorder.zero_tactile()["tactile_a"]
    assert not result["ok"] and "0.05 s" in result["error"]
    assert build_state(rig.hub, recorder)["tactile_zero"] == {"tactile_a": None}
    with TestClient(create_app(rig.hub, recorder)) as client:
        answer = client.post("/api/tactile/zero", json={}).json()
        assert answer["streams"]["tactile_a"]["ok"] is False


class FakeBoard:
    def __init__(self, fail=""):
        self.fail, self.calls = fail, []

    def disable_auto_push(self):
        self.calls.append("pause")

    def enable_auto_push(self):
        self.calls.append("resume")

    def calibrate(self):
        self.calls.append("calibrate")
        if self.fail:
            raise RuntimeError(self.fail)


@pytest.mark.parametrize("fail", ["", "no response to calibrate"])
def test_paxini_zero_pauses_the_push_stream_and_reports_what_the_board_said(fail):
    from tactile_rec.streams.paxini import PaxiniStream

    cfg = {"port": "/dev/null", "baudrate": 921600, "hz": 90, "required": True,
           "places": {"Thumb-Tip": "thumb_tip"}}
    stream = PaxiniStream("tactile_a", cfg, FakeClock())
    stream._board = FakeBoard(fail)
    stream.zero()
    assert stream._take_zero_request()
    stream._run_zero()  # what the reader thread does between two frames
    result = stream.wait_zero(0.01)
    assert stream._board.calls == ["pause", "calibrate", "resume"]  # streaming resumes
    assert result["ok"] is (not fail) and fail in result["error"]
    assert stream.counters() == {"subscriber_errors": 0, "bad_frames": 0, "device_errors": 0}


# ---- readings that are thrown away -------------------------------------------------------------


def test_rejected_readings_become_the_error_only_when_nothing_good_arrives():
    clock = FakeClock()
    stream = numeric_stream(clock=clock)
    stream.reject("packet rejected: version 2")
    assert stream.health().status == STATUS_ERROR  # not "off": something arrives, all bad
    assert "version 2" in stream.health().message
    stream.push(value(1.0))
    stream.reject("packet rejected: version 2")  # one bad reading among good ones
    assert stream.health().message == ""
    clock.set_ns(clock.now_ns() + 1000 * MS)
    stream.reject("packet rejected: version 2")
    assert "version 2" in stream.health().message


def test_counters_are_shown_live_and_written_per_episode(rig):
    recorder = Recorder(rig.hub)
    rig.run(1.5)
    rig.streams["hand"].subscribe(lambda _sample: 1 / 0)  # a consumer that fails: before start
    rig.run(0.1)
    before = rig.streams["hand"].counters()["subscriber_errors"]
    assert before >= 4
    assert build_state(rig.hub, recorder)["streams"]["hand"]["counters"] == {
        "subscriber_errors": before
    }
    recorder.start()
    rig.run(0.5)
    summary = recorder.stop()
    during = summary["streams"]["hand"]["counters"]["subscriber_errors"]
    assert 24 <= during <= 26  # only what happened in this episode (0.5 s at 50 Hz)
    assert summary["streams"]["arm_state"]["counters"] == {"subscriber_errors": 0}


# ---- hand mode ---------------------------------------------------------------------------------


def record_with_mode(rig, code, from_s, to_s):
    make = rig.makers["hand"].make
    recorder = Recorder(rig.hub)
    rig.run(1.5)
    recorder.start()
    start_s = rig.clock.now_ns() / 1e9

    def with_mode(t_s):
        data = make(t_s)
        if from_s <= t_s - start_s < to_s:
            data["mode"] = np.int8(code)
        return data

    rig.makers["hand"].make = with_mode
    rig.run(3.0, on_step=recorder.tick)
    recorder.stop()
    return recorder.save(True)


def test_steps_where_the_teleop_released_the_hand_make_the_episode_a_problem(rig):
    episode = Episode(record_with_mode(rig, 2, 1.0, 2.0))
    report = convert_episode(episode, rig.config.dataset).report
    steps = report["streams"]["hand"]["mode_steps"]
    assert steps["release"] == pytest.approx(30, abs=2) and steps["hold"] == 0
    assert steps["live"] + steps["release"] == report["steps"]
    assert not report["ok"] and any("release" in problem for problem in report["problems"])


def test_hold_steps_are_counted_but_do_not_exclude_the_episode(rig):
    report = convert_episode(
        Episode(record_with_mode(rig, 1, 1.0, 1.5)), rig.config.dataset
    ).report
    assert report["streams"]["hand"]["mode_steps"]["hold"] == pytest.approx(15, abs=2)
    assert report["ok"], report["problems"]


# ---- conversion settings -----------------------------------------------------------------------


def test_hand_action_has_no_default(tmp_path):
    raw = fake_config_dict(tmp_path)
    del raw["dataset"]["hand_action"]
    with pytest.raises(ConfigError, match="hand_action must be set"):
        parse_config(raw)


def test_the_conversion_report_says_which_settings_it_was_made_with(rig, tmp_path):
    record_with_mode(rig, 0, 0, 0)
    report = convert_many(
        [rig.config.data_root], rig.config.dataset, NpzWriter(tmp_path / "out"),
        log=lambda _line: None,
    )
    assert report["dataset"]["hand_action"] == "sent" and report["dataset"]["fps"] == 30
    assert report["dataset"]["time"] == {"hand": "src"}
    json.dumps(report)


# ---- stream status in the log ------------------------------------------------------------------


def test_stream_status_changes_are_printed_once_each_in_the_form_the_hub_reads(rig, capsys):
    rig.hub.print_status_changes()  # the first time: every stream, so "off" is said too
    first = capsys.readouterr().out.splitlines()
    assert len(first) == len(rig.streams) and "[tactile-rec] stream hand: off" in first
    rig.run(1.5)
    rig.hub.print_status_changes()
    assert "[tactile-rec] stream hand: ok" in capsys.readouterr().out.splitlines()
    rig.hub.print_status_changes()
    assert capsys.readouterr().out == ""  # nothing changed: nothing printed
    rig.run(1.0, skip=("hand", "tactile_a"))
    rig.streams["tactile_a"].set_error("read failed: device disconnected")
    rig.hub.print_status_changes()
    assert sorted(capsys.readouterr().out.splitlines()) == [
        "[tactile-rec] stream hand: stale",
        "[tactile-rec] stream tactile_a: error (read failed: device disconnected)",
    ]
