from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from tactile_rec.clock import FakeClock

from policy_runner.chunk import ActionChunk
from policy_runner.executor import Executor, Limits
from policy_runner.trace import Trace

from conftest import RecordingCommand, SimulatedInference, read_trace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "audit"))
from audit_trace import audit  # noqa: E402

MS = 1_000_000
DT = round(1e9 / 30)
STATE = np.linspace(-0.5, 0.5, 22).astype(np.float32)


def limits(**overrides) -> Limits:
    values = {"chunk_max_delay_ns": 500 * MS, "tick_jitter_ns": 10 * MS,
              "first_row_max_rad": 0.15, "step_max_rad": 0.05}
    values.update(overrides)
    return Limits(**values)


class Bench:
    def __init__(self, tmp_path, k=10, latency_ms=150, **limit_overrides):
        self.clock = FakeClock(start_ns=100 * 10**9)
        self.measured = STATE.copy()
        self.chunks = SimulatedInference(self.clock, latency_ms * MS, lambda: self.measured)
        self.command = RecordingCommand()
        self.trace_path = tmp_path / "trace.jsonl"
        self.trace = Trace(self.trace_path)
        self.executor = Executor(DT, k, limits(**limit_overrides), self.chunks,
                                 lambda: self.measured, [self.command], self.trace)
        self.t0 = self.clock.now_ns()
        self.ticks = 0

    def now(self) -> int:
        return self.clock.now_ns()

    def step(self, n=1):
        for _ in range(n):
            self.clock.set_ns(self.t0 + self.ticks * DT)
            self.executor.tick(self.now())
            self.ticks += 1

    def events(self):
        self.trace.close()
        return read_trace(self.trace_path)


def test_nothing_is_sent_before_arm(tmp_path):
    bench = Bench(tmp_path)
    bench.step(30)
    assert bench.executor.state == "READY"
    assert bench.command.rows == []
    assert bench.chunks.requests == []


def test_rows_go_out_one_per_dt_from_adoption(tmp_path):
    bench = Bench(tmp_path, k=10, latency_ms=150)
    bench.executor.arm(bench.now())
    bench.step(15)
    times = [t for t, _ in bench.command.rows]
    assert len(times) == 10
    assert np.all(np.diff(times) == DT)
    assert times[0] == bench.t0 + math.ceil(150 * MS / DT) * DT
    assert audit(bench.events()) == []


def test_at_most_k_rows_per_chunk_then_a_new_request(tmp_path):
    bench = Bench(tmp_path, k=4, latency_ms=50)
    bench.executor.arm(bench.now())
    bench.step(7)
    assert len(bench.command.rows) == 4
    assert len(bench.chunks.requests) == 2
    assert bench.executor.state == "HOLD"


def test_executor_does_not_catch_up(tmp_path):
    bench = Bench(tmp_path, k=10, latency_ms=30)
    bench.executor.arm(bench.now())
    bench.step(3)
    sent_before = len(bench.command.rows)
    bench.ticks += 4
    bench.step(1)
    assert len(bench.command.rows) == sent_before + 1
    events = bench.events()
    assert sum(e["ev"] == "late" for e in events) == 4
    assert audit(events) == []


def test_hold_while_waiting_for_a_chunk(tmp_path):
    bench = Bench(tmp_path, k=10, latency_ms=300)
    bench.executor.arm(bench.now())
    bench.step(5)
    assert bench.executor.state == "HOLD"
    assert bench.command.rows == []


def test_stale_chunk_is_discarded(tmp_path):
    bench = Bench(tmp_path, k=10, latency_ms=600)
    bench.executor.arm(bench.now())
    bench.step(25)
    assert bench.command.rows == []
    adopted = [e for e in bench.events() if e["ev"] == "chunk"]
    assert adopted and not adopted[0]["adopted"]
    assert len(bench.chunks.requests) >= 2


def test_first_row_far_from_state_is_rejected(tmp_path):
    bench = Bench(tmp_path, k=10, latency_ms=50)
    bench.chunks.measured = lambda: STATE + 0.3
    bench.executor.arm(bench.now())
    bench.step(5)
    assert bench.command.rows == []
    assert bench.executor.state == "HOLD"


def test_large_step_inside_a_chunk_is_rejected(tmp_path):
    bench = Bench(tmp_path, k=10, latency_ms=50)

    def jumpy():
        rows = np.tile(STATE, (50, 1))
        rows[3:] += 0.1
        return rows

    original = bench.chunks.take

    def take(now_ns):
        chunk = original(now_ns)
        if chunk is None:
            return None
        return ActionChunk(chunk.chunk_id, chunk.obs_id, chunk.t_obs_ns, chunk.t_reply_ns,
                           jumpy().astype(np.float32))

    bench.chunks.take = take
    bench.executor.arm(bench.now())
    bench.step(5)
    assert bench.command.rows == []


def test_fault_needs_explicit_reset(tmp_path):
    bench = Bench(tmp_path, k=10, latency_ms=30)
    bench.executor.arm(bench.now())
    bench.step(3)
    bench.chunks.fault = "server error"
    bench.step(1)
    assert bench.executor.state == "FAULT"
    sent = len(bench.command.rows)
    bench.chunks.fault = ""
    bench.step(10)
    assert bench.executor.state == "FAULT"
    assert len(bench.command.rows) == sent
    bench.executor.reset(bench.now())
    assert bench.executor.state == "READY"
    bench.executor.arm(bench.now())
    bench.step(5)
    assert len(bench.command.rows) > sent
    assert audit(bench.events()) == []


def test_disarm_stops_commands(tmp_path):
    bench = Bench(tmp_path, k=10, latency_ms=30)
    bench.executor.arm(bench.now())
    bench.step(4)
    bench.executor.disarm(bench.now())
    sent = len(bench.command.rows)
    bench.step(10)
    assert bench.executor.state == "READY"
    assert len(bench.command.rows) == sent


def expected(k: int, latency_ms: int, ticks: int):
    wait = math.ceil(latency_ms * MS / DT)
    cycle = wait + k
    rows = k * (ticks // cycle) + max(0, ticks % cycle - wait)
    chunks = ticks // cycle + (1 if ticks % cycle > wait else 0)
    return rows, chunks, ticks - rows


@pytest.mark.parametrize("k", [10, 25])
@pytest.mark.parametrize("latency_ms", [150, 280, 990])
def test_sixty_seconds_match_the_cycle_formula(tmp_path, k, latency_ms):
    bench = Bench(tmp_path, k=k, latency_ms=latency_ms, chunk_max_delay_ns=2000 * MS)
    ticks = int(60 * 10**9 // DT)
    bench.executor.arm(bench.now())
    bench.step(ticks)
    events = bench.events()
    rows, chunks, holds = expected(k, latency_ms, ticks)
    assert len(bench.command.rows) == rows
    assert sum(e["ev"] == "chunk" and e["adopted"] for e in events) == chunks
    assert sum(e["ev"] == "hold" for e in events) == holds
    assert audit(events) == []
