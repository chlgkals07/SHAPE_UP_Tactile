from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from control_hub.command import build_command, script_for
from control_hub.config import ConfigError, load_config

EXAMPLES = Path(__file__).parent.parent / "config"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "hub.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_and_links(cfg):
    assert set(cfg.processes) >= {"server", "client", "rival"}
    assert cfg.processes["server"].conflicts == ("rival",)  # declared on rival only
    assert cfg.processes["client"].confirm_start[1].unless_flag == "dry"
    assert cfg.checks["port"].kind == "file"
    assert cfg.profiles[0].steps[0].note == "전원을 켠다"
    assert cfg.profiles[0].steps[1].process == "server"
    assert cfg.chains[0].items == ("port", "server", "client")


@pytest.mark.parametrize(
    ("text", "where"),
    [
        ("processes: {a: {cmd: x, colour: red}}", "processes.a"),
        ("processes: {a: {title: x}}", "processes.a.cmd"),
        ("processes: {a: {cmd: x, requires: [nope]}}", "processes.a.requires"),
        ("processes: {a: {cmd: x, conflicts: [nope]}}", "processes.a.conflicts"),
        ("processes: {a: {cmd: x, env: nope}}", "processes.a.env"),
        ("processes: {a: {cmd: x, host: nope}}", "processes.a.host"),
        ("processes: {a: {cmd: x, kind: daemon}}", "processes.a.kind"),
        ("processes: {a: {cmd: x, ready: {log: '('}}}", "processes.a.ready.log"),
        ("processes: {a: {cmd: x, ready: {check: nope}}}", "processes.a.ready.check"),
        ("processes: {Bad-Id: {cmd: x}}", "processes.Bad-Id"),
        ("processes: {a: {cmd: x, confirm_start: [{text: t, unless_flag: nope}]}}", "processes.a"),
        ("checks: {c: {title: x}}", "checks.c"),
        ("checks: {c: {ping: a, file: b}}", "checks.c"),
        ("checks: {c: {tcp: nohostport}}", "checks.c.tcp"),
        ("processes: {a: {cmd: x}}\nprofiles: [{id: p, steps: [nope]}]", "profiles[0].steps[0]"),
        ("processes: {a: {cmd: x}}\nchains: [{id: c, items: [nope]}]", "chains[0].items"),
        ("procesess: {}", "최상위"),
        ("hints: [{match: x}]", "hints[0]"),
        ("processes: [1, 2", "YAML"),
    ],
)
def test_errors_name_the_place(tmp_path, text, where):
    with pytest.raises(ConfigError) as err:
        load_config(write(tmp_path, text))
    assert where in str(err.value)


def test_repo_substitution(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "sub").mkdir()
    path = tmp_path / "sub" / "hub.yaml"
    path.write_text("processes: {a: {cmd: 'ls {repo}/x'}}", encoding="utf-8")
    assert load_config(path).processes["a"].cmd == f"ls {tmp_path}/x"
    path.write_text("repo: /opt/r\nprocesses: {a: {cmd: 'ls {repo}/x'}}", encoding="utf-8")
    assert load_config(path).processes["a"].cmd == "ls /opt/r/x"


def test_script_and_flags(cfg):
    client = cfg.processes["client"]
    assert script_for(cfg, client, []) == "sleep 60"
    assert script_for(cfg, client, ["dry"]) == "sleep 60 # dry"
    assert script_for(cfg, cfg.processes["server"], []).startswith("export GREETING=hello && ")


def test_quoting_survives_every_layer(tmp_path):
    cmd = """printf '%s|%s\\n' "a b" 'it'"'"'s' "$HOME" """.strip()
    path = write(tmp_path, yaml.safe_dump({
        "hosts": {"r": {"ssh": "root@h"}, "rc": {"ssh": "root@h", "container": "box"}},
        "processes": {
            "local": {"cmd": cmd},
            "remote": {"cmd": cmd, "host": "r"},
            "inside": {"cmd": cmd, "host": "rc"},
        },
    }))
    cfg = load_config(path)
    expected = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True).stdout
    assert expected.startswith("a b|it's")

    def run(line: str) -> str:
        return subprocess.run(["bash", "-c", line], capture_output=True, text=True).stdout

    assert run(build_command(cfg, cfg.processes["local"])) == expected

    remote = build_command(cfg, cfg.processes["remote"])
    assert remote.startswith("ssh -tt -o ConnectTimeout=5 ")
    # ssh hands its last argument to the remote shell; stand in for it with bash -c
    stub = tmp_path / "ssh"
    stub.write_text('#!/bin/bash\nexec bash -c "${@: -1}"\n')
    stub.chmod(0o755)
    docker = tmp_path / "docker"
    docker.write_text('#!/bin/bash\nshift 3\nexec "$@"\n')  # drop: exec -it <container>
    docker.chmod(0o755)
    env_path = f'PATH={tmp_path}:"$PATH" '
    assert run(env_path + remote) == expected
    inside = build_command(cfg, cfg.processes["inside"])
    assert "docker exec -it box bash -c" in inside
    assert run(env_path + inside) == expected


def test_shipped_configs_load():
    for name in ("hub.example.yaml", "hub.fake.yaml"):
        cfg = load_config(EXAMPLES / name)
        assert cfg.processes and cfg.profiles and cfg.chains
        for proc in cfg.processes.values():
            assert build_command(cfg, proc, [f.id for f in proc.flags])
