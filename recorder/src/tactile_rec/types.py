"""Shared data contract between stream adapters, the recorder, the converter and the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

NO_TIME = -1  # stored in int64 arrays where a source timestamp / source sequence is absent

# Where a stream's source timestamp comes from. Decides how the converter may use it.
SRC_NONE = "none"  # the device gives no timestamp
SRC_MONO = "mono"  # same CLOCK_MONOTONIC as t_recv_ns (another process on this PC)
SRC_HOST_WALL = "host_wall"  # this PC's wall clock (epoch ns)
SRC_REMOTE_WALL = "remote_wall"  # another PC's wall clock (epoch ns), offset unknown
SRC_CLOCKS = (SRC_NONE, SRC_MONO, SRC_HOST_WALL, SRC_REMOTE_WALL)

KIND_NUMERIC = "numeric"
KIND_VIDEO = "video"


@dataclass(frozen=True)
class Field:
    shape: tuple[int, ...]
    dtype: str
    unit: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"shape": list(self.shape), "dtype": self.dtype, "unit": self.unit}


@dataclass
class StreamSpec:
    """What a stream carries. `meta` may be filled in after the device connects."""

    name: str
    kind: str = KIND_NUMERIC
    fields: dict[str, Field] = field(default_factory=dict)
    nominal_hz: float = 0.0
    required: bool = True
    src_clock: str = SRC_NONE
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in (KIND_NUMERIC, KIND_VIDEO):
            raise ValueError(f"{self.name}: unknown kind {self.kind!r}")
        if self.src_clock not in SRC_CLOCKS:
            raise ValueError(f"{self.name}: unknown src_clock {self.src_clock!r}")
        if self.nominal_hz <= 0:
            raise ValueError(f"{self.name}: nominal_hz must be positive")

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "fields": {k: f.to_json() for k, f in self.fields.items()},
            "nominal_hz": self.nominal_hz,
            "required": self.required,
            "src_clock": self.src_clock,
            "meta": self.meta,
        }


@dataclass(frozen=True)
class Sample:
    """One reading. `t_recv_ns` is stamped on arrival; `t_src_ns` is the device's own time."""

    t_recv_ns: int
    seq: int  # per-stream arrival counter, starts at 0
    data: dict[str, np.ndarray]
    t_src_ns: int = NO_TIME
    src_seq: int = NO_TIME  # device-side counter (camera frame number, teleop tick), if any


STATUS_OFF = "off"  # nothing received yet
STATUS_OK = "ok"
STATUS_SLOW = "slow"  # arriving, but below the expected rate
STATUS_STALE = "stale"  # was arriving, now silent
STATUS_ERROR = "error"  # the adapter reported a failure


@dataclass(frozen=True)
class Health:
    status: str
    hz: float
    age_s: float | None  # seconds since the last sample; None before the first
    count: int
    missed: int  # samples the device produced that never arrived (from src_seq gaps)
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "hz": round(self.hz, 1),
            "age_s": None if self.age_s is None else round(self.age_s, 3),
            "count": self.count,
            "missed": self.missed,
            "message": self.message,
        }
