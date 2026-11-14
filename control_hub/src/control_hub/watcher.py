"""Once a second, look at everything and write down what changed.

Runs in the background whether or not a browser is open: the session log and the incident
folders must not depend on someone watching the page.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from control_hub.checks import CheckResult, CheckRunner
from control_hub.config import HubConfig
from control_hub.devices import device_states
from control_hub.discovery import scan
from control_hub.incidents import Incidents
from control_hub.leapcheck import parse_leap_check
from control_hub.logscan import read_chunk
from control_hub.session import Event, SessionLog
from control_hub.supervisor import Supervisor

ALIVE = ("starting", "ready", "stopping")
TOOL_TAIL_LINES = 30


class Watcher:
    def __init__(self, cfg: HubConfig, supervisor: Supervisor, runner: CheckRunner,
                 session: SessionLog, incidents: Incidents,
                 scan_fn: Callable[[HubConfig, dict[str, CheckResult]], dict] = scan,
                 interval_s: float = 1.0, now: Callable[[], float] = time.time) -> None:
        self.cfg = cfg
        self.supervisor = supervisor
        self.runner = runner
        self.session = session
        self.incidents = incidents
        self.scan_fn = scan_fn
        self.interval_s = interval_s
        self._now = now
        self._checks: dict[str, CheckResult] = {}
        self._procs: dict[str, str] | None = None  # None: not looked yet
        self._usb: dict[tuple, str] | None = None
        self._tool_results: dict[str, dict] = {}  # device id -> last check tool result
        self._snapshot: dict = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def reload(self, cfg: HubConfig) -> None:
        with self._lock:
            self.cfg = cfg

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot

    # ---- one look ----
    def _device_of(self, ref: str) -> str | None:
        for device in self.cfg.devices.values():
            if ref in (*device.checks, *device.processes, *device.tools):
                return device.id
        return None

    def _title(self, ref: str) -> str:
        item = self.cfg.processes.get(ref) or self.cfg.checks.get(ref)
        return item.title if item is not None else ref

    def _check_events(self, checks: dict[str, CheckResult], now: float) -> list[Event]:
        out = []
        for cid, result in checks.items():
            if result.ok is None:
                continue
            prev = self._checks.get(cid)
            self._checks[cid] = result
            if prev is None:
                continue
            title, dev = self._title(cid), self._device_of(cid)
            if prev.ok and not result.ok:
                out.append(Event(now, dev, "check", "bad", f"{title} 없음: {result.detail}",
                                 {"check": cid}))
            elif not prev.ok and result.ok:
                out.append(Event(now, dev, "check", "info", f"{title} 다시 잡힘", {"check": cid}))
            if result.ok and result.warn and result.warn != prev.warn:
                out.append(Event(now, dev, "check", "warn", f"{title}: {result.warn}",
                                 {"check": cid}))
        return out

    def _process_events(self, procs: dict[str, dict], now: float) -> list[Event]:
        before, self._procs = self._procs, {pid: info["state"] for pid, info in procs.items()}
        if before is None:
            return []
        out = []
        for pid, info in procs.items():
            state, prev = info["state"], before.get(pid, "off")
            if state == prev:
                continue
            title, dev = self._title(pid), self._device_of(pid)
            data = {"pid": pid, "run": info.get("run")}
            if prev not in ALIVE and state != "off" and info.get("run"):
                self.session.note_run(pid, info["run"],
                                      self.supervisor.log_path(pid, info["run"]))
            if state == "starting":
                out.append(Event(now, dev, "process", "info", f"{title} 켜짐", data))
            elif state == "ready":
                out.append(Event(now, dev, "process", "info", f"{title} 준비됨", data))
            elif state == "failed":
                code = info.get("exit_code")
                out.append(Event(now, dev, "process", "bad",
                                 f"{title} 오류 (종료 코드 {code})", data))
            elif state == "done":
                out.append(Event(now, dev, "process", "info", f"{title} 끝남", data))
            if state in ("done", "failed") and info.get("run"):
                self._tool_finished(pid, info, now)
        return out

    def _tool_finished(self, pid: str, info: dict, now: float) -> None:
        devices = [d for d in self.cfg.devices.values() if pid in d.tools]
        if not devices:
            return
        _, text = read_chunk(self.supervisor.log_path(pid, info["run"]), 0)
        for device in devices:
            self.incidents.on_tool_done(device.id, pid, info["run"])
            self._tool_results[device.id] = {
                "pid": pid, "run": info["run"], "t": now, "state": info["state"],
                "exit_code": info.get("exit_code"),
                "tail": "\n".join(text.splitlines()[-TOOL_TAIL_LINES:]),
                "table": parse_leap_check(text) if device.kind == "leap" else None,
            }

    def _log_events(self, procs: dict[str, dict]) -> list[Event]:
        out = []
        for pid, found in self.supervisor.drain_events().items():
            dev = self._device_of(pid)
            for e in found:
                out.append(Event(e.t, dev, "log", e.level, e.text, {
                    "pid": pid, "run": procs.get(pid, {}).get("run"), "offset": e.offset,
                    "motors": list(e.motors), "count": e.count, "line": e.line,
                    "hint": e.hint}))
        return out

    def _usb_events(self, found: dict, now: float) -> list[Event]:
        current = {(d["usb_id"], d.get("serial", ""), d["bus_path"]):
                   f"{d.get('label') or d.get('product') or d['usb_id']} ({d['bus_path']})"
                   for d in found.get("devices", [])}
        before, self._usb = self._usb, current
        if before is None:
            return []
        added = [Event(now, None, "check", "info", f"USB 연결: {name}", {})
                 for key, name in current.items() if key not in before]
        removed = [Event(now, None, "check", "info", f"USB 빠짐: {name}", {})
                   for key, name in before.items() if key not in current]
        return added + removed

    def step(self) -> None:
        with self._lock:
            cfg = self.cfg
        now = self._now()
        procs = self.supervisor.status()
        checks = self.runner.results()
        found = self.scan_fn(cfg, checks)
        events = [*self._check_events(checks, now), *self._process_events(procs, now),
                  *self._log_events(procs), *self._usb_events(found, now)]
        running = {pid: info["run"] for pid, info in procs.items()
                   if info["state"] in ALIVE and info.get("run")}
        checks_json = {cid: r.to_json() for cid, r in checks.items()}
        for event in events:
            self.session.add(event)
            self.incidents.on_event(event, running, checks_json, found)
        self.incidents.tick()
        devices = device_states(cfg, procs, checks, self.session.recent(), now)
        for dev, result in self._tool_results.items():
            if dev in devices:
                devices[dev]["check"] = result
        with self._lock:
            self._snapshot = {"devices": devices, "scan": found, "session": self.session.current}

    # ---- thread ----
    def start(self) -> None:
        if self._thread is not None:
            return

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    self.step()
                except Exception as exc:  # noqa: BLE001 - keep watching; say what broke
                    print(f"[control-hub] watcher: {type(exc).__name__}: {exc}", flush=True)
                self._stop.wait(self.interval_s)

        self._thread = threading.Thread(target=loop, name="watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
