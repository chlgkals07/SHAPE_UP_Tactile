"""Colour and one-line summary of each device, from its checks, its processes and recent
events. A pure function: the watcher calls it once a second."""

from __future__ import annotations

from control_hub.checks import CheckResult
from control_hub.config import HubConfig
from control_hub.logscan import STREAM_LEVEL, stream_text
from control_hub.session import Event

WINDOW_S = 60.0
RANK = {"bad": 2, "warn": 1}


def device_states(cfg: HubConfig, procs: dict[str, dict], checks: dict[str, CheckResult],
                  recent: list[Event], now: float) -> dict[str, dict]:
    fresh = [e for e in recent if now - e.t <= WINDOW_S and e.level in RANK]
    out: dict[str, dict] = {}
    for device in cfg.devices.values():
        # events first: on a tie the log line (the cause) wins over "process failed" (the exit)
        mine = [e for e in fresh if e.dev == device.id]
        causes: list[tuple[int, str]] = [(RANK[e.level], e.text) for e in reversed(mine)]
        for cid in device.checks:
            result = checks.get(cid)
            if result is None or result.ok is None:
                continue
            if result.ok is False:
                causes.append((2, f"{cfg.checks[cid].title}: {result.detail}"))
            elif result.warn:
                causes.append((1, result.warn))
        # What a running recorder last said about this device's streams. Unlike an event
        # this does not fade: the device stays marked until the recorder says "ok".
        for info in procs.values():
            if info.get("state") not in ("starting", "ready"):
                continue
            for name in device.recorder_stream:
                said = info.get("streams", {}).get(name)
                if said is not None and said["status"] != "ok":
                    rank = 2 if STREAM_LEVEL.get(said["status"]) == "bad" else 1
                    causes.append((rank, stream_text(name, said["status"], said["message"])))
        pids = (*device.processes, *device.tools)
        for pid in pids:
            if procs.get(pid, {}).get("state") == "failed":
                causes.append((2, f"{cfg.processes[pid].title} 오류"))
        if causes:
            rank, summary = max(causes, key=lambda c: c[0])
            level = "bad" if rank == 2 else "warn"
        else:
            summary = ""
            running = any(procs.get(pid, {}).get("state", "off") != "off" for pid in pids)
            level = "ok" if device.checks or running else "idle"
        state = {"level": level, "summary": summary}
        if device.kind == "leap":
            state["motors"] = {m: {"t": e.t, "text": e.text}
                               for e in mine for m in e.data.get("motors", [])}
        out[device.id] = state
    return out
