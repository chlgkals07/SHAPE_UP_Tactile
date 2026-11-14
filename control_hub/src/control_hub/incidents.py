"""One folder per error, so a field problem can be read later in one place.

    <session>/incidents/<HHMMSS>_<device>_<text>/
        summary.md     what, when, where, the hint, what was running
        meta.json      the same as data (for the list in the UI)
        checks.json    every check result and the USB list at that moment
        <pid>.log      that process: 200 lines before the error and 30 s after it
        others/*.log   every other running process: 100 lines before and 30 s after
        <tool>.txt     a check tool of that device run within 5 min after (leap_check)

The same error on the same device within 30 s only raises the count of the open folder.
"""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from collections.abc import Callable
from pathlib import Path

from control_hub.logscan import clean
from control_hub.session import Event, SessionLog

INCIDENT_PATTERN = re.compile(r"^\d{6}_[\w-]+$")
TAIL_BYTES = 256 * 1024
MAX_AFTER_BYTES = 1024 * 1024


def _slug(text: str) -> str:
    return re.sub(r"[^\w-]", "", re.sub(r"\s+", "_", text.strip()))[:30] or "error"


def _lines_before(path: Path, end: int, count: int) -> list[str]:
    try:
        with path.open("rb") as handle:
            start = max(0, end - TAIL_BYTES)
            handle.seek(start)
            data = handle.read(end - start)
    except OSError:
        return []
    lines = clean(data.decode("utf-8", "replace")).splitlines()
    if start == 0 and lines and lines[0].startswith("$ "):
        lines = lines[1:]  # the command header is not output
    return lines[-count:]


def _text_after(path: Path, start: int) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(start)
            return clean(handle.read(MAX_AFTER_BYTES).decode("utf-8", "replace"))
    except OSError:
        return ""


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _clock(t: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(t))


class Incidents:
    def __init__(self, session: SessionLog, log_path: Callable[[str, str], Path],
                 now: Callable[[], float] = time.time, group_s: float = 30.0,
                 after_s: float = 30.0, before_lines: int = 200,
                 tool_window_s: float = 300.0) -> None:
        self.session = session
        self.log_path = log_path
        self._now = now
        self.group_s = group_s
        self.after_s = after_s
        self.before_lines = before_lines
        self.tool_window_s = tool_window_s
        self._open: list[dict] = []  # incidents still taking repeats, logs or tool results

    def on_event(self, ev: Event, running: dict[str, str], checks: dict, scan: dict) -> str | None:
        if ev.level != "bad":
            return None
        sid = self.session.current
        for inc in self._open:
            if (inc["sid"] == sid and inc["dev"] == ev.dev and inc["text"] == ev.text
                    and ev.t - inc["last_t"] <= self.group_s):
                inc["count"] += 1
                inc["last_t"] = ev.t
                self._write_summary(inc)
                return inc["id"]
        base = f"{time.strftime('%H%M%S', time.localtime(ev.t))}_{ev.dev or 'other'}_" \
               f"{_slug(ev.text)}"
        root = self.session.dir() / "incidents"
        iid, n = base, 1
        while (root / iid).exists():
            n += 1
            iid = f"{base}-{n}"
        (root / iid).mkdir(parents=True)
        pid = ev.data.get("pid")
        inc = {
            "id": iid, "sid": sid, "dev": ev.dev, "text": ev.text, "t": ev.t, "last_t": ev.t,
            "count": 1, "pid": pid, "line": ev.data.get("line", ""), "hint": ev.data.get("hint"),
            "running": dict(running), "logs_done": False,
            # where each running log ended when the error came in
            "marks": {p: _size(self.log_path(p, r)) for p, r in running.items()},
        }
        if pid and pid not in running and ev.data.get("run"):
            inc["running"][pid] = ev.data["run"]
            inc["marks"][pid] = _size(self.log_path(pid, ev.data["run"]))
        (root / iid / "checks.json").write_text(
            json.dumps({"checks": checks, "scan": scan}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        self._write_summary(inc)
        self._open.append(inc)
        return iid

    def on_tool_done(self, dev: str, pid: str, run: str) -> None:
        now = self._now()
        for inc in self._open:
            if inc["dev"] == dev and now - inc["t"] <= self.tool_window_s:
                text = _text_after(self.log_path(pid, run), 0)
                self._folder(inc).joinpath(f"{pid}.txt").write_text(text, encoding="utf-8")

    def tick(self) -> None:
        now = self._now()
        for inc in self._open:
            if not inc["logs_done"] and now - inc["t"] >= self.after_s:
                self._write_logs(inc)
                inc["logs_done"] = True
        self._open = [i for i in self._open
                      if not i["logs_done"] or now - i["t"] <= self.tool_window_s]

    # ---- reading ----
    def _dir(self, sid: str, iid: str) -> Path:
        if not INCIDENT_PATTERN.match(iid):
            raise KeyError(iid)
        folder = self.session.dir(sid) / "incidents" / iid
        if not folder.is_dir():
            raise KeyError(iid)
        return folder

    def list(self, sid: str) -> list[dict]:
        root = self.session.dir(sid) / "incidents"
        if not root.is_dir():
            return []
        rows = []
        for folder in sorted(root.iterdir(), reverse=True):
            try:
                rows.append(json.loads((folder / "meta.json").read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return rows

    def read(self, sid: str, iid: str) -> dict:
        folder = self._dir(sid, iid)
        files = {str(p.relative_to(folder)): p.read_text(encoding="utf-8", errors="replace")
                 for p in sorted(folder.rglob("*")) if p.is_file() and p.name != "meta.json"}
        return {"summary": files.pop("summary.md", ""), "files": files}

    def zip(self, sid: str, iid: str | None) -> bytes:
        folder = self.session.dir(sid) if iid is None else self._dir(sid, iid)
        if not folder.is_dir():
            raise KeyError(sid)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    archive.write(path, f"{folder.name}/{path.relative_to(folder)}")
            if iid is None:  # a session export carries the process logs it refers to
                runs = folder / "runs.json"
                for run in json.loads(runs.read_text(encoding="utf-8")) if runs.exists() else []:
                    log = Path(run["log"])
                    if log.is_file():
                        archive.write(log, f"{folder.name}/logs/{run['pid']}/{log.name}")
        return buffer.getvalue()

    # ---- writing ----
    def _folder(self, inc: dict) -> Path:
        return self.session.dir(inc["sid"]) / "incidents" / inc["id"]

    def _write_summary(self, inc: dict) -> None:
        folder = self._folder(inc)
        lines = [
            f"# {inc['text']}",
            "",
            f"- 시각: {_clock(inc['t'])} ({time.strftime('%Y-%m-%d', time.localtime(inc['t']))})",
            f"- 장치: {inc['dev'] or '기타'}",
            f"- 횟수: {inc['count']} (마지막 {_clock(inc['last_t'])})",
        ]
        if inc["pid"]:
            lines.append(f"- 프로세스: {inc['pid']}")
        if inc["line"]:
            lines.append(f"- 원래 줄: `{inc['line']}`")
        if inc["hint"]:
            lines.append(f"- 힌트: {inc['hint']}")
        lines.append(f"- 그때 돌던 프로세스: {', '.join(inc['running']) or '없음'}")
        folder.joinpath("summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        meta = {k: inc[k] for k in ("id", "t", "last_t", "dev", "text", "count", "pid")}
        folder.joinpath("meta.json").write_text(json.dumps(meta, ensure_ascii=False),
                                                encoding="utf-8")

    def _write_logs(self, inc: dict) -> None:
        folder = self._folder(inc)
        for pid, run in inc["running"].items():
            path = self.log_path(pid, run)
            mark = inc["marks"].get(pid, 0)
            own = pid == inc["pid"]
            before = _lines_before(path, mark, self.before_lines if own else 100)
            text = "\n".join(before) + "\n" + _text_after(path, mark)
            target = folder / f"{pid}.log" if own else folder / "others" / f"{pid}.log"
            target.parent.mkdir(exist_ok=True)
            target.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
