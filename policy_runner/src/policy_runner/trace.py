from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


def plain(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"cannot write {type(value).__name__} to the trace")


class Trace:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, ev: str, t_ns: int, **fields: Any) -> None:
        line = json.dumps({"ev": ev, "t_ns": int(t_ns), **fields}, default=plain)
        with self._lock:
            if not self._file.closed:
                self._file.write(line + "\n")
                self._file.flush()

    def close(self) -> None:
        with self._lock:
            self._file.close()
