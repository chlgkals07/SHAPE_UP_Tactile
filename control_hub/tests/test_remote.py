from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time

import pytest

from conftest import wait_for
from control_hub.command import build_command
from control_hub.config import load_config
from control_hub.remote import PROBE, TAG, RemoteWatcher, probe_command, run_probe
from control_hub.supervisor import HubError, Supervisor

LOCAL_PROBE = [sys.executable, "-c", PROBE]


def tagged_sleep(tag: str) -> subprocess.Popen:
    # through bash -c "a && b" like a real remote command: bash execs the last command away
    return subprocess.Popen(["bash", "-c", f"export {TAG}={tag} && sleep 30"],
                            env={**os.environ, TAG: ""})


def test_probe_finds_tagged_processes_and_stops_them():
    child = tagged_sleep("leftover_test")
    try:
        found = wait_for(lambda: run_probe(LOCAL_PROBE, ["leftover_test", "other"]),
                         what="tagged process")
        assert list(found) == ["leftover_test"]
        assert found["leftover_test"][0][0] == child.pid
        assert "sleep 30" in found["leftover_test"][0][1]
        after = run_probe(LOCAL_PROBE, ["leftover_test"], "INT", "leftover_test")
        assert child.wait(5) != 0  # SIGINT ended it
        assert after["leftover_test"]  # reported as seen when the signal went out
        assert run_probe(LOCAL_PROBE, ["leftover_test"]) == {}
    finally:
        child.kill()


def test_probe_reports_a_failed_link():
    with pytest.raises(OSError, match="no route"):
        run_probe(["bash", "-c", "echo 'ssh: no route to host' >&2; exit 255"], ["x"])


def test_remote_commands_carry_the_tag(cfg):
    host = cfg.hosts["robot_container"]
    argv = probe_command(host)
    assert argv[:2] == ["ssh", "-o"] and argv[-2] == host.ssh
    assert argv[-1].startswith("docker exec -i open_manipulator python3 -c ")
    local = build_command(cfg, cfg.processes["server"])
    assert TAG not in local


REMOTE = """
processes:
  far:
    title: 멀리
    host: robot_container
    cmd: sleep 60
    confirm_stop: [받치고 있다]
  near:
    title: 가까이
    cmd: sleep 60
"""


@pytest.fixture
def remote_cfg(config_path):
    text = config_path.read_text(encoding="utf-8")
    head = text.split("processes:")[0]
    config_path.write_text(head + textwrap.dedent(REMOTE), encoding="utf-8")
    return load_config(config_path)


class FakeHost:
    """Stands in for ssh + the probe: a set of tagged process ids that are 'still running'."""

    def __init__(self) -> None:
        self.running: dict[str, list[list]] = {}
        self.signals: list[tuple[str, str]] = []
        self.down = False

    def __call__(self, argv, ids, signal=None, target=None):
        if self.down:
            raise OSError("ssh: connect to host robot.invalid: No route to host")
        found = {k: v for k, v in self.running.items() if k in ids}
        if signal:
            self.signals.append((target, signal))
        return found


def test_leftover_is_shown_blocks_start_and_can_be_stopped(remote_cfg, tmux):
    host = FakeHost()
    watcher = RemoteWatcher(remote_cfg, runner=host)
    sup = Supervisor(remote_cfg, tmux, remote=watcher)
    assert "export CONTROL_HUB_ID=far && sleep 60" in build_command(remote_cfg, remote_cfg.processes["far"])

    watcher.check("robot_container")
    assert "remote_left" not in sup.status()["far"]

    # the ssh link died, the launch kept running in the container
    host.running["far"] = [[4242, "/usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch x y"]]
    time.sleep(1.1)
    watcher.check("robot_container")
    state = sup.status()["far"]
    assert state["state"] == "off"
    assert state["remote_left"]["count"] == 1
    assert "ros2 launch" in state["remote_left"]["procs"][0]
    assert any("Robot PC" in b for b in state["blockers"])
    with pytest.raises(HubError, match="Robot PC"):
        sup.start("far")
    assert "remote_left" not in sup.status()["near"]  # a local process is never asked about

    with pytest.raises(HubError, match="확인"):
        sup.remote_stop("far")
    assert sup.remote_stop("far", confirmed=True) == 1
    assert host.signals == [("far", "INT")]
    assert sup.status()["far"]["remote_left"]["stop_sent_at"]
    sup.remote_stop("far", force=True, confirmed=True)
    assert host.signals[-1] == ("far", "KILL")

    host.running.clear()
    watcher.check("robot_container")
    state = sup.status()["far"]
    assert "remote_left" not in state and not state["blockers"]
    with pytest.raises(HubError, match="남은 프로세스가 없습니다"):
        sup.remote_stop("far", confirmed=True)


def test_unreachable_host_is_reported_only_for_a_failed_process(remote_cfg, tmux):
    host = FakeHost()
    host.down = True
    watcher = RemoteWatcher(remote_cfg, runner=host)
    sup = Supervisor(remote_cfg, tmux, remote=watcher)
    watcher.check("robot_container")
    assert "remote_unknown" not in sup.status()["far"]  # off: nothing to worry about
    with pytest.raises(HubError, match="닿지 않습니다"):
        sup.remote_stop("far", confirmed=True)
    with pytest.raises(HubError, match="원격 프로세스가 아닙니다"):
        sup.remote_stop("near")
