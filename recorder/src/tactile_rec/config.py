"""Rig config: one YAML file describes the devices, the recording and the dataset.

Everything is checked when the file is loaded, so a typo stops the program before recording
rather than in the middle of an episode. Unknown keys are errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from tactile_rec.convert.align import TIME_MODES
from tactile_rec.tactile import DEFAULT_ORDER

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")

# type -> (required keys, optional keys with defaults)
STREAM_TYPES: dict[str, tuple[tuple[str, ...], dict[str, Any]]] = {
    "arm_zenoh": (
        ("message", "topic", "joints", "hz"),
        {"router": "10.42.0.241:7447", "domain_id": 30},
    ),
    "hand_udp": (("hz",), {"host": "127.0.0.1", "port": 47800, "glove": True}),
    "paxini": (("port", "hz", "places"), {"baudrate": 921600}),
    "realsense": (
        ("width", "height", "fps"),
        {"serial": "", "rotation_deg": 0, "exposure_us": 0},
    ),
    "fake": (("like", "hz"), {"places": None, "width": 320, "height": 240, "rotation_deg": 0,
                              "joints": None, "tap_period_s": 4.0, "drop_after_s": 0.0}),
}
FAKE_KINDS = ("arm_state", "arm_action", "hand", "glove", "tactile", "camera")
ARM_MESSAGES = ("joint_state", "joint_trajectory")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RecordConfig:
    preroll_s: float = 1.0
    time_limit_s: float = 0.0  # 0 = no limit
    jpeg_quality: int = 95
    min_free_gb: float = 5.0


@dataclass(frozen=True)
class SessionConfig:
    task: str = "untitled"
    text: str = ""
    operator: str = "anon"


@dataclass(frozen=True)
class DatasetConfig:
    fps: float = 30.0
    robot_type: str = "omy_f3m_leap"
    arm_state: str = "arm_state"
    arm_action: str = "arm_action"
    hand: str = "hand"
    arm_dof: int = 6  # leading joints of the arm streams that go into state / action
    hand_action: str = "cmd"  # "cmd" (after the stale guard) or "sent" (after clip + slew)
    tactile: tuple[str, ...] = ()
    tactile_order: tuple[str, ...] = DEFAULT_ORDER
    tactile_hr: int = 3  # high-rate tactile samples packed into each dataset step
    tactile_hr_distributed: bool = False
    cameras: tuple[str, ...] = ()
    max_staleness_ms: float = 150.0
    time: dict[str, str] = field(default_factory=dict)  # stream -> recv | src | respread
    latency_ms: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class UiConfig:
    host: str = "0.0.0.0"
    port: int = 8800
    preview_hz: float = 10.0
    preview_width: int = 480


@dataclass(frozen=True)
class Config:
    rig_name: str
    mount: str
    data_root: Path
    streams: dict[str, dict[str, Any]]
    record: RecordConfig
    session: SessionConfig
    dataset: DatasetConfig
    ui: UiConfig
    source: str = ""  # path of the YAML file, for display

    def to_json(self) -> dict[str, Any]:
        import dataclasses

        def plain(value: Any) -> Any:
            if dataclasses.is_dataclass(value):
                return {k: plain(v) for k, v in dataclasses.asdict(value).items()}
            if isinstance(value, dict):
                return {k: plain(v) for k, v in value.items()}
            if isinstance(value, (tuple, list)):
                return [plain(v) for v in value]
            if isinstance(value, Path):
                return str(value)
            return value

        return plain(self)


def _section(raw: dict[str, Any], key: str, cls: type) -> Any:
    data = raw.get(key) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{key}: must be a mapping")
    allowed = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
    unknown = set(data) - allowed
    if unknown:
        raise ConfigError(f"{key}: unknown keys {sorted(unknown)} (allowed: {sorted(allowed)})")
    converted = {k: tuple(v) if isinstance(v, list) else v for k, v in data.items()}
    return cls(**converted)


def _check_stream(name: str, raw: Any) -> dict[str, Any]:
    if not NAME_PATTERN.match(name):
        raise ConfigError(f"streams.{name}: names are lowercase letters, digits and '_'")
    if not isinstance(raw, dict) or "type" not in raw:
        raise ConfigError(f"streams.{name}: needs a 'type'")
    kind = raw["type"]
    if kind not in STREAM_TYPES:
        raise ConfigError(f"streams.{name}: unknown type {kind!r} (known: {sorted(STREAM_TYPES)})")
    required, optional = STREAM_TYPES[kind]
    common = {"type", "required"}
    unknown = set(raw) - common - set(required) - set(optional)
    if unknown:
        raise ConfigError(f"streams.{name}: unknown keys {sorted(unknown)} for type {kind}")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ConfigError(f"streams.{name}: missing {missing} for type {kind}")
    out = {**optional, "required": True, **raw}
    if not isinstance(out["hz"] if "hz" in out else out["fps"], (int, float)):
        raise ConfigError(f"streams.{name}: rate must be a number")
    rate = float(out.get("hz", out.get("fps")))
    if rate <= 0:
        raise ConfigError(f"streams.{name}: rate must be positive")
    if kind == "arm_zenoh" and out["message"] not in ARM_MESSAGES:
        raise ConfigError(f"streams.{name}: message must be one of {ARM_MESSAGES}")
    if kind == "fake":
        if out["like"] not in FAKE_KINDS:
            raise ConfigError(f"streams.{name}: like must be one of {FAKE_KINDS}")
        if out["like"] == "tactile" and not out["places"]:
            raise ConfigError(f"streams.{name}: a fake tactile stream needs 'places'")
    if kind in ("realsense", "fake") and out["rotation_deg"] not in (0, 90, 180, 270):
        raise ConfigError(f"streams.{name}: rotation_deg must be 0, 90, 180 or 270")
    if kind == "paxini" and (not isinstance(out["places"], dict) or not out["places"]):
        raise ConfigError(f"streams.{name}: places must map board module names to hand places")
    return out


def _check_label(value: str, what: str) -> None:
    if not LABEL_PATTERN.match(value):
        raise ConfigError(
            f"{what} {value!r}: use letters, digits, '_' and '-' only (it becomes a folder name)"
        )


def parse_config(raw: dict[str, Any], source: str = "") -> Config:
    if not isinstance(raw, dict):
        raise ConfigError("config must be a mapping")
    known = {"rig", "data_root", "streams", "record", "session", "dataset", "ui"}
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"unknown top-level keys {sorted(unknown)}")
    rig = raw.get("rig") or {}
    if "name" not in rig or "mount" not in rig:
        raise ConfigError("rig: needs 'name' and 'mount'")
    _check_label(str(rig["mount"]), "rig.mount")
    streams_raw = raw.get("streams") or {}
    if not streams_raw:
        raise ConfigError("streams: at least one stream is required")
    streams = {name: _check_stream(name, value) for name, value in streams_raw.items()}
    session = _section(raw, "session", SessionConfig)
    _check_label(session.task, "session.task")
    _check_label(session.operator, "session.operator")
    record = _section(raw, "record", RecordConfig)
    if not 1 <= record.jpeg_quality <= 100:
        raise ConfigError("record.jpeg_quality must be 1..100")
    if record.preroll_s < 0 or record.preroll_s > 1.5:
        raise ConfigError("record.preroll_s must be 0..1.5 (streams keep 2 s of history)")
    dataset = _section(raw, "dataset", DatasetConfig)
    if dataset.hand_action not in ("cmd", "sent"):
        raise ConfigError("dataset.hand_action must be 'cmd' or 'sent'")
    if dataset.tactile_hr < 1:
        raise ConfigError("dataset.tactile_hr must be >= 1")
    for stream, mode in dataset.time.items():
        if mode not in TIME_MODES:
            raise ConfigError(f"dataset.time.{stream}: must be one of {TIME_MODES}")
    produced = set(streams)
    if any(s["type"] == "hand_udp" and s["glove"] for s in streams.values()):
        produced.add("glove")
    referenced = [dataset.arm_state, dataset.arm_action, dataset.hand]
    referenced += list(dataset.tactile) + list(dataset.cameras)
    referenced += list(dataset.time) + list(dataset.latency_ms)
    for name in referenced:
        if name not in produced:
            raise ConfigError(f"dataset refers to stream {name!r}, which is not in streams")
    return Config(
        rig_name=str(rig["name"]),
        mount=str(rig["mount"]),
        data_root=Path(str(raw.get("data_root", "data"))).expanduser(),
        streams=streams,
        record=record,
        session=session,
        dataset=dataset,
        ui=_section(raw, "ui", UiConfig),
        source=source,
    )


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"config file not found: {path}") from error
    except yaml.YAMLError as error:
        raise ConfigError(f"{path}: not valid YAML: {error}") from error
    return parse_config(raw, source=str(path))
