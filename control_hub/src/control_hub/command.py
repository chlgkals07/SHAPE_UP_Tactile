"""Turn a process from the config into the one shell line its tmux window runs.

The only place that knows how "run this on the Robot PC, inside the container" is spelled.
"""

from __future__ import annotations

import shlex
from collections.abc import Iterable

from control_hub.config import LOCAL, HubConfig, Process

SSH_OPTIONS = (
    "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3",
)


def script_for(cfg: HubConfig, proc: Process, flags: Iterable[str] = ()) -> str:
    """Environment lines, then the command with the chosen flags. A failing line stops the rest."""
    chosen = set(flags)
    command = proc.cmd
    for flag in proc.flags:  # config order, not click order
        if flag.id in chosen:
            command += " " + flag.arg
    lines = list(cfg.envs.get(proc.env, ())) if proc.env else []
    return " && ".join([*lines, command])


def build_command(cfg: HubConfig, proc: Process, flags: Iterable[str] = ()) -> str:
    script = script_for(cfg, proc, flags)
    if proc.host == LOCAL:
        return f"bash -c {shlex.quote(script)}"
    host = cfg.hosts[proc.host]
    remote = script
    if host.container:
        # -it: the container side needs a terminal so that Ctrl+C reaches the process
        remote = f"docker exec -it {shlex.quote(host.container)} bash -c {shlex.quote(script)}"
    options = " ".join(shlex.quote(o) for o in (*SSH_OPTIONS, *host.ssh_options))
    # -tt: a terminal on the far side, so Ctrl+C in the window stops the remote process
    return f"ssh -tt {options} {shlex.quote(host.ssh)} {shlex.quote(remote)}"
