from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from policy_runner.chunk import ActionChunk
from policy_runner.trace import Trace

READY, RUNNING, HOLD, FAULT = "READY", "RUNNING", "HOLD", "FAULT"
MS = 1_000_000


@dataclass(frozen=True)
class Limits:
    chunk_max_delay_ns: int
    tick_jitter_ns: int
    first_row_max_rad: float
    step_max_rad: float


class ChunkSource(Protocol):
    fault: str

    def request(self, now_ns: int) -> None: ...

    def take(self, now_ns: int) -> ActionChunk | None: ...


class Command(Protocol):
    def send(self, row: np.ndarray, t_ns: int) -> None: ...


class Executor:
    def __init__(self, dt_ns: int, exec_horizon: int, limits: Limits, chunks: ChunkSource,
                 measured: Callable[[], np.ndarray | None], commands: Sequence[Command],
                 trace: Trace):
        self.dt_ns = dt_ns
        self.k = exec_horizon
        self.limits = limits
        self.chunks = chunks
        self.measured = measured
        self.commands = list(commands)
        self.trace = trace
        self.state = READY
        self.active: ActionChunk | None = None
        self.t_start_ns = 0
        self.cursor = 0
        self.last_problem = ""
        self._lock = threading.Lock()
        trace.write("config", 0, dt_ns=dt_ns, exec_horizon=exec_horizon,
                    chunk_max_delay_ns=limits.chunk_max_delay_ns,
                    tick_jitter_ns=limits.tick_jitter_ns,
                    first_row_max_rad=limits.first_row_max_rad,
                    step_max_rad=limits.step_max_rad)

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

    def tick(self, now_ns: int) -> None:
        with self._lock:
            if self.state not in (RUNNING, HOLD):
                return
            if self.chunks.fault:
                self._fail(now_ns, self.chunks.fault)
                return
            if self.active is None and not self._adopt(now_ns):
                self._hold(now_ns, "waiting for a chunk")
                return
            self._step(now_ns)

    def status(self, now_ns: int) -> dict:
        with self._lock:
            chunk = self.active
            return {
                "state": self.state,
                "problem": self.last_problem,
                "chunk": {
                    "id": chunk.chunk_id if chunk else 0,
                    "age_ms": (now_ns - chunk.t_obs_ns) / MS if chunk else None,
                    "row": self.cursor if chunk else 0,
                    "of": self.k,
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
        due_ns = self.t_start_ns + row * self.dt_ns
        if now_ns - due_ns > self.limits.tick_jitter_ns:
            self._late(now_ns, row)
            return
        self._send(now_ns, due_ns, row)

    def _adopt(self, now_ns: int) -> bool:
        chunk = self.chunks.take(now_ns)
        if chunk is None:
            return False
        measured = self.measured()
        problems = self._problems(chunk, now_ns, measured)
        self.trace.write("chunk", now_ns, chunk_id=chunk.chunk_id, obs_id=chunk.obs_id,
                         t_obs_ns=chunk.t_obs_ns, t_reply_ns=chunk.t_reply_ns,
                         adopted=not problems, problems=problems, row0=chunk.actions[0],
                         measured=measured)
        if problems:
            self.last_problem = problems[0]
            self.chunks.request(now_ns)
            return False
        self.active, self.t_start_ns, self.cursor = chunk, now_ns, 0
        self._enter(RUNNING, now_ns, f"chunk {chunk.chunk_id}")
        return True

    def _problems(self, chunk: ActionChunk, now_ns: int,
                  measured: np.ndarray | None) -> list[str]:
        problems = []
        age_ns = now_ns - chunk.t_obs_ns
        if age_ns > self.limits.chunk_max_delay_ns:
            problems.append(f"chunk {chunk.chunk_id} is {age_ns / MS:.0f} ms old "
                            f"(limit {self.limits.chunk_max_delay_ns / MS:.0f})")
        rows = chunk.actions[: self.k]
        if measured is None:
            problems.append("no measured state to compare the first row with")
        else:
            gap = float(np.max(np.abs(rows[0] - measured)))
            if gap > self.limits.first_row_max_rad:
                problems.append(f"first row is {gap:.3f} rad from the measured state "
                                f"(limit {self.limits.first_row_max_rad})")
        if len(rows) > 1:
            step = float(np.max(np.abs(np.diff(rows, axis=0))))
            if step > self.limits.step_max_rad:
                problems.append(f"rows step {step:.3f} rad (limit {self.limits.step_max_rad})")
        return problems

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
