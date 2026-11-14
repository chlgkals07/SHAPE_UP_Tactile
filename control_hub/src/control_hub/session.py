"""One bring-up = one session folder: every change the hub noticed, in order, on disk.

    <session_dir>/<YYYY-MM-DD_HHMMSS>/events.jsonl   one event per line
                                     runs.json      which process runs (and logs) belong here
                                     incidents/     one folder per error (incidents.py)
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

SESSION_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}(-\d+)?$")
RECENT = 500


@dataclass(frozen=True)
class Event:
    t: float
    dev: str | None  # device id; None = not tied to a device ("기타")
    source: str  # check | process | log
    level: str  # info | warn | bad
    text: str
    data: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)


class SessionLog:
    def __init__(self, root: Path, keep: int = 30, now: Callable[[], float] = time.time) -> None:
        self.root = root
        self.keep = keep
        self._now = now
        self._lock = threading.Lock()
        self._recent: deque[Event] = deque(maxlen=RECENT)
        self.current = ""
        self.new_session()

    def dir(self, sid: str | None = None) -> Path:
        sid = self.current if sid is None else sid
        if not SESSION_PATTERN.match(sid):
            raise KeyError(sid)
        return self.root / sid

    def new_session(self) -> str:
        with self._lock:
            base = time.strftime("%Y-%m-%d_%H%M%S", time.localtime(self._now()))
            sid, n = base, 1
            while (self.root / sid).exists():
                n += 1
                sid = f"{base}-{n}"
            (self.root / sid).mkdir(parents=True)
            self.current = sid
            self._recent.clear()
            older = [i for i in self._ids() if i != sid]
            for old in older:  # a hub start where nothing happened leaves an empty folder
                if not any((self.root / old).iterdir()):
                    (self.root / old).rmdir()
            for old in self._ids()[self.keep:]:
                shutil.rmtree(self.root / old, ignore_errors=True)
            return sid

    def add(self, event: Event) -> None:
        with self._lock:
            self._recent.append(event)
            with (self.dir() / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.to_json(), ensure_ascii=False) + "\n")

    def recent(self) -> list[Event]:
        with self._lock:
            return list(self._recent)

    def note_run(self, pid: str, run: str, log_path: Path) -> None:
        with self._lock:
            path = self.dir() / "runs.json"
            runs = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            runs.append({"pid": pid, "run": run, "log": str(log_path)})
            path.write_text(json.dumps(runs, ensure_ascii=False), encoding="utf-8")

    def _ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        # newest first: the timestamp sorts as text, "-2" suffixes after their base
        return sorted((p.name for p in self.root.iterdir()
                       if p.is_dir() and SESSION_PATTERN.match(p.name)), reverse=True)

    def sessions(self) -> list[dict]:
        out = []
        for sid in self._ids():
            events = self.root / sid / "events.jsonl"
            incidents = self.root / sid / "incidents"
            out.append({
                "id": sid,
                "events": sum(1 for _ in events.open(encoding="utf-8")) if events.exists() else 0,
                "incidents": len(list(incidents.iterdir())) if incidents.is_dir() else 0,
            })
        return out

    def read_events(self, sid: str) -> list[dict]:
        path = self.dir(sid) / "events.jsonl"
        if not path.parent.is_dir():
            raise KeyError(sid)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
