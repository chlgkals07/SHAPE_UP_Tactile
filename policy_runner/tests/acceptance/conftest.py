from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from tactile_rec import features
from tactile_rec.clock import FakeClock
from tactile_rec.config import parse_config
from tactile_rec.hub import Hub
from tactile_rec.stream import Stream
from tactile_rec.streams.fake import FakeStream
from tactile_rec.types import Field, Sample, StreamSpec

PLACES = {
    "Thumb-Tip": "thumb_tip", "Thumb-Middle": "thumb_pad",
    "Index-Tip": "index_tip", "Index-Middle": "index_pad",
    "Middle-Tip": "middle_tip", "Middle-Middle": "middle_pad",
    "Little-Tip": "ring_tip", "Little-Middle": "ring_pad",
}

ARM_JOINTS = [f"joint{i}" for i in range(1, 7)]


def rig_dict(tmp_path: Path, **dataset: Any) -> dict[str, Any]:
    raw = {
        "rig": {"name": "omy_f3m_leap", "mount": "wrist_flip"},
        "data_root": str(tmp_path / "data"),
        "session": {"task": "pick_cup", "text": "Pick up the cup", "operator": "tester"},
        "record": {"preroll_s": 1.0, "min_free_gb": 0, "jpeg_quality": 95},
        "streams": {
            "arm_state": {"type": "fake", "like": "arm_state", "hz": 400},
            "arm_action": {"type": "fake", "like": "arm_action", "hz": 300},
            "hand": {"type": "fake", "like": "hand", "hz": 50},
            "tactile_a": {"type": "fake", "like": "tactile", "hz": 90, "places": PLACES},
            "cam_wrist": {"type": "fake", "like": "camera", "hz": 30, "width": 64,
                          "height": 48, "rotation_deg": 90},
            "cam_ext": {"type": "fake", "like": "camera", "hz": 30, "width": 64, "height": 48},
        },
        "dataset": {
            "fps": 30,
            "hand_action": "sent",
            "tactile": ["tactile_a"],
            "cameras": ["cam_wrist", "cam_ext"],
            "time": {"hand": "src", "tactile_a": "respread"},
            **dataset,
        },
    }
    return raw


def manifest_dict(**overrides: Any) -> dict[str, Any]:
    raw = {
        "schema_version": 1,
        "joint_names": features.joint_names(ARM_JOINTS, 6),
        "fps": 30,
        "pred_horizon": 50,
        "cameras": ["cam_wrist", "cam_ext"],
        "mount": "wrist_flip",
        "hand_action": "sent",
        "checkpoint": "fake",
        "norm_stats_id": "fake",
    }
    raw.update(overrides)
    return raw


def runner_dict(**overrides: Any) -> dict[str, Any]:
    raw = {
        "rig": "rig.yaml",
        "manifest": "manifest.yaml",
        "policy": {"endpoint": "ws://127.0.0.1:8000", "connect_timeout_s": 2,
                   "infer_timeout_ms": 1000},
        "observation": {"max_age_ms": {"cam_wrist": 200, "cam_ext": 200, "arm_state": 50,
                                       "hand": 100},
                        "max_skew_ms": 200},
        "execution": {"mode": "dry_run", "exec_horizon": 10, "chunk_max_delay_ms": 500,
                      "tick_jitter_ms": 10},
        "hand_udp": {"host": "127.0.0.1", "port": 47810},
        "ui": {"host": "127.0.0.1", "port": 8810},
        "trace": {"dir": "traces"},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(raw.get(key), dict):
            raw[key] = {**raw[key], **value}
        else:
            raw[key] = value
    return raw


def write_yaml(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def files(tmp_path):
    def make(rig=None, manifest=None, runner=None) -> Path:
        write_yaml(tmp_path / "rig.yaml", rig if rig is not None else rig_dict(tmp_path))
        write_yaml(tmp_path / "manifest.yaml", manifest if manifest is not None
                   else manifest_dict())
        return write_yaml(tmp_path / "runner.yaml", runner if runner is not None
                          else runner_dict())
    return make


def passive_rig(tmp_path: Path, clock: FakeClock, **dataset: Any):
    config = parse_config(rig_dict(tmp_path, **dataset))
    makers = {name: FakeStream(name, cfg, clock) for name, cfg in config.streams.items()}
    streams = {name: Stream(maker.spec, clock, buffer_s=2.0) for name, maker in makers.items()}
    return Hub(config, clock, streams), makers


def passive_hub(tmp_path: Path, clock: FakeClock | None = None, **dataset: Any) -> Hub:
    return passive_rig(tmp_path, clock or FakeClock(), **dataset)[0]


@dataclass
class TimedRig:
    hub: Hub
    clock: FakeClock
    makers: dict[str, FakeStream]
    collected: dict[str, list[Sample]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._due = {name: self.clock.now_ns() for name in self.hub.streams}
        for name, stream in self.hub.streams.items():
            self.collected[name] = []
            stream.subscribe(self.collected[name].append)

    def run(self, seconds: float, on_step=None) -> None:
        end_ns = self.clock.now_ns() + int(seconds * 1e9)
        while True:
            name = min(self._due, key=lambda n: self._due[n])
            due = self._due[name]
            if due > end_ns:
                break
            self.clock.set_ns(max(due, self.clock.now_ns()))
            stream = self.hub.streams[name]
            self._due[name] = due + int(1e9 / stream.spec.nominal_hz)
            maker = self.makers[name]
            maker._tick += 1
            stream.push(maker.make(due / 1e9), t_src_ns=due, src_seq=maker._tick)
            if on_step is not None:
                on_step()
        self.clock.set_ns(end_ns)


@pytest.fixture
def timed_rig(tmp_path):
    def make(**dataset: Any) -> TimedRig:
        clock = FakeClock()
        hub, makers = passive_rig(tmp_path, clock, **dataset)
        return TimedRig(hub, clock, makers)
    return make


def spec_from_json(name: str, raw: dict[str, Any]) -> StreamSpec:
    fields = {key: Field(tuple(f["shape"]), f["dtype"], f.get("unit", ""))
              for key, f in raw["fields"].items()}
    return StreamSpec(name, kind=raw["kind"], fields=fields, nominal_hz=raw["nominal_hz"],
                      required=raw["required"], src_clock=raw["src_clock"],
                      meta=copy.deepcopy(raw["meta"]))


class Replay:
    def __init__(self, hub: Hub, clock: FakeClock, recorded: dict[str, list[Sample]]):
        self.hub = hub
        self.clock = clock
        self.queue = sorted(
            ((s.t_recv_ns, name, s) for name, samples in recorded.items() for s in samples),
            key=lambda item: (item[0], item[1]),
        )
        self.next = 0

    def until(self, t_ns: int) -> None:
        while self.next < len(self.queue) and self.queue[self.next][0] <= t_ns:
            _, name, sample = self.queue[self.next]
            self.hub.streams[name].push(sample.data, t_src_ns=sample.t_src_ns,
                                        src_seq=sample.src_seq, t_recv_ns=sample.t_recv_ns)
            self.next += 1
        self.clock.set_ns(t_ns)


def fresh_hub_like(hub: Hub, clock: FakeClock) -> Hub:
    streams = {name: Stream(stream.spec, clock, buffer_s=2.0)
               for name, stream in hub.streams.items()}
    return Hub(hub.config, clock, streams)


def episode_samples(episode, names: list[str]) -> dict[str, list[Sample]]:
    out: dict[str, list[Sample]] = {}
    for name in names:
        arrays = episode.arrays(name)
        keys = [k for k in arrays if k not in ("t_recv_ns", "t_src_ns", "src_seq", "seq")]
        out[name] = [
            Sample(int(arrays["t_recv_ns"][i]), i, {k: arrays[k][i] for k in keys},
                   int(arrays["t_src_ns"][i]),
                   int(arrays["src_seq"][i]) if "src_seq" in arrays else -1)
            for i in range(arrays["t_recv_ns"].size)
        ]
    return out


def read_trace(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


@dataclass
class SimulatedInference:
    clock: FakeClock
    latency_ns: int
    measured: Any
    pred_horizon: int = 50
    fault: str = ""
    requests: list[int] = field(default_factory=list)
    _pending: int | None = None
    _ids: int = 0

    def request(self, now_ns: int) -> None:
        self.requests.append(now_ns)
        self._pending = now_ns

    def take(self, now_ns: int):
        from policy_runner.chunk import ActionChunk

        if self._pending is None or now_ns < self._pending + self.latency_ns:
            return None
        t_obs = self._pending
        self._pending = None
        self._ids += 1
        actions = np.tile(self.measured(), (self.pred_horizon, 1)).astype(np.float32)
        return ActionChunk(chunk_id=self._ids, obs_id=self._ids, t_obs_ns=t_obs,
                           t_reply_ns=t_obs + self.latency_ns, actions=actions)


@dataclass
class RecordingCommand:
    rows: list[tuple[int, np.ndarray]] = field(default_factory=list)

    def send(self, row: np.ndarray, t_ns: int) -> None:
        self.rows.append((t_ns, np.array(row)))
