"""Read and validate the hub YAML. Everything the hub can run is described here and nowhere
else: a command changes by editing the file, never the code.

Errors name the place in the file (``processes.arm.requires``) so a typo is found at once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
LOCAL = "local"
PROCESS_KINDS = ("service", "tool")
CHECK_KINDS = (
    "ping", "tcp", "file", "http", "ssh", "usb", "process", "no_process", "command",
)
DEVICE_KINDS = ("generic", "leap")
EVENT_LEVELS = ("info", "warn", "bad")


class ConfigError(Exception):
    """The config file is wrong. The message says where."""


@dataclass(frozen=True)
class Host:
    name: str
    ssh: str
    container: str | None = None
    ssh_options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Flag:
    id: str
    label: str
    arg: str
    default: bool = False


@dataclass(frozen=True)
class Confirm:
    text: str
    unless_flag: str | None = None  # not asked while this flag is on (e.g. dry-run)


@dataclass(frozen=True)
class Hint:
    pattern: re.Pattern[str]
    text: str
    ignore: bool = False  # a known, harmless line: never reported as a problem


@dataclass(frozen=True)
class Ready:
    log: re.Pattern[str] | None = None
    check: str | None = None


@dataclass(frozen=True)
class Process:
    id: str
    title: str
    group: str
    kind: str
    host: str
    env: str | None
    cmd: str
    flags: tuple[Flag, ...] = ()
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    ready: Ready | None = None
    confirm_start: tuple[Confirm, ...] = ()
    confirm_stop: tuple[Confirm, ...] = ()
    input: bool = False
    stop_grace_s: float = 10.0
    help: str = ""
    hints: tuple[Hint, ...] = ()


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    kind: str
    target: str
    help: str = ""
    link: str = ""


@dataclass(frozen=True)
class Step:
    note: str | None = None
    process: str | None = None


@dataclass(frozen=True)
class Profile:
    id: str
    title: str
    steps: tuple[Step, ...]
    help: str = ""


@dataclass(frozen=True)
class EventRule:
    """A log line that means something happened to a device. Named groups fill ``text``."""

    pattern: re.Pattern[str]
    level: str
    text: str


@dataclass(frozen=True)
class Device:
    id: str
    title: str
    kind: str = "generic"
    recorder_stream: tuple[str, ...] = ()  # where this device meets the recorder later
    checks: tuple[str, ...] = ()
    processes: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    events: tuple[EventRule, ...] = ()
    usb_id: str = ""  # "vvvv:pppp": lets discovery say "it seems to be on another port"
    help: str = ""


@dataclass(frozen=True)
class HubConfig:
    path: Path
    repo: Path
    hosts: dict[str, Host]
    envs: dict[str, tuple[str, ...]]
    processes: dict[str, Process]
    checks: dict[str, Check]
    profiles: tuple[Profile, ...]
    devices: dict[str, Device]
    hints: tuple[Hint, ...]
    known_usb: dict[str, str]  # "vvvv:pppp" -> label shown in discovery
    ui_host: str = "127.0.0.1"
    ui_port: int = 8700
    tmux_socket: str = "shapeup"
    tmux_session: str = "hub"
    log_dir: Path = Path("~/.local/state/control_hub/logs")
    check_interval_s: float = 3.0
    session_dir: Path = Path("~/.local/state/control_hub/sessions")
    keep_sessions: int = 30


def _fail(where: str, message: str) -> ConfigError:
    return ConfigError(f"{where}: {message}")


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _fail(where, "키: 값 형태여야 합니다")
    return value


def _strings(value: Any, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise _fail(where, "문자열 목록이어야 합니다")
    return tuple(value)


def _known_keys(data: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise _fail(where, f"모르는 키 {', '.join(unknown)} "
                           f"(쓸 수 있는 키: {', '.join(sorted(allowed))})")


def _check_id(value: str, where: str) -> None:
    if not isinstance(value, str) or not ID_PATTERN.match(value):
        raise _fail(where, f"id '{value}' 는 영문 소문자, 숫자, 밑줄만 쓸 수 있습니다")


def _regex(value: Any, where: str) -> re.Pattern[str]:
    if not isinstance(value, str):
        raise _fail(where, "정규식 문자열이어야 합니다")
    try:
        return re.compile(value)
    except re.error as exc:
        raise _fail(where, f"정규식이 틀렸습니다 ({exc})") from exc


def _hints(value: Any, where: str) -> tuple[Hint, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _fail(where, "목록이어야 합니다")
    out = []
    for i, item in enumerate(value):
        item = _mapping(item, f"{where}[{i}]")
        _known_keys(item, {"match", "hint", "ignore"}, f"{where}[{i}]")
        ignore = bool(item.get("ignore", False))
        if "match" not in item or ("hint" not in item and not ignore):
            raise _fail(f"{where}[{i}]", "match 와 hint (또는 ignore: true) 가 있어야 합니다")
        out.append(Hint(_regex(item["match"], f"{where}[{i}].match"),
                        str(item.get("hint", "")), ignore))
    return tuple(out)


def _confirms(value: Any, where: str) -> tuple[Confirm, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _fail(where, "목록이어야 합니다")
    out = []
    for i, item in enumerate(value):
        if isinstance(item, str):
            out.append(Confirm(item))
            continue
        item = _mapping(item, f"{where}[{i}]")
        _known_keys(item, {"text", "unless_flag"}, f"{where}[{i}]")
        if "text" not in item:
            raise _fail(f"{where}[{i}]", "text 가 없습니다")
        out.append(Confirm(str(item["text"]), item.get("unless_flag")))
    return tuple(out)


def _find_repo(config_path: Path) -> Path:
    for parent in config_path.resolve().parents:
        if (parent / ".git").exists():
            return parent
    return config_path.resolve().parent


class _Sub:
    """Replaces ``{repo}`` in every string of the file."""

    def __init__(self, repo: Path) -> None:
        self.repo = str(repo)

    def __call__(self, value: Any) -> Any:
        if isinstance(value, str):
            return value.replace("{repo}", self.repo)
        if isinstance(value, list):
            return [self(v) for v in value]
        if isinstance(value, dict):
            return {k: self(v) for k, v in value.items()}
        return value


PROCESS_KEYS = {
    "title", "group", "kind", "host", "env", "cmd", "flags", "requires", "conflicts", "ready",
    "confirm_start", "confirm_stop", "input", "stop_grace_s", "help", "hints",
}
TOP_KEYS = {
    "repo", "hosts", "envs", "processes", "checks", "profiles", "devices", "hints", "ui", "tmux",
    "log_dir", "check_interval_s", "known_usb", "session_dir", "keep_sessions",
}


def _process(pid: str, raw: Any, hosts: dict[str, Host], envs: dict[str, Any]) -> Process:
    where = f"processes.{pid}"
    _check_id(pid, where)
    raw = _mapping(raw, where)
    _known_keys(raw, PROCESS_KEYS, where)
    if not isinstance(raw.get("cmd"), str) or not raw["cmd"].strip():
        raise _fail(f"{where}.cmd", "실행할 명령이 없습니다")
    kind = raw.get("kind", "service")
    if kind not in PROCESS_KINDS:
        raise _fail(f"{where}.kind", f"'{kind}' 는 없습니다 ({' / '.join(PROCESS_KINDS)})")
    host = raw.get("host", LOCAL)
    if host != LOCAL and host not in hosts:
        raise _fail(f"{where}.host", f"'{host}' 는 hosts 에 없습니다")
    env = raw.get("env")
    if env is not None and env not in envs:
        raise _fail(f"{where}.env", f"'{env}' 는 envs 에 없습니다")

    flags = []
    for i, item in enumerate(raw.get("flags") or []):
        fwhere = f"{where}.flags[{i}]"
        item = _mapping(item, fwhere)
        _known_keys(item, {"id", "label", "arg", "default"}, fwhere)
        for key in ("id", "arg"):
            if not isinstance(item.get(key), str):
                raise _fail(fwhere, f"{key} 가 없습니다")
        _check_id(item["id"], fwhere)
        flags.append(Flag(item["id"], str(item.get("label", item["id"])), item["arg"],
                          bool(item.get("default", False))))
    flag_ids = {f.id for f in flags}

    ready = None
    if raw.get("ready") is not None:
        rraw = _mapping(raw["ready"], f"{where}.ready")
        _known_keys(rraw, {"log", "check"}, f"{where}.ready")
        if len(rraw) != 1:
            raise _fail(f"{where}.ready", "log 또는 check 중 하나만 적습니다")
        ready = Ready(
            log=_regex(rraw["log"], f"{where}.ready.log") if "log" in rraw else None,
            check=rraw.get("check"),
        )

    confirm_start = _confirms(raw.get("confirm_start"), f"{where}.confirm_start")
    confirm_stop = _confirms(raw.get("confirm_stop"), f"{where}.confirm_stop")
    for confirm in confirm_start + confirm_stop:
        if confirm.unless_flag is not None and confirm.unless_flag not in flag_ids:
            raise _fail(
                where, f"unless_flag '{confirm.unless_flag}' 는 이 프로세스의 flag 가 아닙니다")

    try:
        grace = float(raw.get("stop_grace_s", 10.0))
    except (TypeError, ValueError) as exc:
        raise _fail(f"{where}.stop_grace_s", "숫자여야 합니다") from exc

    return Process(
        id=pid, title=str(raw.get("title", pid)), group=str(raw.get("group", "기타")), kind=kind,
        host=host, env=env, cmd=raw["cmd"].strip(), flags=tuple(flags),
        requires=_strings(raw.get("requires"), f"{where}.requires"),
        conflicts=_strings(raw.get("conflicts"), f"{where}.conflicts"),
        ready=ready, confirm_start=confirm_start, confirm_stop=confirm_stop,
        input=bool(raw.get("input", False)), stop_grace_s=grace,
        help=str(raw.get("help", "")).strip(), hints=_hints(raw.get("hints"), f"{where}.hints"),
    )


def _check(cid: str, raw: Any, hosts: dict[str, Host]) -> Check:
    where = f"checks.{cid}"
    _check_id(cid, where)
    raw = _mapping(raw, where)
    _known_keys(raw, {"title", "help", "link", *CHECK_KINDS}, where)
    kinds = [k for k in CHECK_KINDS if k in raw]
    if len(kinds) != 1:
        raise _fail(where, f"점검 종류를 하나만 적습니다 ({', '.join(CHECK_KINDS)})")
    kind = kinds[0]
    target = str(raw[kind])
    if kind == "ssh" and target not in hosts:
        raise _fail(f"{where}.ssh", f"'{target}' 는 hosts 에 없습니다")
    if kind == "tcp" and ":" not in target:
        raise _fail(f"{where}.tcp", "'주소:포트' 형태여야 합니다")
    return Check(cid, str(raw.get("title", cid)), kind, target, str(raw.get("help", "")).strip(),
                 str(raw.get("link", "")))


def _events(value: Any, where: str) -> tuple[EventRule, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _fail(where, "목록이어야 합니다")
    out = []
    for i, item in enumerate(value):
        at = f"{where}[{i}]"
        item = _mapping(item, at)
        _known_keys(item, {"match", "level", "text"}, at)
        if "match" not in item or "text" not in item:
            raise _fail(at, "match 와 text 가 있어야 합니다")
        level = item.get("level", "bad")
        if level not in EVENT_LEVELS:
            raise _fail(f"{at}.level", f"{', '.join(EVENT_LEVELS)} 중 하나여야 합니다")
        out.append(EventRule(_regex(item["match"], f"{at}.match"), level, str(item["text"])))
    return tuple(out)


def _device(did: str, raw: Any, processes: dict[str, Process],
            checks: dict[str, Check]) -> Device:
    where = f"devices.{did}"
    _check_id(did, where)
    raw = _mapping(raw, where)
    _known_keys(raw, {"title", "kind", "recorder_stream", "checks", "processes", "tools",
                      "events", "usb_id", "help"}, where)
    kind = raw.get("kind", "generic")
    if kind not in DEVICE_KINDS:
        raise _fail(f"{where}.kind", f"{', '.join(DEVICE_KINDS)} 중 하나여야 합니다")
    refs = {key: _strings(raw.get(key), f"{where}.{key}")
            for key in ("checks", "processes", "tools")}
    for ref in refs["checks"]:
        if ref not in checks:
            raise _fail(f"{where}.checks", f"'{ref}' 는 checks 에 없습니다")
    for ref in refs["processes"]:
        if ref not in processes:
            raise _fail(f"{where}.processes", f"'{ref}' 는 프로세스가 아닙니다")
    for ref in refs["tools"]:
        if ref not in processes or processes[ref].kind != "tool":
            raise _fail(f"{where}.tools", f"'{ref}' 는 kind: tool 인 프로세스가 아닙니다")
    return Device(
        did, str(raw.get("title", did)), kind,
        _strings(raw.get("recorder_stream"), f"{where}.recorder_stream"),
        refs["checks"], refs["processes"], refs["tools"], _events(raw.get("events"),
                                                                  f"{where}.events"),
        str(raw.get("usb_id", "")), str(raw.get("help", "")).strip(),
    )


def load_config(path: Path | str) -> HubConfig:
    path = Path(path).expanduser()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"{path}: 읽을 수 없습니다 ({exc.strerror})") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: YAML 문법 오류\n{exc}") from exc
    raw = _mapping(raw, str(path))
    if "chains" in raw:
        raise ConfigError("chains 는 v2 에서 없어졌습니다. devices 로 옮깁니다")
    _known_keys(raw, TOP_KEYS, "최상위")

    repo = Path(raw["repo"]).expanduser() if raw.get("repo") else _find_repo(path)
    raw = _Sub(repo)(raw)

    hosts: dict[str, Host] = {}
    for name, hraw in _mapping(raw.get("hosts"), "hosts").items():
        where = f"hosts.{name}"
        _check_id(name, where)
        if name == LOCAL:
            raise _fail(where, "'local' 은 이 PC 를 뜻하는 예약 이름입니다")
        hraw = _mapping(hraw, where)
        _known_keys(hraw, {"ssh", "container", "ssh_options"}, where)
        if not isinstance(hraw.get("ssh"), str):
            raise _fail(where, "ssh (예: root@10.42.0.241) 가 없습니다")
        hosts[name] = Host(name, hraw["ssh"], hraw.get("container"),
                           _strings(hraw.get("ssh_options"), f"{where}.ssh_options"))

    envs: dict[str, tuple[str, ...]] = {}
    for name, lines in _mapping(raw.get("envs"), "envs").items():
        envs[name] = _strings(lines, f"envs.{name}")

    processes = {
        pid: _process(pid, praw, hosts, envs)
        for pid, praw in _mapping(raw.get("processes"), "processes").items()
    }
    checks = {
        cid: _check(cid, craw, hosts) for cid, craw in _mapping(raw.get("checks"), "checks").items()
    }
    both = set(processes) & set(checks)
    if both:
        raise ConfigError(f"프로세스와 점검에 같은 id 가 있습니다: {', '.join(sorted(both))}")

    # references
    conflicts: dict[str, set[str]] = {pid: set() for pid in processes}
    for pid, proc in processes.items():
        for ref in proc.requires:
            if ref == pid or (ref not in processes and ref not in checks):
                raise _fail(f"processes.{pid}.requires", f"'{ref}' 는 프로세스도 점검도 아닙니다")
        for ref in proc.conflicts:
            if ref == pid or ref not in processes:
                raise _fail(f"processes.{pid}.conflicts", f"'{ref}' 는 프로세스가 아닙니다")
            conflicts[pid].add(ref)
            conflicts[ref].add(pid)  # a conflict holds both ways
        ready_check = proc.ready.check if proc.ready is not None else None
        if ready_check is not None and ready_check not in checks:
            raise _fail(f"processes.{pid}.ready.check", f"'{ready_check}' 는 checks 에 없습니다")
    processes = {
        pid: Process(**{**proc.__dict__, "conflicts": tuple(sorted(conflicts[pid]))})
        for pid, proc in processes.items()
    }

    profiles = []
    for i, praw in enumerate(raw.get("profiles") or []):
        where = f"profiles[{i}]"
        praw = _mapping(praw, where)
        _known_keys(praw, {"id", "title", "steps", "help"}, where)
        _check_id(praw.get("id", ""), where)
        steps = []
        for j, sraw in enumerate(praw.get("steps") or []):
            if isinstance(sraw, str):
                if sraw not in processes:
                    raise _fail(f"{where}.steps[{j}]", f"'{sraw}' 는 프로세스가 아닙니다")
                steps.append(Step(process=sraw))
            elif isinstance(sraw, dict) and set(sraw) == {"note"}:
                steps.append(Step(note=str(sraw["note"])))
            else:
                raise _fail(f"{where}.steps[{j}]", "프로세스 id 또는 {note: 문장} 이어야 합니다")
        profiles.append(Profile(praw["id"], str(praw.get("title", praw["id"])), tuple(steps),
                                str(praw.get("help", "")).strip()))

    devices = {
        did: _device(did, draw, processes, checks)
        for did, draw in _mapping(raw.get("devices"), "devices").items()
    }
    known_usb = {str(k): str(v) for k, v in _mapping(raw.get("known_usb"), "known_usb").items()}

    ui = _mapping(raw.get("ui"), "ui")
    _known_keys(ui, {"host", "port"}, "ui")
    tmux = _mapping(raw.get("tmux"), "tmux")
    _known_keys(tmux, {"socket", "session"}, "tmux")

    return HubConfig(
        path=path, repo=repo, hosts=hosts, envs=envs, processes=processes, checks=checks,
        profiles=tuple(profiles), devices=devices, hints=_hints(raw.get("hints"), "hints"),
        known_usb=known_usb,
        ui_host=str(ui.get("host", "127.0.0.1")), ui_port=int(ui.get("port", 8700)),
        tmux_socket=str(tmux.get("socket", "shapeup")),
        tmux_session=str(tmux.get("session", "hub")),
        log_dir=Path(raw.get("log_dir", "~/.local/state/control_hub/logs")).expanduser(),
        check_interval_s=float(raw.get("check_interval_s", 3.0)),
        session_dir=Path(raw.get("session_dir", "~/.local/state/control_hub/sessions"))
        .expanduser(),
        keep_sessions=int(raw.get("keep_sessions", 30)),
    )
