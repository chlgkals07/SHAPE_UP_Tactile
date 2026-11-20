from __future__ import annotations

import threading

import numpy as np


class DryRunCommand:
    def __init__(self):
        self.count = 0
        self.last: list[float] | None = None
        self._lock = threading.Lock()

    def send(self, row: np.ndarray, t_ns: int) -> None:
        with self._lock:
            self.count += 1
            self.last = [round(float(v), 4) for v in row]

    def status(self) -> dict:
        with self._lock:
            return {"sent": self.count, "last": self.last}

    def close(self) -> None:
        pass
