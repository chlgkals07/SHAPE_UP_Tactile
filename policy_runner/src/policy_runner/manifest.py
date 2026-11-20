from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from tactile_rec import features
from tactile_rec.hub import Hub


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    joint_names: list[str]
    fps: float
    pred_horizon: int
    cameras: list[str]
    mount: str
    hand_action: str
    checkpoint: str
    norm_stats_id: str

    @classmethod
    def load(cls, path: str | Path) -> Manifest:
        return cls.from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Manifest:
        names = {f.name for f in dataclasses.fields(cls)}
        missing = sorted(names - set(raw))
        unknown = sorted(set(raw) - names)
        if missing or unknown:
            raise ValueError(f"manifest: missing {missing}, unknown {unknown}")
        return cls(**{**raw, "joint_names": list(raw["joint_names"]),
                      "cameras": list(raw["cameras"])})

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def mismatches(self, hub: Hub) -> list[str]:
        dataset = hub.config.dataset
        arm_joints = hub.streams[dataset.arm_state].spec.meta["joints"]
        rig = {
            "joint_names": features.joint_names(arm_joints, dataset.arm_dof),
            "fps": dataset.fps,
            "cameras": list(dataset.cameras),
            "mount": hub.config.mount,
            "hand_action": dataset.hand_action,
        }
        return [
            f"{key}: manifest {getattr(self, key)!r}, rig {value!r}"
            for key, value in rig.items() if getattr(self, key) != value
        ]

    def differences(self, other: dict[str, Any]) -> list[str]:
        mine = self.to_dict()
        return [f"{key}: runner {mine.get(key)!r}, server {other.get(key)!r}"
                for key in sorted(set(mine) | set(other)) if mine.get(key) != other.get(key)]
