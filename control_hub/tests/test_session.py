from __future__ import annotations

import json

import pytest

from control_hub.checks import CheckResult
from control_hub.devices import device_states
from control_hub.session import Event, SessionLog


def ev(t, dev, level="bad", text="문제", **data):
    return Event(t, dev, "log", level, text, data)


class Clock:
    def __init__(self, t=1_700_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_session_writes_jsonl_and_recent(tmp_path):
    clock = Clock()
    log = SessionLog(tmp_path, now=clock)
    log.add(ev(clock.t - 100, "hand", text="옛날"))
    log.add(ev(clock.t, "hand", text="지금"))
    log.add(ev(clock.t, None, "warn", text="기타"))
    lines = (log.dir() / "events.jsonl").read_text().splitlines()
    assert [json.loads(x)["text"] for x in lines] == ["옛날", "지금", "기타"]
    assert [e.text for e in log.recent(60)] == ["지금", "기타"]
    assert [e.text for e in log.recent(dev="hand")] == ["옛날", "지금"]
    assert log.read_events(log.current)[1]["dev"] == "hand"


def test_new_session_and_retention(tmp_path):
    clock = Clock()
    log = SessionLog(tmp_path, keep=2, now=clock)
    first = log.current
    clock.t += 1
    second = log.new_session()
    clock.t += 1
    third = log.new_session()
    assert [s["id"] for s in log.sessions()] == [third, second]
    assert not (tmp_path / first).exists() and log.recent() == []


def test_same_second_sessions_get_distinct_ids(tmp_path):
    first = SessionLog(tmp_path, now=Clock())
    second = SessionLog(tmp_path, now=Clock())
    assert first.current != second.current and len(second.sessions()) == 2


def test_note_run(tmp_path):
    log = SessionLog(tmp_path, now=Clock())
    log.note_run("server", "20261115-140000", tmp_path / "x.log")
    runs = json.loads((log.dir() / "runs.json").read_text())
    assert runs == [{"pid": "server", "run": "20261115-140000", "log": str(tmp_path / "x.log")}]


@pytest.mark.parametrize("sid", ["../x", "2026-11-15_140210/../../etc", ""])
def test_read_events_rejects_bad_id(tmp_path, sid):
    with pytest.raises(KeyError):
        SessionLog(tmp_path, now=Clock()).read_events(sid)


# ---- device state ----
NOW = 1_700_000_000.0


def test_device_bad_from_check(cfg):
    states = device_states(cfg, {}, {"port": CheckResult(False, "없음")}, [], NOW)
    assert states["hand"]["level"] == "bad" and "없음" in states["hand"]["summary"]


def test_device_warn_from_check_warning(cfg):
    states = device_states(cfg, {}, {"port": CheckResult(True, "ok", warn="latency timer 16")},
                           [], NOW)
    assert states["hand"]["level"] == "warn" and states["hand"]["summary"] == "latency timer 16"


def test_device_bad_from_failed_process(cfg):
    states = device_states(cfg, {"server": {"state": "failed"}},
                           {"port": CheckResult(True, "ok")}, [], NOW)
    assert states["hand"]["level"] == "bad" and "서버" in states["hand"]["summary"]


def test_device_bad_from_recent_event_then_ok_after_60s(cfg):
    events = [ev(NOW - 5, "hand", text="모터 응답 없음: 7", motors=[7])]
    checks = {"port": CheckResult(True, "ok")}
    assert device_states(cfg, {}, checks, events, NOW)["hand"]["level"] == "bad"
    assert device_states(cfg, {}, checks, events, NOW + 61)["hand"]["level"] == "ok"


def test_device_idle_when_nothing_to_check_and_nothing_runs(tmp_path):
    from control_hub.config import load_config
    path = tmp_path / "hub.yaml"
    path.write_text("processes: {a: {cmd: x}}\ndevices: {d: {processes: [a]}}")
    states = device_states(load_config(path), {"a": {"state": "off"}}, {}, [], NOW)
    assert states["d"]["level"] == "idle"


def test_leap_motors_from_events(cfg):
    events = [ev(NOW - 5, "hand", text="모터 응답 없음: 3, 7", motors=[3, 7])]
    motors = device_states(cfg, {}, {}, events, NOW)["hand"]["motors"]
    assert set(motors) == {3, 7} and motors[7]["text"] == "모터 응답 없음: 3, 7"


def test_unassigned_issue_goes_to_other(cfg):
    events = [ev(NOW - 1, None, "warn", text="something failed")]
    other = device_states(cfg, {}, {}, events, NOW)["_other"]
    assert other["level"] == "warn" and other["events"][0]["text"] == "something failed"
