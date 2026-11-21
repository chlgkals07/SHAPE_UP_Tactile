from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from policy_runner.chunk import ActionChunk
from policy_runner.trace import Trace

READY, RUNNING, HOLD, FAULT = "READY", "RUNNING", "HOLD", "FAULT"
MS = 1_000_000


class ChunkSource(Protocol):
    fault: str

    def request(self, now_ns: int) -> None: ...

    def take(self, now_ns: int) -> ActionChunk | None: ...


class Command(Protocol):
    def send(self, row: np.ndarray, t_ns: int) -> None: ...


class Executor:
    def __init__(self, dt_ns: int, exec_horizon: int, chunks: ChunkSource,
                 commands: Sequence[Command], trace: Trace):
        self.dt_ns = dt_ns
        self.k = exec_horizon
        self.chunks = chunks
        self.commands = list(commands)
        self.trace = trace
        self.state = READY
        self.active: ActionChunk | None = None
        self.adopted: ActionChunk | None = None
        self.t_start_ns = 0
        self.cursor = 0
        self.last_problem = ""
        self._lock = threading.Lock()
        trace.write("config", 0, dt_ns=dt_ns, exec_horizon=exec_horizon)

    def arm(self, now_ns: int) -> None:
        with self._lock:
            if self.state == READY:
                self._enter(HOLD, now_ns, "arm")
                self.chunks.request(now_ns)

    def disarm(self, now_ns: int) -> None:
        with self._lock:
            if self.state in (RUNNING, HOLD):
                self.active = None
                self._enter(READY, now_ns, "disarm")

    def reset(self, now_ns: int) -> None:
        with self._lock:
            if self.state == FAULT:
                self._enter(READY, now_ns, "reset")

    def fail(self, now_ns: int, reason: str) -> None:
        with self._lock:
            self._fail(now_ns, reason)

    def tick(self, now_ns: int, grid_ns: int | None = None) -> None:
        grid_ns = now_ns if grid_ns is None else grid_ns
        with self._lock:
            if self.state not in (RUNNING, HOLD):
                return
            if self.chunks.fault:
                self._fail(now_ns, self.chunks.fault)
                return
            if self.active is None and not self._adopt(now_ns, grid_ns):
                self._hold(now_ns, "waiting for a chunk")
                return
            self._step(now_ns)

    def status(self, now_ns: int) -> dict:
        with self._lock:
            chunk = self.adopted
            return {
                "state": self.state,
                "problem": self.last_problem,
                "chunk": {
                    "id": chunk.chunk_id if chunk else 0,
                    "age_ms": (now_ns - chunk.t_obs_ns) / MS if chunk else None,
                    "row": self.cursor,
                    "of": self.k,
                    "active": self.active is not None,
                },
            }

    def _step(self, now_ns: int) -> None:
        assert self.active is not None
        row = (now_ns - self.t_start_ns) // self.dt_ns
        for skipped in range(self.cursor, min(row, self.k)):
            self._late(now_ns, skipped)
        if row >= self.k:
            self.active = None
            self.chunks.request(now_ns)
            self._hold(now_ns, "chunk done")
            return
        if row < self.cursor:
            return
        self.cursor = row + 1
        self._send(now_ns, self.t_start_ns + row * self.dt_ns, row)

    def _adopt(self, now_ns: int, grid_ns: int) -> bool:
        chunk = self.chunks.take(now_ns)
        if chunk is None:
            return False
        self.trace.write("chunk", now_ns, chunk_id=chunk.chunk_id, obs_id=chunk.obs_id,
                         t_obs_ns=chunk.t_obs_ns, t_reply_ns=chunk.t_reply_ns)
        self.active, self.adopted, self.t_start_ns, self.cursor = chunk, chunk, grid_ns, 0
        self._enter(RUNNING, now_ns, f"chunk {chunk.chunk_id}")
        return True

    def _send(self, now_ns: int, due_ns: int, row: int) -> None:
        assert self.active is not None
        action = self.active.actions[row]
        try:
            for command in self.commands:
                command.send(action, now_ns)
        except OSError as error:
            self._fail(now_ns, f"command failed: {error}")
            return
        self.trace.write("send", now_ns, due_ns=due_ns, chunk_id=self.active.chunk_id, row=row,
                         action=action)

    def _late(self, now_ns: int, row: int) -> None:
        assert self.active is not None
        self.trace.write("late", now_ns, due_ns=self.t_start_ns + row * self.dt_ns,
                         chunk_id=self.active.chunk_id, row=row)

    def _hold(self, now_ns: int, reason: str) -> None:
        self._enter(HOLD, now_ns, reason)
        self.trace.write("hold", now_ns)

    def _fail(self, now_ns: int, reason: str) -> None:
        self.active = None
        self.last_problem = reason
        self._enter(FAULT, now_ns, reason)

    def _enter(self, state: str, now_ns: int, reason: str) -> None:
        if state != self.state:
            self.state = state
            self.trace.write("state", now_ns, state=state, reason=reason)
