"""Terminal UI: the same Recorder as the web UI, driven by single keys. For debugging and for
PCs where a browser is not convenient."""

from __future__ import annotations

import select
import sys
import termios
import time
import tty

from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text

from tactile_rec.hub import Hub
from tactile_rec.record.session import IDLE, RECORDING, REVIEW, Recorder, RecorderError

STATE_TEXT = {IDLE: "대기", RECORDING: "● 녹화 중", REVIEW: "검토"}
STATE_STYLE = {IDLE: "bold", RECORDING: "bold red", REVIEW: "bold yellow"}
STATUS_STYLE = {"ok": "green", "slow": "yellow", "stale": "red", "error": "red", "off": "dim"}
KEYS = {
    IDLE: "[Space] 시작   [!] 문제 무시하고 시작   [z] 촉각 영점   [q] 종료",
    RECORDING: "[Space] 정지   [m] 표시   [d] 중단하고 버리기",
    REVIEW: "[s] 성공 저장   [f] 실패 저장   [d] 버리고 다시 찍기",
}


def render(hub: Hub, recorder: Recorder, message: str) -> Group:
    status = recorder.status()
    counts = status["counts"]
    head = Text.assemble(
        ("태스크 ", "dim"), (status["task"], "bold"), f'  "{status["text"]}"   ',
        ("세션 ", "dim"), status["session"] or "(첫 녹화 때 생성)", "   ",
        ("저장 ", "dim"), f'{counts["success"] + counts["failure"]} '
        f'(성공 {counts["success"]} / 실패 {counts["failure"]})',
    )
    line = Text.assemble(
        (STATE_TEXT[status["state"]], STATE_STYLE[status["state"]]),
        f'   ep_{status["episode"]:04d}' if status["state"] != IDLE else "",
        f'   {status["elapsed_s"]:6.1f} s',
    )
    table = Table(box=None, pad_edge=False, header_style="dim")
    for column, justify in (("스트림", "left"), ("Hz (기대)", "right"), ("마지막 수신", "right"),
                            ("빠짐", "right"), ("상태", "left")):
        table.add_column(column, justify=justify)
    for name, health in hub.health().items():
        spec = hub.streams[name].spec
        age = "-" if health.age_s is None else (
            f"{health.age_s * 1000:.0f} ms" if health.age_s < 1 else f"{health.age_s:.1f} s"
        )
        note = health.status + ("" if spec.required else " (선택)")
        if health.message:
            note += f"  {health.message}"
        table.add_row(
            name, f"{health.hz:.0f} ({spec.nominal_hz:.0f})", age, str(health.missed),
            Text(note, style=STATUS_STYLE.get(health.status, "")),
        )
    parts: list = [head, line, Text(""), table, Text("")]
    if status["state"] == IDLE:
        parts += [Text(f"· {problem}", style="yellow") for problem in recorder.preflight()]
    if status["state"] == REVIEW and status["summary"]:
        flags = status["summary"]["flags"]
        for name, count in flags["dropouts"].items():
            parts.append(Text(f"주의: {name} 끊김 {count}회", style="red"))
    if message:
        parts.append(Text(message, style="cyan"))
    parts.append(Text(KEYS[status["state"]], style="dim"))
    return Group(*parts)


def _read_key(timeout_s: float) -> str:
    ready, _, _ = select.select([sys.stdin], [], [], timeout_s)
    return sys.stdin.read(1) if ready else ""


def run(hub: Hub, recorder: Recorder) -> None:
    if not sys.stdin.isatty():
        raise RuntimeError("the terminal UI needs an interactive terminal (try --ui web)")
    console = Console()
    message = ""
    saved = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        with Live(render(hub, recorder, message), console=console, refresh_per_second=8,
                  screen=False) as live:
            while True:
                key = _read_key(0.1).lower()
                recorder.tick()
                try:
                    state = recorder.state
                    if key == "q" and state == IDLE:
                        return
                    if key == " " and state == IDLE:
                        recorder.start()
                        message = ""
                    elif key == "!" and state == IDLE:
                        recorder.start(force=True)
                        message = "점검 실패를 무시하고 시작했습니다"
                    elif key == " " and state == RECORDING:
                        recorder.stop()
                    elif key == "m" and state == RECORDING:
                        recorder.mark()
                        message = "표시를 남겼습니다"
                    elif key == "d" and state in (RECORDING, REVIEW):
                        recorder.discard()
                        message = "버렸습니다"
                    elif key in ("s", "f") and state == REVIEW:
                        path = recorder.save(key == "s")
                        message = f"저장: {path}"
                    elif key == "z" and state == IDLE:
                        message = f"촉각 영점 보정 요청: {recorder.zero_tactile() or '보드 없음'}"
                    if key in (" ", "!", "s", "f", "d"):
                        console.bell()
                except RecorderError as error:
                    message = " / ".join(error.problems)
                live.update(render(hub, recorder, message))
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, saved)
        if recorder.state == RECORDING:
            recorder.discard()
        time.sleep(0)
