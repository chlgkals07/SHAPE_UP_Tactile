"""Find and stop what a remote process left running on its host after the ssh link died.

When the network to the Robot PC drops, the ssh in the tmux window dies and the hub shows the
process as failed, but inside the container the launch keeps running (field 2026-11-17).
Nothing on the hub side can reach it any more, and starting it again would run two copies.

Every remote command exports ``CONTROL_HUB_ID=<process id>`` first (see command.py). Each
child inherits it, so the whole tree can be found later by reading ``/proc/*/environ``. A
command line would not do: bash replaces itself with the last command of ``a && b``, so the
script text is gone from the process list.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from control_hub.config import LOCAL, HubConfig, Host

TAG = "CONTROL_HUB_ID"
SSH_OPTIONS = ("-o", "BatchMode=yes", "-o", "ConnectTimeout=3")
SIGNALS = ("INT", "TERM", "KILL")

# Runs on the far side (python3 is in the container). Reads {"ids": [...], "signal": ...} on
# stdin, signals every tagged process when asked, and prints what is still tagged.
PROBE = r"""
import json, os, signal, sys
ask = json.load(sys.stdin)
ids = set(ask["ids"])
sig = getattr(signal, "SIG" + ask["signal"]) if ask.get("signal") else None
found = {}
for name in os.listdir("/proc"):
    if not name.isdigit() or int(name) == os.getpid():
        continue
    try:
        with open(f"/proc/{name}/environ", "rb") as f:
            env = f.read().split(b"\0")
        with open(f"/proc/{name}/cmdline", "rb") as f:
            cmd = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
    except OSError:
        continue
    for item in env:
        if item.startswith(b"CONTROL_HUB_ID="):
            pid_id = item.split(b"=", 1)[1].decode(errors="replace")
            if pid_id in ids and cmd:
                found.setdefault(pid_id, []).append([int(name), cmd[:200]])
            break
if sig is not None and ask.get("target") in found:
    for pid, _ in found[ask["target"]]:
        try:
            os.kill(pid, sig)
        except OSError:
            pass
print(json.dumps(found))
"""


def tag_line(pid: str) -> str:
    return f"export {TAG}={shlex.quote(pid)}"


def probe_command(host: Host) -> list[str]:
    """argv that runs PROBE on the host (inside its container if it has one)."""
    inner = f"python3 -c {shlex.quote(PROBE)}"
    if host.container:
        inner = f"docker exec -i {shlex.quote(host.container)} {inner}"
    return ["ssh", *SSH_OPTIONS, *host.ssh_options, host.ssh, inner]


def run_probe(argv: list[str], ids: list[str], signal: str | None = None,
              target: str | None = None, timeout: float = 8.0) -> dict[str, list[list[Any]]]:
    """Tagged processes per id. Raises OSError / subprocess errors / ValueError on failure."""
    ask = json.dumps({"ids": ids, "signal": signal, "target": target})
    done = subprocess.run(argv, input=ask, capture_output=True, text=True, timeout=timeout,
                          check=False)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise OSError(detail[-1] if detail else f"exit {done.returncode}")
    found = json.loads(done.stdout.strip().splitlines()[-1])
    return {k: v for k, v in found.items() if isinstance(v, list)}


@dataclass
class HostReport:
    checked_at: float = 0.0
    error: str | None = None
    found: dict[str, list[list[Any]]] = field(default_factory=dict)


class RemoteWatcher:
    """Asks each host every few seconds which configured processes are still running there."""

    def __init__(self, cfg: HubConfig, interval_s: float = 5.0, runner=run_probe) -> None:
        self.cfg = cfg
        self.interval_s = interval_s
        self._run = runner
        self._reports: dict[str, HostReport] = {}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _ids(self, host: str) -> list[str]:
        return [p.id for p in self.cfg.processes.values() if p.host == host]

    def hosts(self) -> list[str]:
        return [h for h in self.cfg.hosts if h != LOCAL and self._ids(h)]

    def reload(self, cfg: HubConfig) -> None:
        self.cfg = cfg
        self._wake.set()

    def refresh(self) -> None:
        """Ask again soon (after a stop, so the screen catches up)."""
        self._wake.set()

    def check(self, host: str) -> HostReport:
        report = HostReport(checked_at=time.time())
        try:
            report.found = self._run(probe_command(self.cfg.hosts[host]), self._ids(host))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            report.error = str(exc) or type(exc).__name__
        with self._lock:
            self._reports[host] = report
        return report

    def signal(self, host: str, pid: str, signal: str) -> int:
        """Send `signal` to every process tagged `pid` on `host`. Returns how many were signalled."""
        if signal not in SIGNALS:
            raise ValueError(signal)
        found = self._run(probe_command(self.cfg.hosts[host]), self._ids(host), signal, pid)
        with self._lock:
            self._reports[host] = HostReport(checked_at=time.time(), found=found)
        self._wake.set()
        return len(found.get(pid, []))

    def report(self, host: str) -> HostReport | None:
        with self._lock:
            return self._reports.get(host)

    # ---- thread ----
    def start(self) -> None:
        if self._thread is None and self.hosts():
            self._thread = threading.Thread(target=self._loop, name="remote-watch", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            for host in self.hosts():
                self.check(host)
            self._wake.wait(self.interval_s)
            self._wake.clear()
