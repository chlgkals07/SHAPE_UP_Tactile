from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ACTION_DIM = 22

SCHEMA = {
    "config": ["dt_ns", "exec_horizon", "chunk_max_delay_ns", "tick_jitter_ns"],
    "state": ["state", "reason"],
    "obs": ["obs_id", "t_obs_ns", "ok", "problems", "picks"],
    "request": ["obs_id"],
    "reply": ["obs_id", "ok", "problems", "rtt_ms"],
    "chunk": ["chunk_id", "obs_id", "t_obs_ns", "t_reply_ns", "adopted", "problems"],
    "send": ["due_ns", "chunk_id", "row", "action"],
    "late": ["due_ns", "chunk_id", "row"],
    "hold": [],
}


def audit(events: list[dict]) -> list[str]:
    problems: list[str] = []
    if not events or events[0].get("ev") != "config":
        return ["first event must be config"]
    cfg = events[0]
    for index, event in enumerate(events):
        missing = [k for k in ["ev", "t_ns", *SCHEMA.get(str(event.get("ev")), [])]
                   if k not in event]
        if event.get("ev") not in SCHEMA or missing:
            problems.append(f"line {index + 1}: bad event {event.get('ev')} missing {missing}")
    if problems:
        return problems

    state = "READY"
    adopted: dict[int, dict] = {}
    rows_per_chunk: dict[int, int] = {}
    last_send: dict | None = None
    faulted = False
    for index, event in enumerate(events):
        where = f"line {index + 1}"
        kind = event["ev"]
        if kind == "state":
            if faulted and event["state"] != "FAULT":
                if event["state"] == "READY" and event["reason"] == "reset":
                    faulted = False
                else:
                    problems.append(f"{where}: left FAULT to {event['state']} without reset")
            state = event["state"]
            faulted = faulted or state == "FAULT"
        elif kind == "obs":
            for name, pick in event["picks"].items():
                if pick["t_ns"] > event["t_obs_ns"]:
                    problems.append(f"{where}: obs {event['obs_id']} used {name} from the future")
        elif kind == "chunk" and event["adopted"]:
            adopted[event["chunk_id"]] = event
            if event["t_ns"] - event["t_obs_ns"] > cfg["chunk_max_delay_ns"]:
                problems.append(f"{where}: chunk {event['chunk_id']} adopted too late")
        elif kind == "send":
            action = event["action"]
            if len(action) != ACTION_DIM or not all(math.isfinite(v) for v in action):
                problems.append(f"{where}: send action is not {ACTION_DIM} finite values")
            if state != "RUNNING":
                problems.append(f"{where}: send while {state}")
            if faulted:
                problems.append(f"{where}: send after FAULT")
            chunk = adopted.get(event["chunk_id"])
            if chunk is None:
                problems.append(f"{where}: send from chunk {event['chunk_id']} never adopted")
            if not 0 <= event["row"] < cfg["exec_horizon"]:
                problems.append(f"{where}: row {event['row']} outside 0..K-1")
            rows_per_chunk[event["chunk_id"]] = rows_per_chunk.get(event["chunk_id"], 0) + 1
            if rows_per_chunk[event["chunk_id"]] > cfg["exec_horizon"]:
                problems.append(f"{where}: chunk {event['chunk_id']} sent more than K rows")
            if event["t_ns"] - event["due_ns"] > cfg["tick_jitter_ns"]:
                problems.append(f"{where}: sent {event['t_ns'] - event['due_ns']} ns late")
            if (last_send is not None
                    and event["t_ns"] - last_send["t_ns"] < cfg["dt_ns"] - cfg["tick_jitter_ns"]):
                problems.append(f"{where}: two sends closer than dt")
            last_send = event
    return problems


def main(argv: list[str]) -> int:
    path = Path(argv[1])
    events = [json.loads(line) for line in path.read_text().splitlines() if line]
    problems = audit(events)
    for problem in problems:
        print(problem)
    print(f"{path}: {len(events)} events, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
