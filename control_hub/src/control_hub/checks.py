"""Small yes/no probes of the rig: is the robot reachable, is the port open, is the device
plugged in. They run in the background every few seconds; the UI only reads the last result.
"""

from __future__ import annotations

import glob
import os
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from control_hub.config import Check, Host, HubConfig
from control_hub.sysfs import DEV, SYS, tty_info, usb_devices

PING_RTT = re.compile(r"= [\d.]+/([\d.]+)/")  # "rtt min/avg/max/mdev = 0.1/0.2/0.3/0.0 ms"


@dataclass(frozen=True)
class CheckResult:
    ok: bool | None  # None: not looked at yet
    detail: str = ""
    checked_at: float = 0.0
    info: dict = field(default_factory=dict)  # details shown on the device page
    warn: str = ""  # works, but something will bite (slow USB, latency timer)

    def to_json(self) -> dict:
        return {"ok": self.ok, "detail": self.detail, "checked_at": self.checked_at,
                "info": self.info, "warn": self.warn}


def _sh(args: list[str] | str, timeout: float, shell: bool = False) -> tuple[int, str]:
    try:
        result = subprocess.run(args, shell=shell, capture_output=True, text=True, timeout=timeout,
                                stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return 124, f"{timeout:g}초 안에 응답 없음"
    except FileNotFoundError:
        name = args if isinstance(args, str) else args[0]
        return 127, f"{name} 명령이 없습니다"
    lines = [ln for ln in (result.stdout + result.stderr).strip().splitlines() if ln.strip()]
    return result.returncode, lines[-1].strip()[:200] if lines else ""


def _ping(target: str) -> tuple[bool, str, dict]:
    code, out = _sh(["ping", "-c", "1", "-W", "1", target], 3)
    if code != 0:
        return False, out or "응답 없음", {}
    match = PING_RTT.search(out)
    if match is None:
        return True, "응답 있음", {}
    ms = float(match.group(1))
    return True, f"{ms:g} ms", {"ms": ms}


def _tcp(target: str) -> tuple[bool, str]:
    host, _, port = target.rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=1.5):
            return True, "열림"
    except OSError as exc:
        return False, exc.strerror or str(exc)


def _file(target: str) -> tuple[bool, str]:
    matches = sorted(glob.glob(os.path.expanduser(target)))
    return bool(matches), ", ".join(matches[:4]) if matches else "없음"


def _http(target: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(target, timeout=1.5) as response:  # noqa: S310 - config URL
            return True, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return True, f"HTTP {exc.code}"  # the server answered: it is up
    except (urllib.error.URLError, OSError) as exc:
        return False, str(getattr(exc, "reason", exc))


def _ssh(host: Host) -> tuple[bool, str]:
    code, out = _sh(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=2", *host.ssh_options, host.ssh,
         "true"], 4)
    return code == 0, "접속됨" if code == 0 else (out or "접속 실패")


def _serial(target: str, sys_root: Path, dev_root: Path) -> tuple[bool, str, dict, str]:
    matches = sorted(glob.glob(os.path.expanduser(target)))
    if not matches:
        return False, "없음", {}, ""
    path = matches[0]
    tty = Path(path).name
    found = tty_info(tty, sys_root, dev_root)
    usb = found["usb"]
    info = {"path": path, "tty": tty, "by_id": found["by_id"],
            "latency_timer": found["latency_timer"],
            "serial": usb.serial if usb else "", "usb_id": usb.usb_id if usb else "",
            "rw": os.access(path, os.R_OK | os.W_OK)}
    if not info["rw"]:
        return False, f"{path}: 권한 없음 (dialout 그룹)", info, ""
    warn = ""
    latency = found["latency_timer"]
    if latency is not None and latency != 1:
        warn = (f"latency timer {latency} (1 이어야 빠름). "
                "USB 를 다시 꽂으면 16 으로 돌아갑니다")
    return True, path, info, warn


def _usb(check: Check, sys_root: Path, dev_root: Path) -> tuple[bool, str, dict, str]:
    usb = next((d for d in usb_devices(sys_root, dev_root) if d.usb_id == check.target), None)
    if usb is None:
        return False, "꽂혀 있지 않음", {}, ""
    info = {"speed_mbps": usb.speed_mbps, "serial": usb.serial, "product": usb.product,
            "bus_path": usb.bus_path}
    warn = ""
    if check.warn_below_mbps and usb.speed_mbps is not None \
            and usb.speed_mbps < check.warn_below_mbps:
        warn = f"USB {usb.speed_mbps} Mbps 로 잡힘 (USB3 포트에 꽂기)"
    return True, usb.product or check.target, info, warn


def _process(target: str) -> tuple[bool, str]:
    code, out = _sh(["pgrep", "-a", "-f", target], 3)
    return code == 0, out if code == 0 else "실행 중이 아님"


def run_check(check: Check, hosts: dict[str, Host], sys_root: Path = SYS,
              dev_root: Path = DEV) -> CheckResult:
    info: dict = {}
    warn = ""
    try:
        if check.kind == "ping":
            ok, detail, info = _ping(check.target)
        elif check.kind == "tcp":
            ok, detail = _tcp(check.target)
        elif check.kind == "file":
            ok, detail = _file(check.target)
        elif check.kind == "http":
            ok, detail = _http(check.target)
        elif check.kind == "ssh":
            ok, detail = _ssh(hosts[check.target])
        elif check.kind == "usb":
            ok, detail, info, warn = _usb(check, sys_root, dev_root)
        elif check.kind == "serial":
            ok, detail, info, warn = _serial(check.target, sys_root, dev_root)
        elif check.kind == "process":
            ok, detail = _process(check.target)
        elif check.kind == "no_process":
            found, detail = _process(check.target)
            ok, detail = not found, f"실행 중: {detail}" if found else "꺼져 있음"
        else:  # command
            code, detail = _sh(check.target, 3, shell=True)
            ok = code == 0
    except Exception as exc:  # noqa: BLE001 - a probe must never take the hub down
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return CheckResult(ok, detail, time.time(), info, warn)


class CheckRunner:
    def __init__(self, cfg: HubConfig) -> None:
        self._cfg = cfg
        self._results: dict[str, CheckResult] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def reload(self, cfg: HubConfig) -> None:
        with self._lock:
            self._cfg = cfg
            self._results = {k: v for k, v in self._results.items() if k in cfg.checks}

    def results(self) -> dict[str, CheckResult]:
        with self._lock:
            return {cid: self._results.get(cid, CheckResult(None)) for cid in self._cfg.checks}

    def run_once(self) -> None:
        with self._lock:
            cfg = self._cfg
        if not cfg.checks:
            return
        with ThreadPoolExecutor(max_workers=min(8, len(cfg.checks))) as pool:
            done = dict(zip(cfg.checks, pool.map(lambda c: run_check(c, cfg.hosts),
                                                 cfg.checks.values()), strict=True))
        with self._lock:
            self._results.update({k: v for k, v in done.items() if k in self._cfg.checks})

    def start(self) -> None:
        if self._thread is not None:
            return

        def loop() -> None:
            while not self._stop.is_set():
                self.run_once()
                self._stop.wait(self._cfg.check_interval_s)

        self._thread = threading.Thread(target=loop, name="checks", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
