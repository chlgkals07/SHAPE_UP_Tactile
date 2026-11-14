from __future__ import annotations

from conftest import wait_for

from control_hub.checks import CheckResult
from control_hub.incidents import Incidents
from control_hub.leapcheck import parse_leap_check
from control_hub.session import SessionLog
from control_hub.supervisor import Supervisor
from control_hub.watcher import Watcher

NO_USB = {"devices": [], "misplaced": []}


class FakeRunner:
    def __init__(self):
        self.now: dict[str, CheckResult] = {}

    def results(self):
        return dict(self.now)


def make(cfg, tmux, runner=None, scan=None):
    sup = Supervisor(cfg, tmux)
    session = SessionLog(cfg.session_dir)
    incidents = Incidents(session, sup.log_path)
    watcher = Watcher(cfg, sup, runner or FakeRunner(), session, incidents,
                      scan_fn=scan or (lambda cfg, checks: NO_USB), interval_s=0.1)
    return sup, session, watcher


def texts(session):
    return [(e["dev"], e["level"], e["text"]) for e in session.read_events(session.current)]


def test_watcher_records_without_browser(cfg, tmux):
    sup, session, watcher = make(cfg, tmux)
    watcher.start()
    try:
        sup.start("motor")
        event = wait_for(lambda: [e for e in session.read_events(session.current)
                                  if e["source"] == "log"], what="log event")[0]
        assert event["dev"] == "hand" and event["data"]["motors"] == [7]
        assert event["data"]["pid"] == "motor"
        assert wait_for(lambda: list((session.dir() / "incidents").iterdir()), what="incident")
        assert watcher.snapshot()["devices"]["hand"]["level"] == "bad"
    finally:
        watcher.stop()
        sup.kill("motor")


def test_check_transition_events(cfg, tmux):
    runner = FakeRunner()
    _, session, watcher = make(cfg, tmux, runner)
    runner.now = {"port": CheckResult(True, "ok")}
    watcher.step()  # first look: nothing changed yet
    runner.now = {"port": CheckResult(False, "없음")}
    watcher.step()
    runner.now = {"port": CheckResult(True, "ok", warn="latency timer 16")}
    watcher.step()
    assert texts(session) == [("hand", "bad", "포트 없음: 없음"),
                              ("hand", "info", "포트 다시 잡힘"),
                              ("hand", "warn", "포트: latency timer 16")]


def test_process_transitions_and_unassigned(cfg, tmux):
    sup, session, watcher = make(cfg, tmux)
    watcher.step()
    sup.start("boom")  # not part of any device
    wait_for(lambda: sup.status()["boom"]["state"] == "failed", what="boom fails")
    watcher.step()
    rows = texts(session)
    assert (None, "bad", "실패 오류 (종료 코드 3)") in rows
    assert any(r[0] is None and r[2].startswith("boom: device busy") for r in rows)
    sup.clear("boom")


def test_usb_plug_events(cfg, tmux):
    found = {"devices": [], "misplaced": []}
    _, session, watcher = make(cfg, tmux, scan=lambda cfg, checks: found)
    watcher.step()
    found["devices"] = [{"usb_id": "0403:6014", "serial": "A", "bus_path": "1-2",
                         "label": "FTDI", "product": "Serial"}]
    watcher.step()
    found["devices"] = []
    watcher.step()
    assert [r[2] for r in texts(session)] == ["USB 연결: FTDI (1-2)", "USB 빠짐: FTDI (1-2)"]


def test_tool_done_keeps_last_result(cfg, tmux):
    sup, _, watcher = make(cfg, tmux)
    watcher.step()
    sup.start("once")
    wait_for(lambda: sup.status()["once"]["state"] == "done", what="tool done")
    watcher.step()
    result = watcher.snapshot()["devices"]["hand"]["check"]
    assert result["pid"] == "once" and result["exit_code"] == 0 and "done" in result["tail"]
    assert result["table"] == parse_leap_check("done")  # None: not leap_check output
