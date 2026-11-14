"""Start, stop and report on the processes. All rules live here: what must be up first, what
cannot run together, what needs a confirmation.

The supervisor holds almost no state of its own. What is running is whatever tmux says is
running; what it was started with is in ``<log_dir>/<id>/current.json``. A restarted hub
therefore picks up exactly where the old one left off.
"""

from __future__ import annotations

import json
import re
import shlex
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from control_hub.checks import CheckResult
from control_hub.command import build_command
from control_hub.config import ID_PATTERN, HubConfig, Process
from control_hub.logscan import LogScanner, read_chunk
from control_hub.tmux import Tmux, TmuxError, Window

RUN_PATTERN = re.compile(r"^\d{8}-\d{6}(-\d+)?$")
KEEP_RUNS = 30
STATE_LABEL = {
    "off": "꺼짐", "starting": "켜는 중", "ready": "준비됨", "stopping": "끄는 중",
    "done": "끝남", "failed": "오류",
}


class HubError(Exception):
    """A refusal the person at the screen should read."""


@dataclass
class Run:
    run: str
    command: str
    flags: list[str]
    started_at: float
    stop_requested_at: float | None = None
    scanner: LogScanner | None = field(default=None, repr=False)

    def to_json(self) -> dict[str, Any]:
        return {"run": self.run, "command": self.command, "flags": self.flags,
                "started_at": self.started_at, "stop_requested_at": self.stop_requested_at}


class Supervisor:
    def __init__(self, cfg: HubConfig, tmux: Tmux,
                 checks: Callable[[], dict[str, CheckResult]] = dict) -> None:
        self.cfg = cfg
        self.tmux = tmux
        self._checks = checks
        self._runs: dict[str, Run] = {}
        self._lock = threading.RLock()
        for name in self.tmux.windows():  # adopt what is already running
            self._load_run(name)

    # ---- files ----
    def _dir(self, pid: str) -> Path:
        return self.cfg.log_dir / pid

    def _log_path(self, pid: str, run: str) -> Path:
        return self._dir(pid) / f"{run}.log"

    def _exit_path(self, pid: str, run: str) -> Path:
        return self._dir(pid) / f"{run}.exit"

    def _exit_code(self, pid: str, run: Run | None, window: Window) -> int | None:
        if not window.dead:
            return None
        if run is not None and run.run:
            try:
                return int(self._exit_path(pid, run.run).read_text().strip())
            except (OSError, ValueError):
                pass
        return window.exit_code

    def _scanner(self, pid: str, run: str) -> LogScanner:
        proc = self.cfg.processes.get(pid)
        ready = proc.ready.log if proc is not None and proc.ready is not None else None
        hints = [*(proc.hints if proc is not None else ()), *self.cfg.hints]
        return LogScanner(self._log_path(pid, run), ready, hints)

    def _load_run(self, pid: str) -> Run | None:
        try:
            data = json.loads((self._dir(pid) / "current.json").read_text(encoding="utf-8"))
            run = Run(data["run"], data["command"], list(data["flags"]), float(data["started_at"]),
                      data.get("stop_requested_at"))
        except (OSError, ValueError, KeyError, TypeError):
            return None
        run.scanner = self._scanner(pid, run.run)
        self._runs[pid] = run
        return run

    def _save_run(self, pid: str, run: Run) -> None:
        path = self._dir(pid) / "current.json"
        path.write_text(json.dumps(run.to_json(), ensure_ascii=False), encoding="utf-8")

    def _forget(self, pid: str) -> None:
        self._runs.pop(pid, None)
        (self._dir(pid) / "current.json").unlink(missing_ok=True)

    def _prune(self, pid: str) -> None:
        for old in sorted(self._dir(pid).glob("*.log"), reverse=True)[KEEP_RUNS:]:
            for path in (old, old.with_suffix(".sh"), old.with_suffix(".exit"),
                         Path(f"{old.with_suffix('.sh')}.go")):
                path.unlink(missing_ok=True)

    # ---- config ----
    def reload(self, cfg: HubConfig) -> None:
        with self._lock:
            self.cfg = cfg
            for pid, run in self._runs.items():  # hints and ready patterns may have changed
                run.scanner = self._scanner(pid, run.run)

    # ---- status ----
    def _base_state(self, pid: str, window: Window | None,
                    checks: dict[str, CheckResult]) -> dict[str, Any]:
        proc = self.cfg.processes.get(pid)
        run = self._runs.get(pid)
        if window is None:
            if run is not None:
                self._forget(pid)  # the window was closed from a terminal
            return {"state": "off"}
        if run is None:
            run = self._load_run(pid)
        code = self._exit_code(pid, run, window)
        info: dict[str, Any] = {"exit_code": code}
        if run is not None:
            if run.scanner is not None:
                run.scanner.poll()
                info["issues"] = list(run.scanner.issues)
                info["last_line"] = run.scanner.last_line
            info.update(run=run.run, command=run.command, flags=run.flags,
                        started_at=run.started_at)
        if window.dead:
            if run is not None and run.stop_requested_at is not None:
                self._close(pid)  # it stopped because we asked: nothing left to show
                return {"state": "off"}
            kind = proc.kind if proc is not None else "service"
            info["state"] = "done" if kind == "tool" and code == 0 else "failed"
            return info
        if run is not None and run.stop_requested_at is not None:
            grace = proc.stop_grace_s if proc is not None else 10.0
            info["state"] = "stopping"
            info["stop_overdue"] = time.time() - run.stop_requested_at > grace
            return info
        ready = True
        if proc is not None and proc.ready is not None:
            if proc.ready.log is not None:
                ready = bool(run and run.scanner and run.scanner.ready_seen)
            else:
                result = checks.get(proc.ready.check or "")
                ready = bool(result and result.ok)
        info["state"] = "ready" if ready else "starting"
        return info

    def _close(self, pid: str) -> None:
        try:
            self.tmux.kill(pid)
        except TmuxError:
            pass
        self._forget(pid)

    def _title(self, ref: str) -> str:
        if ref in self.cfg.processes:
            return self.cfg.processes[ref].title
        if ref in self.cfg.checks:
            return self.cfg.checks[ref].title
        return ref

    def _blockers(self, proc: Process, states: dict[str, dict[str, Any]],
                  checks: dict[str, CheckResult]) -> list[str]:
        out = []
        for ref in proc.requires:
            if ref in self.cfg.processes:
                state = states.get(ref, {}).get("state", "off")
                if state != "ready":
                    out.append(f"먼저 필요: {self._title(ref)} ({STATE_LABEL[state]})")
            else:
                result = checks.get(ref)
                if result is None or result.ok is None:
                    out.append(f"먼저 필요: {self._title(ref)} (확인 중)")
                elif not result.ok:
                    out.append(f"먼저 필요: {self._title(ref)} ({result.detail or '실패'})")
        for ref in proc.conflicts:
            if states.get(ref, {}).get("state") in ("starting", "ready", "stopping"):
                out.append(f"같이 켤 수 없음: {self._title(ref)} 이(가) 켜져 있음")
        return out

    def status(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            windows = self.tmux.windows()
            checks = self._checks()
            ids = list(self.cfg.processes) + [w for w in windows if w not in self.cfg.processes]
            states = {pid: self._base_state(pid, windows.get(pid), checks) for pid in ids}
            alive = ("starting", "ready", "stopping")
            for pid, info in states.items():
                proc = self.cfg.processes.get(pid)
                info.setdefault("issues", [])
                info["orphan"] = proc is None
                info["blockers"] = (
                    self._blockers(proc, states, checks)
                    if proc is not None and info["state"] not in alive else []
                )
                info["dependents"] = [
                    other.id for other in self.cfg.processes.values()
                    if pid in other.requires and states[other.id]["state"] in alive
                ]
                info["stale_config"] = bool(
                    proc is not None and info["state"] in alive and "command" in info
                    and build_command(self.cfg, proc, info["flags"]) != info["command"]
                )
            return states

    # ---- actions ----
    def _proc(self, pid: str) -> Process:
        proc = self.cfg.processes.get(pid)
        if proc is None:
            raise KeyError(pid)
        return proc

    def start(self, pid: str, flags: Iterable[str] | None = None, confirmed: bool = False) -> None:
        with self._lock:
            proc = self._proc(pid)
            known = {f.id for f in proc.flags}
            chosen = [f.id for f in proc.flags if f.default] if flags is None else list(flags)
            unknown = sorted(set(chosen) - known)
            if unknown:
                raise HubError(f"없는 옵션입니다: {', '.join(unknown)}")
            chosen = [f.id for f in proc.flags if f.id in set(chosen)]
            states = self.status()
            state = states[pid]["state"]
            if state in ("starting", "ready", "stopping"):
                raise HubError(f"{proc.title}: 이미 켜져 있습니다 ({STATE_LABEL[state]})")
            if states[pid]["blockers"]:
                raise HubError(f"{proc.title}: " + " / ".join(states[pid]["blockers"]))
            needed = [c for c in proc.confirm_start if c.unless_flag not in chosen]
            if needed and not confirmed:
                raise HubError(f"{proc.title}: 켜기 전 확인이 필요합니다")
            if state in ("done", "failed"):
                self._close(pid)

            self._dir(pid).mkdir(parents=True, exist_ok=True)
            self._prune(pid)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            run_id, n = stamp, 1
            while self._log_path(pid, run_id).exists():
                n += 1
                run_id = f"{stamp}-{n}"
            command = build_command(self.cfg, proc, chosen)
            script = self._dir(pid) / f"{run_id}.sh"
            script.write_text(
                "#!/bin/bash\n"
                f"# control-hub: {pid} ({proc.title}) {run_id}\n"
                # tmux does not always report the status of a process that ends at once
                f"trap 'echo $? > {shlex.quote(str(self._exit_path(pid, run_id)))}' EXIT\n"
                f"printf '%s\\n' {shlex.quote('$ ' + command)}\n"
                f"{command}\n",
                encoding="utf-8",
            )
            run = Run(run_id, command, chosen, time.time())
            run.scanner = self._scanner(pid, run_id)
            self._runs[pid] = run
            self._save_run(pid, run)
            try:
                self.tmux.spawn(pid, script, self._log_path(pid, run_id))
            except TmuxError as exc:
                self._forget(pid)
                raise HubError(f"{proc.title}: 창을 만들지 못했습니다 ({exc})") from exc

    def _alive_window(self, pid: str, action: str) -> None:
        window = self.tmux.windows().get(pid)
        if window is None or window.dead:
            raise HubError(f"{self._title(pid)}: 켜져 있지 않아 {action} 수 없습니다")

    def stop(self, pid: str, confirmed: bool = False) -> None:
        """Ctrl+C. Never escalates on its own: ``kill`` is a separate, deliberate action."""
        with self._lock:
            self._known(pid)
            self._alive_window(pid, "끌")
            proc = self.cfg.processes.get(pid)
            dependents = self.status()[pid]["dependents"]
            if not confirmed and ((proc is not None and proc.confirm_stop) or dependents):
                raise HubError(f"{self._title(pid)}: 끄기 전 확인이 필요합니다")
            run = self._runs.get(pid) or Run("", "", [], time.time())
            if run.stop_requested_at is None:
                run.stop_requested_at = time.time()
                self._runs[pid] = run
                if run.run:
                    self._save_run(pid, run)
            try:
                self.tmux.interrupt(pid)
            except TmuxError as exc:
                raise HubError(str(exc)) from exc

    def kill(self, pid: str) -> None:
        with self._lock:
            self._known(pid)
            if pid not in self.tmux.windows():
                raise HubError(f"{self._title(pid)}: 켜져 있지 않습니다")
            self._close(pid)

    def clear(self, pid: str) -> None:
        with self._lock:
            self._known(pid)
            window = self.tmux.windows().get(pid)
            if window is None:
                return
            if not window.dead:
                raise HubError(f"{self._title(pid)}: 아직 돌고 있습니다. 먼저 끕니다")
            self._close(pid)

    def send_input(self, pid: str, text: str) -> None:
        with self._lock:
            proc = self._proc(pid)
            if not proc.input:
                raise HubError(f"{proc.title}: 입력을 받지 않는 프로세스입니다")
            self._alive_window(pid, "입력을 보낼")
            line = text.replace("\r", " ").replace("\n", " ")[:500]
            try:
                self.tmux.send_line(pid, line)
            except TmuxError as exc:
                raise HubError(str(exc)) from exc

    # ---- logs ----
    def _known(self, pid: str) -> None:
        if pid in self.cfg.processes:
            return
        if ID_PATTERN.match(pid) and (pid in self._runs or pid in self.tmux.windows()):
            return  # running, but no longer in the config: still visible and stoppable
        raise KeyError(pid)

    def runs(self, pid: str) -> list[str]:
        if not ID_PATTERN.match(pid):
            raise KeyError(pid)
        return sorted((p.stem for p in self._dir(pid).glob("*.log")), reverse=True)[:KEEP_RUNS]

    def read_log(self, pid: str, offset: int = 0, run: str | None = None) -> dict[str, Any]:
        if not ID_PATTERN.match(pid):
            raise KeyError(pid)
        if run is None:
            current = self._runs.get(pid)
            run = current.run if current is not None and current.run else None
            if run is None:
                past = self.runs(pid)
                run = past[0] if past else None
        if run is None or not RUN_PATTERN.match(run):
            return {"run": None, "offset": 0, "text": ""}
        new_offset, text = read_chunk(self._log_path(pid, run), offset)
        return {"run": run, "offset": new_offset, "text": text}
