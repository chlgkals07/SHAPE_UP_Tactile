from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from tactile_rec.config import Config, load_config
from tactile_rec.convert import align
from tactile_rec.hub import Hub
from tactile_rec.types import SRC_MONO

from policy_runner.manifest import Manifest

MS = 1_000_000
MODES = ("dry_run", "hand")
ONLINE_TIME_MODES = (align.TIME_RECV, align.TIME_SRC)


class ConfigError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class RunnerConfig:
    rig: Config
    manifest: Manifest
    endpoint: str
    connect_timeout_s: float
    infer_timeout_s: float
    max_age_ms: dict[str, float]
    max_skew_ms: float
    mode: str
    exec_horizon: int
    hand_udp: tuple[str, int]
    ui: tuple[str, int]
    trace_dir: Path
    warmup_timeout_s: float
    max_failures: int
    obs_fail_after_ms: float

    @property
    def dt_ns(self) -> int:
        return round(1e9 / self.rig.dataset.fps)

    @property
    def cameras(self) -> tuple[str, ...]:
        return tuple(self.manifest.cameras)

    @property
    def required_streams(self) -> tuple[str, ...]:
        return (self.rig.dataset.arm_state, self.rig.dataset.hand, *self.cameras)

    @property
    def prompt(self) -> str:
        return self.rig.session.text


def load(path: str | Path, allow_hand: bool = False) -> RunnerConfig:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return parse(raw, path.parent, allow_hand)


def parse(raw: dict[str, Any], base: Path, allow_hand: bool = False) -> RunnerConfig:
    try:
        rig = load_config(resolve(base, raw["rig"]))
        manifest = Manifest.load(resolve(base, raw["manifest"]))
        policy, observation, execution = raw["policy"], raw["observation"], raw["execution"]
        cfg = RunnerConfig(
            rig=rig,
            manifest=manifest,
            endpoint=str(policy["endpoint"]),
            connect_timeout_s=float(policy["connect_timeout_s"]),
            infer_timeout_s=float(policy["infer_timeout_ms"]) / 1000,
            max_age_ms={str(k): float(v) for k, v in observation["max_age_ms"].items()},
            max_skew_ms=float(observation["max_skew_ms"]),
            mode=str(execution["mode"]),
            exec_horizon=int(execution["exec_horizon"]),
            hand_udp=(str(raw["hand_udp"]["host"]), int(raw["hand_udp"]["port"])),
            ui=(str(raw["ui"]["host"]), int(raw["ui"]["port"])),
            trace_dir=resolve(base, raw["trace"]["dir"]),
            warmup_timeout_s=float(policy.get("warmup_timeout_s", 60)),
            max_failures=int(policy.get("max_failures", 3)),
            obs_fail_after_ms=float(observation.get("fail_after_ms", 1000)),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ConfigError([f"{type(error).__name__}: {error}"]) from error
    problems = check(cfg, allow_hand)
    if problems:
        raise ConfigError(problems)
    return cfg


def resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def check(cfg: RunnerConfig, allow_hand: bool) -> list[str]:
    dataset = cfg.rig.dataset
    problems = []
    if cfg.mode not in MODES:
        problems.append(f"execution.mode: {cfg.mode!r} is not one of {MODES}")
    if cfg.mode == "hand" and not allow_hand:
        problems.append("execution.mode: hand sends targets to leap_teleop; start with "
                        "--allow-hand")
    if not 1 <= cfg.exec_horizon <= cfg.manifest.pred_horizon:
        problems.append(f"execution.exec_horizon: {cfg.exec_horizon} is outside "
                        f"1..{cfg.manifest.pred_horizon}")
    for name in cfg.required_streams:
        if name not in cfg.rig.streams:
            problems.append(f"{name}: required by the manifest but not in the rig")
            continue
        if name not in cfg.max_age_ms:
            problems.append(f"observation.max_age_ms: no budget for {name}")
        mode = dataset.time.get(name, align.TIME_RECV)
        if mode not in ONLINE_TIME_MODES:
            problems.append(f"dataset.time.{name}: {mode} needs samples from the future; "
                            "use recv or src")
    if problems:
        return problems
    hub = Hub(cfg.rig)
    for name in cfg.required_streams:
        src_clock = hub.streams[name].spec.src_clock
        if dataset.time.get(name) == align.TIME_SRC and src_clock != SRC_MONO:
            problems.append(f"dataset.time.{name}: src on a {src_clock} clock cannot be mapped "
                            "while running; use recv")
    problems += [f"manifest {p}" for p in cfg.manifest.mismatches(hub)]
    return problems
