"""Colour and one-line summary of each device, from its checks, its processes and recent
events. A pure function: the watcher calls it once a second."""

from __future__ import annotations

from control_hub.checks import CheckResult
from control_hub.config import HubConfig
from control_hub.session import Event

WINDOW_S = 60.0
RANK = {"bad": 2, "warn": 1}


def device_states(cfg: HubConfig, procs: dict[str, dict], checks: dict[str, CheckResult],
                  recent: list[Event], now: float) -> dict[str, dict]:
    fresh = [e for e in recent if now - e.t <= WINDOW_S and e.level in RANK]
    out: dict[str, dict] = {}
    for device in cfg.devices.values():
        causes: list[tuple[int, str]] = []
        for cid in device.checks:
            result = checks.get(cid)
            if result is None or result.ok is None:
                continue
            if result.ok is False:
                causes.append((2, f"{cfg.checks[cid].title}: {result.detail}"))
            elif result.warn:
                causes.append((1, result.warn))
        pids = (*device.processes, *device.tools)
        for pid in pids:
            if procs.get(pid, {}).get("state") == "failed":
                causes.append((2, f"{cfg.processes[pid].title} 오류"))
        mine = [e for e in fresh if e.dev == device.id]
        causes += [(RANK[e.level], e.text) for e in reversed(mine)]  # newest first
        if causes:
            rank, summary = max(causes, key=lambda c: c[0])
            level = "bad" if rank == 2 else "warn"
        else:
            summary = ""
            running = any(procs.get(pid, {}).get("state", "off") != "off" for pid in pids)
            level = "ok" if device.checks or running else "idle"
        state = {"level": level, "summary": summary,
                 "last_event": mine[-1].to_json() if mine else None}
        if device.kind == "leap":
            state["motors"] = {m: {"t": e.t, "text": e.text}
                               for e in mine for m in e.data.get("motors", [])}
        out[device.id] = state
    other = [e for e in fresh if e.dev is None]
    out["_other"] = {
        "level": max((e.level for e in other), key=RANK.get, default="ok"),
        "events": [e.to_json() for e in other[-20:]],
    }
    return out
