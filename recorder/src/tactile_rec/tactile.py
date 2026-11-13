"""Paxini payload layout and decoding, shared by the live view, the converter and the policy side.

The recorder stores the board's payload bytes untouched. Everything here is a pure function of
those bytes, so a wrong decoding rule can be fixed later without re-recording.

Decoding rule (vendor Hand_UI.py, cross-checked on hardware only for small loads, see
third_party/paxini/docs/FINDINGS.md): per active module, in board order,
  6 bytes resultant   [Fx_lo Fx_hi Fy_lo Fy_hi Fz_lo Fz_hi]   (if the board sends resultants)
  3 bytes per taxel   [Fx Fy Fz]                              (if it sends distributed forces)
Only the low byte is used: Fx, Fy are int8, Fz is uint8, 0.1 N per count.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

NEWTON_PER_COUNT = 0.1

FINGERS = ("thumb", "index", "middle", "ring")
SEGMENTS = ("tip", "pad")
DEFAULT_ORDER = tuple(f"{finger}_{segment}" for finger in FINGERS for segment in SEGMENTS)


@dataclass(frozen=True)
class Module:
    name: str  # board name, e.g. "Index-Tip"
    points: int  # taxel count (identifies the sensor model)
    place: str  # where it sits on our hand, e.g. "index_tip"
    model: str = ""


@dataclass(frozen=True)
class TactileLayout:
    modules: tuple[Module, ...]
    has_resultant: bool = True
    has_distributed: bool = True

    def module_size(self, module: Module) -> int:
        return (6 if self.has_resultant else 0) + (module.points * 3 if self.has_distributed else 0)

    @property
    def payload_size(self) -> int:
        return sum(self.module_size(m) for m in self.modules)

    def to_json(self) -> dict[str, Any]:
        return {
            "has_resultant": self.has_resultant,
            "has_distributed": self.has_distributed,
            "payload_size": self.payload_size,
            "modules": [
                {"name": m.name, "points": m.points, "place": m.place, "model": m.model}
                for m in self.modules
            ],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TactileLayout:
        modules = tuple(
            Module(m["name"], int(m["points"]), m["place"], m.get("model", ""))
            for m in data["modules"]
        )
        return cls(modules, bool(data["has_resultant"]), bool(data["has_distributed"]))


def _signed_xy_unsigned_z(raw: np.ndarray) -> np.ndarray:
    """(..., 3) uint8 [Fx Fy Fz] -> int16 with Fx, Fy read as int8 and Fz as uint8."""
    out = raw.astype(np.int16)
    out[..., :2] = raw[..., :2].astype(np.int8)
    return out


def decode_payload(
    payload: np.ndarray, layout: TactileLayout
) -> dict[str, dict[str, np.ndarray]]:
    """Decode payload bytes into counts.

    payload: (T, payload_size) or (payload_size,) uint8.
    Returns {place: {"resultant": (T, 3) int16, "distributed": (T, points, 3) int16}}.
    A missing data type gives an array with zero rows on the last-but-one axis.
    """
    payload = np.atleast_2d(np.asarray(payload, dtype=np.uint8))
    if payload.shape[1] != layout.payload_size:
        raise ValueError(
            f"payload has {payload.shape[1]} bytes per frame, layout expects {layout.payload_size}"
        )
    frames = payload.shape[0]
    out: dict[str, dict[str, np.ndarray]] = {}
    offset = 0
    for module in layout.modules:
        if layout.has_resultant:
            block = payload[:, offset : offset + 6]
            resultant = _signed_xy_unsigned_z(block[:, [0, 2, 4]])
            offset += 6
        else:
            resultant = np.zeros((frames, 3), dtype=np.int16)
        if layout.has_distributed:
            size = module.points * 3
            block = payload[:, offset : offset + size].reshape(frames, module.points, 3)
            distributed = _signed_xy_unsigned_z(block)
            offset += size
        else:
            distributed = np.zeros((frames, 0, 3), dtype=np.int16)
        out[module.place] = {"resultant": resultant, "distributed": distributed}
    return out


def to_newtons(counts: np.ndarray) -> np.ndarray:
    return counts.astype(np.float32) * NEWTON_PER_COUNT


def encode_payload(
    layout: TactileLayout, forces: dict[str, tuple[np.ndarray, np.ndarray]]
) -> np.ndarray:
    """Inverse of decode_payload for one frame (fake streams and tests).

    forces: {place: (resultant counts (3,), distributed counts (points, 3))}.
    """
    parts: list[np.ndarray] = []
    for module in layout.modules:
        resultant, distributed = forces[module.place]
        if layout.has_resultant:
            block = np.zeros(6, dtype=np.uint8)
            block[[0, 2, 4]] = np.asarray(resultant, dtype=np.int16).astype(np.uint8)
            parts.append(block)
        if layout.has_distributed:
            taxels = np.asarray(distributed, dtype=np.int16).reshape(module.points, 3)
            parts.append(taxels.astype(np.uint8).reshape(-1))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.uint8)
