"""The only file that calls tmux.

Every process is one window of one session on a private tmux server (``tmux -L <socket>``).
tmux owns the processes, so they keep running when the hub restarts or crashes, and
``tmux -L <socket> attach`` always gives the plain terminals back.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ANCHOR = "_hub"  # an idle shell window that keeps the session alive
_FORMAT = "#{window_name}\t#{window_id}\t#{pane_dead}\t#{pane_dead_status}\t#{pane_dead_signal}\t#{pane_pid}"
# Wait for the hub to attach the log pipe, then run the script: the first line is never lost.
_GATE = 'until [ -e "$1.go" ]; do sleep 0.05; done; exec bash "$1"'


class TmuxError(Exception):
    pass


@dataclass(frozen=True)
class Window:
    name: str
    id: str
    dead: bool
    exit_code: int | None  # best effort: -1 when tmux did not catch the status
    pid: int


class Tmux:
    def __init__(self, socket: str, session: str) -> None:
        self.socket = socket
        self.session = session

    # ---- plumbing ----
    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        # -f /dev/null: the user's own tmux.conf must not change how windows behave here
        cmd = ["tmux", "-L", self.socket, "-f", "/dev/null", *args]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except FileNotFoundError as exc:
            raise TmuxError("tmux 가 설치되어 있지 않습니다 (sudo apt install tmux)") from exc
        except subprocess.TimeoutExpired as exc:
            raise TmuxError(f"tmux 가 응답하지 않습니다: {' '.join(args)}") from exc
        if check and result.returncode != 0:
            raise TmuxError(f"tmux {args[0]}: {result.stderr.strip() or result.returncode}")
        return result

    @staticmethod
    def available() -> bool:
        return shutil.which("tmux") is not None

    def _has_session(self) -> bool:
        return self._run("has-session", "-t", f"={self.session}", check=False).returncode == 0

    def _ensure_session(self) -> None:
        if self._has_session():
            return
        self._run("new-session", "-d", "-s", self.session, "-n", ANCHOR, "-x", "220", "-y", "50")
        for option, value in (
            ("remain-on-exit", "on"),      # keep a finished window so its exit code can be read
            ("allow-rename", "off"),       # a program must not rename its window: names are ids
            ("automatic-rename", "off"),
            ("history-limit", "20000"),
        ):
            self._run("set-option", "-g", option, value)

    # ---- queries ----
    def windows(self) -> dict[str, Window]:
        if not self._has_session():
            return {}
        out = self._run("list-windows", "-t", f"={self.session}", "-F", _FORMAT).stdout
        windows: dict[str, Window] = {}
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) != 6 or parts[0] == ANCHOR:
                continue
            name, wid, dead, status, signal, pid = parts
            code: int | None = None
            if dead == "1":
                if status:
                    code = int(status)
                elif signal:
                    code = 128 + int(signal)
                else:
                    code = -1
            windows[name] = Window(name, wid, dead == "1", code, int(pid or 0))
        return windows

    def _window(self, name: str) -> Window:
        # Looked up by exact name and then addressed by id: tmux's own name matching accepts
        # prefixes, which would let "arm" hit "arm_stock".
        window = self.windows().get(name)
        if window is None:
            raise TmuxError(f"'{name}' 창이 없습니다")
        return window

    def attach_hint(self) -> str:
        return f"tmux -L {self.socket} attach -t {self.session}"

    # ---- actions ----
    def spawn(self, name: str, script_path: Path, log_path: Path) -> None:
        """Run ``bash script_path`` in a new window named ``name``, logging to ``log_path``."""
        self._ensure_session()
        if name in self.windows():
            raise TmuxError(f"'{name}' 창이 이미 있습니다")
        gate = Path(f"{script_path}.go")
        gate.unlink(missing_ok=True)
        command = shlex.join(["bash", "-c", _GATE, "_", str(script_path)])
        wid = self._run(
            "new-window", "-d", "-t", f"={self.session}:", "-n", name, "-P", "-F", "#{window_id}",
            command,
        ).stdout.strip()
        try:
            self._run("pipe-pane", "-t", wid, "-o", f"cat >> {shlex.quote(str(log_path))}")
        finally:
            gate.touch()

    def interrupt(self, name: str) -> None:
        self._run("send-keys", "-t", self._window(name).id, "C-c")

    def send_line(self, name: str, text: str) -> None:
        wid = self._window(name).id
        if text:
            self._run("send-keys", "-t", wid, "-l", "--", text)
        self._run("send-keys", "-t", wid, "Enter")

    def kill(self, name: str) -> None:
        self._run("kill-window", "-t", self._window(name).id)

    def kill_server(self) -> None:
        self._run("kill-server", check=False)
