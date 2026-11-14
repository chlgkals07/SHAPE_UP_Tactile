from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from conftest import wait_for

from control_hub.checks import CheckResult, CheckRunner, run_check
from control_hub.config import Check, load_config
from control_hub.logscan import clean
from control_hub.supervisor import HubError, Supervisor
from control_hub.tmux import TmuxError


def state_of(sup: Supervisor, pid: str) -> str:
    return sup.status()[pid]["state"]


def until(sup: Supervisor, pid: str, state: str) -> dict:
    wait_for(lambda: state_of(sup, pid) == state, what=f"{pid} -> {state}")
    return sup.status()[pid]


# ---- tmux ----
def test_tmux_spawn_log_exit_and_exact_names(tmux, tmp_path):
    script = tmp_path / "a.sh"
    script.write_text("echo first line\nread -r X\necho got $X\nexit 3\n")
    log = tmp_path / "a.log"
    tmux.spawn("arm_stock", script, log)
    wait_for(lambda: log.exists() and "first line" in log.read_text(), what="first line")
    with pytest.raises(TmuxError):
        tmux.interrupt("arm")  # a prefix of an existing name must not match
    with pytest.raises(TmuxError):
        tmux.spawn("arm_stock", script, log)
    tmux.send_line("arm_stock", "hello")
    window = wait_for(lambda: (w := tmux.windows()["arm_stock"]).dead and w, what="exit")
    assert window.exit_code in (3, -1)  # tmux sometimes loses the status; the supervisor
    # records its own (see test_failure_shows_exit_code_and_hints)
    assert "got hello" in log.read_text()
    tmux.kill("arm_stock")
    assert "arm_stock" not in tmux.windows()


def test_tmux_interrupt(tmux, tmp_path):
    script = tmp_path / "s.sh"
    script.write_text("sleep 60\n")
    tmux.spawn("sleeper", script, tmp_path / "s.log")
    wait_for(lambda: "sleeper" in tmux.windows())
    tmux.interrupt("sleeper")
    wait_for(lambda: tmux.windows()["sleeper"].dead, what="interrupt")


# ---- log cleaning ----
def test_clean_strips_terminal_noise():
    assert clean("\x1b[32m[srv] ready\x1b[0m\r\n\x1b]0;title\x07next\rover") == \
        "[srv] ready\nnext\nover"


# ---- supervisor ----
def test_start_ready_stop(cfg, tmux):
    sup = Supervisor(cfg, tmux)
    assert state_of(sup, "server") == "off"
    sup.start("server")
    info = until(sup, "server", "ready")  # the ready line is wrapped in colour codes and \r\n
    assert info["command"].startswith("bash -c ")
    text = sup.read_log("server")["text"]
    assert text.startswith("$ bash -c ") and "hello" in text and "\x1b" not in text
    with pytest.raises(HubError, match="이미 켜져"):
        sup.start("server")
    sup.stop("server")
    until(sup, "server", "off")
    assert sup.runs("server")  # the log of the finished run stays


def test_command_line_is_not_output(cfg, tmux):
    """The log starts with the command; its words are neither "ready" nor an error."""
    sup = Supervisor(cfg, tmux)
    sup.start("slow")
    wait_for(lambda: "sleep 2" in sup.read_log("slow")["text"], what="header")
    info = sup.status()["slow"]
    assert info["state"] == "starting" and info["issues"] == []
    info = until(sup, "slow", "ready")
    wait_for(lambda: sup.status()["slow"]["issues"], what="issue")
    assert [i["line"] for i in sup.status()["slow"]["issues"]] == ["it failed"]
    sup.kill("slow")


def test_requires_conflicts_and_confirm(cfg, tmux):
    sup = Supervisor(cfg, tmux)
    assert sup.status()["client"]["blockers"] == ["먼저 필요: 서버 (꺼짐)"]
    with pytest.raises(HubError, match="먼저 필요: 서버"):
        sup.start("client", confirmed=True)
    sup.start("server")
    until(sup, "server", "ready")
    with pytest.raises(HubError, match="같이 켤 수 없음"):
        sup.start("rival")
    with pytest.raises(HubError, match="확인이 필요"):
        sup.start("client")
    with pytest.raises(HubError, match="없는 옵션"):
        sup.start("client", flags=["nope"], confirmed=True)
    sup.start("client", confirmed=True)  # default flag: dry
    info = until(sup, "client", "ready")
    assert info["flags"] == ["dry"] and "# dry" in info["command"]
    assert sup.status()["server"]["dependents"] == ["client"]
    with pytest.raises(HubError, match="끄기 전 확인"):
        sup.stop("server")  # something leans on it
    with pytest.raises(HubError, match="끄기 전 확인"):
        sup.stop("client")  # confirm_stop
    sup.stop("client", confirmed=True)
    until(sup, "client", "off")
    sup.stop("server")
    until(sup, "server", "off")


def test_check_based_requirement_and_ready(cfg, tmux):
    results = {"port": CheckResult(False, "없음")}
    sup = Supervisor(cfg, tmux, lambda: results)
    with pytest.raises(HubError, match="먼저 필요: 포트 \\(없음\\)"):
        sup.start("gated")
    results["port"] = CheckResult(True, "있음")
    sup.start("gated")
    until(sup, "gated", "ready")
    results["port"] = CheckResult(False, "없음")
    assert state_of(sup, "gated") == "starting"
    sup.kill("gated")
    assert state_of(sup, "gated") == "off"


def test_failure_shows_exit_code_and_hints(cfg, tmux):
    sup = Supervisor(cfg, tmux)
    sup.start("boom")
    info = until(sup, "boom", "failed")
    assert info["exit_code"] == 3
    hints = {issue["hint"] for issue in info["issues"]}
    assert "다른 프로그램이 장치를 잡고 있습니다" in hints  # the process's own hint
    assert "명령이 없습니다. 환경 준비 줄을 확인합니다" in hints  # a global hint
    with pytest.raises(HubError, match="켜져 있지 않아"):
        sup.stop("boom")
    sup.clear("boom")
    assert state_of(sup, "boom") == "off"
    sup.start("boom")  # can be started again; a new run
    until(sup, "boom", "failed")
    assert len(sup.runs("boom")) == 2


def test_tool_done_and_input(cfg, tmux):
    sup = Supervisor(cfg, tmux)
    sup.start("once")
    assert until(sup, "once", "done")["exit_code"] == 0
    with pytest.raises(HubError, match="입력을 받지 않는"):
        sup.send_input("once", "x")
    sup.start("ask")
    wait_for(lambda: "name?" in sup.read_log("ask")["text"], what="prompt")
    sup.send_input("ask", "하민")
    until(sup, "ask", "done")
    assert "hi 하민" in sup.read_log("ask")["text"]


def test_restart_adopts_running_processes(cfg, tmux):
    first = Supervisor(cfg, tmux)
    first.start("server")
    started = until(first, "server", "ready")["started_at"]
    second = Supervisor(cfg, tmux)  # the hub restarted; tmux kept the process
    info = second.status()["server"]
    assert info["state"] == "ready" and info["started_at"] == started
    assert "hello" in second.read_log("server")["text"]
    second.stop("server")
    until(second, "server", "off")


def test_reload_marks_stale_and_keeps_orphans(cfg, tmux, config_path):
    sup = Supervisor(cfg, tmux)
    sup.start("arm_stock")
    until(sup, "arm_stock", "ready")
    text = config_path.read_text()
    config_path.write_text(text.replace("  arm_stock:\n    title: 순정\n    cmd: sleep 60",
                                        "  arm_stock:\n    title: 순정\n    cmd: sleep 61"))
    sup.reload(load_config(config_path))
    assert sup.status()["arm_stock"]["stale_config"] is True
    config_path.write_text(text.replace("  arm_stock:\n    title: 순정\n    cmd: sleep 60\n", ""))
    sup.reload(load_config(config_path))
    info = sup.status()["arm_stock"]
    assert info["orphan"] is True and info["state"] == "ready"
    sup.stop("arm_stock")
    wait_for(lambda: "arm_stock" not in sup.status(), what="orphan gone")


def test_log_offsets_and_bad_ids(cfg, tmux):
    sup = Supervisor(cfg, tmux)
    sup.start("once")
    until(sup, "once", "done")
    first = sup.read_log("once")
    assert "done" in first["text"]
    assert sup.read_log("once", offset=first["offset"])["text"] == ""
    assert sup.read_log("once", run="../../etc/passwd")["text"] == ""
    with pytest.raises(KeyError):
        sup.read_log("../x")
    with pytest.raises(KeyError):
        sup.start("nope")


# ---- checks ----
def check(kind: str, target: str) -> CheckResult:
    return run_check(Check("c", "c", kind, target), {})


def test_checks(tmp_path: Path):
    flag = tmp_path / "ttyUSB0"
    assert check("file", str(tmp_path / "tty*")).ok is False
    flag.touch()
    assert check("file", str(tmp_path / "tty*")).ok is True

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    assert check("tcp", f"127.0.0.1:{port}").ok is True
    listener.close()
    assert check("tcp", f"127.0.0.1:{port}").ok is False

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    assert check("http", f"http://127.0.0.1:{server.server_port}/").ok is True
    server.shutdown()
    server.server_close()
    assert check("http", f"http://127.0.0.1:{server.server_port}/").ok is False

    assert check("command", "true").ok is True
    bad = check("command", "echo why; false")
    assert bad.ok is False and bad.detail == "why"
    assert check("command", "sleep 10").ok is False
    assert check("no_process", "definitely_not_running_xyz_123").ok is True
    assert check("process", "definitely_not_running_xyz_123").ok is False


def test_check_runner_fills_results(cfg, tmp_path):
    runner = CheckRunner(cfg)
    assert runner.results()["port"].ok is None
    runner.run_once()
    assert runner.results()["port"].ok is False
    (tmp_path / "port.flag").touch()
    runner.run_once()
    assert runner.results()["port"].ok is True
