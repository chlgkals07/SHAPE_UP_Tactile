from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "audit"))
from audit_trace import audit  # noqa: E402

MS = 1_000_000
DT = 33_333_333
ROW = [0.0] * 22


def good_trace() -> list[dict]:
    events = [
        {"ev": "config", "t_ns": 0, "dt_ns": DT, "exec_horizon": 3,
         "chunk_max_delay_ns": 500 * MS, "tick_jitter_ns": 10 * MS},
        {"ev": "state", "t_ns": 0, "state": "HOLD", "reason": "arm"},
        {"ev": "obs", "t_ns": 0, "obs_id": 1, "t_obs_ns": 0, "ok": True, "problems": [],
         "picks": {"arm_state": {"seq": 1, "t_ns": -2 * MS, "age_ns": 2 * MS}}},
        {"ev": "request", "t_ns": 0, "obs_id": 1},
        {"ev": "reply", "t_ns": 90 * MS, "obs_id": 1, "ok": True, "problems": [], "rtt_ms": 90},
        {"ev": "hold", "t_ns": 0},
        {"ev": "chunk", "t_ns": 4 * DT, "chunk_id": 1, "obs_id": 1, "t_obs_ns": 0,
         "t_reply_ns": 90 * MS, "adopted": True, "problems": []},
        {"ev": "state", "t_ns": 4 * DT, "state": "RUNNING", "reason": "chunk 1"},
    ]
    for row in range(3):
        t = (4 + row) * DT
        events.append({"ev": "send", "t_ns": t, "due_ns": t, "chunk_id": 1, "row": row,
                       "action": [0.01 * row] * 22})
    events.append({"ev": "state", "t_ns": 7 * DT, "state": "HOLD", "reason": "chunk done"})
    return events


def index_of(events, kind, nth=0):
    return [i for i, e in enumerate(events) if e["ev"] == kind][nth]


def test_good_trace_passes():
    assert audit(good_trace()) == []


def broken(change):
    events = copy.deepcopy(good_trace())
    change(events)
    return audit(events)


def set_send(events, nth, **values):
    events[index_of(events, "send", nth)].update(values)


VIOLATIONS = {
    "nan action": lambda e: set_send(e, 1, action=[float("nan")] * 22),
    "short action": lambda e: set_send(e, 1, action=[0.0] * 21),
    "chunk never adopted": lambda e: set_send(e, 0, chunk_id=9),
    "adopted too late": lambda e: e[index_of(e, "chunk")].update(t_ns=600 * MS),
    "future pick": lambda e: e[index_of(e, "obs")]["picks"]["arm_state"].update(t_ns=5 * MS),
    "sends closer than dt": lambda e: set_send(e, 1, t_ns=4 * DT + MS, due_ns=4 * DT + MS),
    "sent late": lambda e: set_send(e, 2, t_ns=6 * DT + 20 * MS),
    "send while hold": lambda e: e.insert(index_of(e, "send", 2),
                                          {"ev": "state", "t_ns": 6 * DT, "state": "HOLD",
                                           "reason": "x"}),
    "row outside K": lambda e: set_send(e, 2, row=3),
    "more than K rows": lambda e: e.insert(index_of(e, "send", 2) + 1,
                                           {"ev": "send", "t_ns": 7 * DT, "due_ns": 7 * DT,
                                            "chunk_id": 1, "row": 0, "action": ROW}),
    "send after fault": lambda e: e.insert(index_of(e, "send", 1),
                                           {"ev": "state", "t_ns": 5 * DT - 1, "state": "FAULT",
                                            "reason": "server"}),
    "fault left without reset": lambda e: e.extend([
        {"ev": "state", "t_ns": 8 * DT, "state": "FAULT", "reason": "server"},
        {"ev": "state", "t_ns": 9 * DT, "state": "HOLD", "reason": "arm"},
    ]),
    "missing config": lambda e: e.pop(0),
    "unknown event": lambda e: e.append({"ev": "teleport", "t_ns": 0}),
    "missing field": lambda e: e[index_of(e, "send")].pop("due_ns"),
}


@pytest.mark.parametrize("name", list(VIOLATIONS))
def test_each_violation_is_caught(name):
    assert broken(VIOLATIONS[name]), name


def test_reset_after_fault_is_allowed():
    def change(events):
        events.extend([
            {"ev": "state", "t_ns": 8 * DT, "state": "FAULT", "reason": "server"},
            {"ev": "state", "t_ns": 9 * DT, "state": "READY", "reason": "reset"},
            {"ev": "state", "t_ns": 10 * DT, "state": "HOLD", "reason": "arm"},
        ])
    assert broken(change) == []
