"""What the recorder says about its streams reaches the device the stream belongs to."""

from __future__ import annotations

import pytest

from control_hub.checks import CheckResult
from control_hub.devices import device_states
from control_hub.incidents import Incidents
from control_hub.logscan import LogScanner
from control_hub.session import SessionLog
from control_hub.watcher import Watcher

NOW = 1_700_000_000.0
LOG = """$ tactile-rec record --config config/rig.yaml
[tactile-rec] rig omy_f3m_leap (wrist_flip), data under /data
[tactile-rec] stream hand: off
[tactile-rec] stream cam_wrist: error (open failed: No device connected)
[tactile-rec] stream hand: ok
[tactile-rec] stream arm_state: slow
"""


def scanner_for(tmp_path, text=LOG):
    path = tmp_path / "run.log"
    path.write_text(text, encoding="utf-8")
    scanner = LogScanner(path, None, [])
    scanner.poll()
    return scanner


def test_stream_lines_become_events_and_the_last_status_is_kept(tmp_path):
    scanner = scanner_for(tmp_path)
    assert scanner.streams == {
        "hand": {"status": "ok", "message": ""},
        "cam_wrist": {"status": "error", "message": "open failed: No device connected"},
        "arm_state": {"status": "slow", "message": ""},
    }
    events = scanner.drain()
    assert [(e.stream, e.level) for e in events] == [("cam_wrist", "bad"), ("arm_state", "warn")]
    assert events[0].text == "녹화기 cam_wrist: 오류 (open failed: No device connected)"
    # "open failed" also looks like a generic error: it is one event, not two, and no raw issue
    assert list(scanner.issues) == []


def test_status_survives_a_hub_restart_without_repeating_the_events(tmp_path):
    path = tmp_path / "run.log"
    path.write_text(LOG, encoding="utf-8")
    scanner = LogScanner(path, None, [])
    scanner.skip_existing()
    assert scanner.drain() == [] and scanner.streams["cam_wrist"]["status"] == "error"


class OneLog:
    """Stands in for the supervisor: one running process with this scanner."""

    def __init__(self, pid, scanner):
        self.pid, self.scanner = pid, scanner

    def drain_events(self):
        return {self.pid: self.scanner.drain()}


def test_an_event_goes_to_the_device_of_the_stream_not_of_the_process(cfg, tmp_path):
    # "server" is a process of the device "hand"; the recorder would be a process of none.
    text = "$ rec\n[tactile-rec] stream hand: stale\n[tactile-rec] stream cam_wrist: stale\n"
    supervisor = OneLog("server", scanner_for(tmp_path, text))
    session = SessionLog(cfg.session_dir)
    watcher = Watcher(cfg, supervisor, None, session, Incidents(session, lambda *_: tmp_path),
                      scan_fn=lambda *_: None)
    hand, camera = watcher._log_events({"server": {"run": "r1"}})
    assert hand.dev == "hand" and hand.level == "bad" and hand.text == "녹화기 hand: 끊김"
    assert camera.dev is None  # no device has that stream: shown as unassigned, not as "hand"


@pytest.mark.parametrize(
    ("status", "state", "level"),
    [("error", "ready", "bad"), ("stale", "ready", "bad"), ("slow", "ready", "warn"),
     ("off", "starting", "warn"), ("ok", "ready", "ok"),
     # a recorder that is gone or going says nothing
     ("error", "failed", "ok"), ("error", "stopping", "ok")],
)
def test_device_follows_what_a_running_recorder_last_said(cfg, status, state, level):
    procs = {"rival": {"state": state,
                       "streams": {"hand": {"status": status, "message": "bad packet"}}}}
    checks = {"port": CheckResult(True, "ok")}
    hand = device_states(cfg, procs, checks, [], NOW + 3600)["hand"]  # long after any event
    assert hand["level"] == level
    if level != "ok":
        assert hand["summary"].startswith("녹화기 hand:") and "bad packet" in hand["summary"]
