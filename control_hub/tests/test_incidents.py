from __future__ import annotations

import io
import zipfile

import pytest

from control_hub.incidents import Incidents
from control_hub.session import Event, SessionLog


class Clock:
    def __init__(self):
        self.t = 1_700_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def rig(tmp_path):
    clock = Clock()
    logs = tmp_path / "logs"
    logs.mkdir()

    def log_path(pid, run):
        return logs / f"{pid}-{run}.log"

    session = SessionLog(tmp_path / "sessions", now=clock)
    return clock, session, Incidents(session, log_path, now=clock), log_path


def bad(clock, text="모터 응답 없음: 7", dev="hand", pid="leap", run="r1"):
    return Event(clock.t, dev, "log", "bad", text, {"pid": pid, "run": run, "line": "IDs: [7]"})


def test_incident_folder_contents(rig):
    clock, session, incidents, log_path = rig
    log_path("leap", "r1").write_text("$ cmd\n" + "".join(f"line {i}\n" for i in range(300)))
    log_path("arm", "a1").write_text("$ arm\narm ok\n")
    iid = incidents.on_event(bad(clock), {"leap": "r1", "arm": "a1"}, {"port": {"ok": True}},
                             {"devices": []})
    folder = session.dir() / "incidents" / iid
    assert iid[6:12] == "_hand_" and iid.endswith("모터_응답_없음_7")
    assert (folder / "summary.md").read_text().startswith("# 모터 응답 없음: 7")
    assert '"port"' in (folder / "checks.json").read_text()
    assert not (folder / "leap.log").exists()  # filled 30 s later
    with log_path("leap", "r1").open("a") as handle:
        handle.write("after the error\n")
    clock.t += 31
    incidents.tick()
    text = (folder / "leap.log").read_text().splitlines()
    assert text[0] == "line 100" and text[199] == "line 299" and text[-1] == "after the error"
    assert (folder / "others" / "arm.log").read_text().splitlines()[-1] == "arm ok"


def test_non_bad_event_makes_no_incident(rig):
    clock, _, incidents, _ = rig
    event = Event(clock.t, "hand", "log", "warn", "느림", {})
    assert incidents.on_event(event, {}, {}, {}) is None


def test_incident_groups_repeats(rig):
    clock, session, incidents, _ = rig
    first = incidents.on_event(bad(clock), {}, {}, {})
    clock.t += 10
    assert incidents.on_event(bad(clock), {}, {}, {}) == first
    [row] = incidents.list(session.current)
    assert row["count"] == 2 and row["last_t"] == clock.t
    clock.t += 31
    assert incidents.on_event(bad(clock), {}, {}, {}) != first


def test_tool_result_attached_within_5min(rig):
    clock, session, incidents, log_path = rig
    iid = incidents.on_event(bad(clock), {}, {}, {})
    log_path("leap_check", "c1").write_text("$ leap_check\nHardware errors: [0]\n")
    clock.t += 120
    incidents.on_tool_done("hand", "leap_check", "c1")
    folder = session.dir() / "incidents" / iid
    assert "Hardware errors" in (folder / "leap_check.txt").read_text()


def test_tool_result_ignored_after_5min(rig):
    clock, session, incidents, log_path = rig
    iid = incidents.on_event(bad(clock), {}, {}, {})
    log_path("leap_check", "c1").write_text("$ leap_check\n")
    clock.t += 301
    incidents.on_tool_done("hand", "leap_check", "c1")
    assert not (session.dir() / "incidents" / iid / "leap_check.txt").exists()


@pytest.mark.parametrize("iid", ["../x", "x/y", "..", ""])
def test_read_rejects_traversal(rig, iid):
    _, session, incidents, _ = rig
    with pytest.raises(KeyError):
        incidents.read(session.current, iid)


def test_read_and_zip(rig):
    clock, session, incidents, _ = rig
    iid = incidents.on_event(bad(clock), {}, {}, {})
    data = incidents.read(session.current, iid)
    assert data["summary"].startswith("# 모터") and "checks.json" in data["files"]
    names = zipfile.ZipFile(io.BytesIO(incidents.zip(session.current, iid))).namelist()
    assert f"{iid}/summary.md" in names
    whole = zipfile.ZipFile(io.BytesIO(incidents.zip(session.current, None))).namelist()
    assert f"{session.current}/incidents/{iid}/summary.md" in whole
