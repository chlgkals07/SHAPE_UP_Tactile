from __future__ import annotations

import os
import textwrap
import time
from pathlib import Path

import pytest

from control_hub.config import load_config
from control_hub.tmux import Tmux

BASE = """
log_dir: {log_dir}
tmux: {{socket: {socket}, session: hub}}
hosts:
  robot: {{ssh: root@robot.invalid}}
  robot_container: {{ssh: root@robot.invalid, container: open_manipulator}}
envs:
  greet: ["export GREETING=hello"]
hints:
  - {{match: "command not found", hint: "명령이 없습니다. 환경 준비 줄을 확인합니다"}}
processes:
  server:
    title: 서버
    kind: service
    env: greet
    cmd: 'echo "$GREETING"; printf "\\033[32m[srv] ready now\\033[0m\\r\\n"; sleep 60'
    ready: {{log: "\\\\[srv\\\\] ready"}}
  client:
    title: 클라이언트
    cmd: sleep 60
    requires: [server]
    confirm_start: [확인 하나, {{text: 실물 확인, unless_flag: dry}}]
    confirm_stop: [받치고 있다]
    flags: [{{id: dry, label: dry-run, arg: "# dry", default: true}}]
  rival:
    title: 경쟁자
    cmd: sleep 60
    conflicts: [server]
  gated:
    title: 포트 대기
    cmd: sleep 60
    requires: [port]
    ready: {{check: port}}
  boom:
    title: 실패
    cmd: 'echo "boom: device busy"; nosuchcommand_xyz; exit 3'
    hints: [{{match: "device busy", hint: "다른 프로그램이 장치를 잡고 있습니다"}}]
  slow:
    title: 느린 시작
    cmd: 'sleep 2; echo "now [slow] up"; echo "it failed"; sleep 60'
    ready: {{log: "\\\\[slow\\\\] up"}}
  once:
    title: 한 번
    kind: tool
    cmd: echo done
  ask:
    title: 묻기
    kind: tool
    input: true
    cmd: 'printf "name? "; read -r NAME; echo "hi $NAME"'
  arm_stock:
    title: 순정
    cmd: sleep 60
checks:
  port: {{title: 포트, file: {flag}}}
profiles:
  - {{id: demo, title: 데모, steps: [{{note: 전원을 켠다}}, server, client]}}
devices:
  hand:
    title: 손
    kind: leap
    recorder_stream: hand
    checks: [port]
    processes: [server]
    tools: [once]
    usb_id: "0403:6014"
    events:
      - {{match: "IDs: \\\\[?(?P<motors>[\\\\d, ]+)", level: bad, text: "모터 없음: {{motors}}"}}
"""


def wait_for(predicate, timeout: float = 8.0, what: str = "condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {what}")


@pytest.fixture
def socket_name() -> str:
    return f"hubtest-{os.getpid()}-{time.time_ns() % 1_000_000}"


@pytest.fixture
def tmux(socket_name):
    if not Tmux.available():
        pytest.skip("tmux is not installed")
    server = Tmux(socket_name, "hub")
    yield server
    server.kill_server()


@pytest.fixture
def config_path(tmp_path: Path, socket_name: str) -> Path:
    path = tmp_path / "hub.yaml"
    path.write_text(textwrap.dedent(BASE).format(
        log_dir=tmp_path / "logs", socket=socket_name, flag=tmp_path / "port.flag"),
        encoding="utf-8")
    return path


@pytest.fixture
def cfg(config_path):
    return load_config(config_path)
