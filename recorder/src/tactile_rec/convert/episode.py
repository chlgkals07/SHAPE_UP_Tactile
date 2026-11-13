"""One raw episode -> fixed-rate arrays ready to be written as a dataset. numpy only.

Every grid step takes, for each stream, the latest sample at or before that step (causal, no
interpolation). How old that sample was is measured and reported, so a stream that stalled
shows up as a number instead of silently frozen values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from tactile_rec import features
from tactile_rec.config import DatasetConfig
from tactile_rec.convert import align
from tactile_rec.convert.load import Episode, EpisodeError
from tactile_rec.tactile import decode_payload


class ConvertError(ValueError):
    pass


@dataclass
class Converted:
    grid_ns: np.ndarray
    arrays: dict[str, np.ndarray]  # feature key -> (T, D) float32
    names: dict[str, list[str]]  # feature key -> D element names
    frames: dict[str, np.ndarray]  # camera -> (T,) index of the stored frame for each step
    image_shapes: dict[str, tuple[int, int, int]]  # camera -> upright (H, W, 3)
    rotations: dict[str, int]
    report: dict[str, Any] = field(default_factory=dict)

    @property
    def steps(self) -> int:
        return int(self.grid_ns.size)


def _percentile(values: np.ndarray, q: float) -> float:
    finite = values[np.isfinite(values)]
    return float(np.percentile(finite, q)) if finite.size else float("nan")


class _Timed:
    """A stream's samples with their alignment times, and what was picked from it."""

    def __init__(self, episode: Episode, name: str, cfg: DatasetConfig):
        self.name = name
        self.spec = episode.spec(name)
        self.data = episode.arrays(name)
        if self.data["t_recv_ns"].size == 0:
            raise ConvertError(f"{episode.name}: stream {name} has no samples")
        self.mode = cfg.time.get(name, align.TIME_RECV)
        self.times, self.note = align.stream_times(
            self.data["t_recv_ns"], self.data["t_src_ns"],
            mode=self.mode, src_clock=self.spec["src_clock"], anchor=episode.meta["start"],
            latency_ns=int(cfg.latency_ms.get(name, 0.0) * 1e6),
        )
        self.staleness: np.ndarray | None = None

    def pick(self, grid_ns: np.ndarray, rows: np.ndarray | None = None) -> np.ndarray:
        """Row index for each grid time. With `rows` (a boolean mask) only those rows count."""
        if rows is None:
            index = align.pick_latest(self.times, grid_ns)
            times = self.times
        else:
            usable = np.flatnonzero(rows)
            if usable.size == 0:
                raise ConvertError(f"stream {self.name} has no usable samples")
            sub = align.pick_latest(self.times[usable], grid_ns)
            index = np.where(sub >= 0, usable[np.clip(sub, 0, None)], -1)
            times = self.times
        if (index < 0).any():
            raise ConvertError(
                f"stream {self.name}: {int((index < 0).sum())} steps come before its first sample"
            )
        stale = align.staleness_s(times, grid_ns, index)
        self.staleness = stale if self.staleness is None else np.maximum(self.staleness, stale)
        return index

    def report(self) -> dict[str, Any]:
        stale = self.staleness if self.staleness is not None else np.zeros(0)
        return {
            "time": self.mode,
            "note": self.note,
            "samples": int(self.times.size),
            "stale_max_ms": round(float(np.nanmax(stale)) * 1e3, 2) if stale.size else 0.0,
            "stale_p99_ms": round(_percentile(stale, 99) * 1e3, 2) if stale.size else 0.0,
            "missed": int(self.spec.get("stats", {}).get("missed", 0)),
        }


def convert_episode(episode: Episode, cfg: DatasetConfig) -> Converted:
    try:
        return _convert(episode, cfg)
    except (EpisodeError, KeyError) as error:
        raise ConvertError(f"{episode.name}: {error}") from error


def _convert(episode: Episode, cfg: DatasetConfig) -> Converted:
    meta = episode.meta
    arm_state = _Timed(episode, cfg.arm_state, cfg)
    arm_action = _Timed(episode, cfg.arm_action, cfg)
    hand = _Timed(episode, cfg.hand, cfg)
    boards = [_Timed(episode, name, cfg) for name in cfg.tactile]
    cameras = [_Timed(episode, name, cfg) for name in cfg.cameras]
    hand_has_feedback = np.isfinite(hand.data["pos"]).all(axis=1)
    if not hand_has_feedback.any():
        raise ConvertError(f"{episode.name}: hand stream has no position feedback at all")

    # The dataset starts when recording started and every stream has produced a sample.
    firsts = [t.times[0] for t in (arm_state, arm_action, hand, *boards, *cameras)]
    firsts.append(hand.times[np.flatnonzero(hand_has_feedback)[0]])
    start_ns = max(int(meta["start"]["mono_ns"]), *(int(f) for f in firsts))
    grid = align.make_grid(start_ns, int(meta["end_ns"]), cfg.fps)
    if grid.size < 2:
        raise ConvertError(f"{episode.name}: too short to convert ({grid.size} steps)")

    arrays: dict[str, np.ndarray] = {}
    names: dict[str, list[str]] = {}

    # ---- state and action -------------------------------------------------------------------
    hand_state_rows = hand.pick(grid, hand_has_feedback)
    hand_action_rows = hand.pick(grid)
    arm_joints = arm_state.spec["meta"]["joints"]
    if len(arm_joints) < cfg.arm_dof or len(arm_action.spec["meta"]["joints"]) < cfg.arm_dof:
        raise ConvertError(f"{episode.name}: arm streams have fewer than {cfg.arm_dof} joints")
    arrays[features.KEY_STATE] = features.joint_vector(
        arm_state.data["pos"][arm_state.pick(grid)],
        hand.data["pos"][hand_state_rows], cfg.arm_dof,
    )
    arrays[features.KEY_ACTION] = features.joint_vector(
        arm_action.data["pos"][arm_action.pick(grid)],
        hand.data[cfg.hand_action][hand_action_rows], cfg.arm_dof,
    )
    if not np.isfinite(arrays[features.KEY_ACTION]).all():
        raise ConvertError(
            f"{episode.name}: hand '{cfg.hand_action}' has missing values; "
            "use dataset.hand_action: cmd"
        )
    names[features.KEY_STATE] = names[features.KEY_ACTION] = features.joint_names(
        arm_joints, cfg.arm_dof
    )
    arrays[features.KEY_CURRENT] = hand.data["cur"][hand_state_rows].astype(np.float32)
    names[features.KEY_CURRENT] = [f"leap_{n}" for n in features.HAND_JOINTS]

    # ---- tactile ----------------------------------------------------------------------------
    if boards:
        period_ns = 1e9 / cfg.fps
        # Sub-step times for the high-rate window: the last one is the grid time itself.
        offsets = ((np.arange(cfg.tactile_hr) - (cfg.tactile_hr - 1)) * period_ns / cfg.tactile_hr)
        sub_grid = (grid[:, None] + offsets[None, :].astype(np.int64)).reshape(-1)
        now: dict[str, dict[str, np.ndarray]] = {}
        window: dict[str, dict[str, np.ndarray]] = {}
        points: dict[str, int] = {}
        clamped = 0
        for board in boards:
            layout = episode.layout(board.name)
            decoded = decode_payload(board.data["payload"], layout)
            rows = board.pick(grid)
            # Sub-steps before the board's first sample (only possible without pre-roll) reuse
            # the first sample; they are counted in the report.
            sub_rows = align.pick_latest(board.times, sub_grid)
            clamped += int((sub_rows < 0).sum())
            sub_rows = np.clip(sub_rows, 0, None)
            for module in layout.modules:
                points[module.place] = module.points
                now[module.place] = {k: v[rows] for k, v in decoded[module.place].items()}
                window[module.place] = {k: v[sub_rows] for k, v in decoded[module.place].items()}
        order = cfg.tactile_order
        resultant, distributed = features.tactile_vectors(now, order)
        resultant_hr, distributed_hr = features.tactile_vectors(window, order)
        resultant_names, distributed_names = features.tactile_names(order, points)
        arrays[features.KEY_TACTILE] = resultant
        names[features.KEY_TACTILE] = resultant_names
        arrays[features.KEY_TACTILE_DIST] = distributed
        names[features.KEY_TACTILE_DIST] = distributed_names
        steps = range(cfg.tactile_hr)
        arrays[features.KEY_TACTILE_HR] = resultant_hr.reshape(grid.size, -1)
        names[features.KEY_TACTILE_HR] = [f"t{k}.{n}" for k in steps for n in resultant_names]
        if cfg.tactile_hr_distributed:
            arrays[features.KEY_TACTILE_DIST_HR] = distributed_hr.reshape(grid.size, -1)
            names[features.KEY_TACTILE_DIST_HR] = [
                f"t{k}.{n}" for k in steps for n in distributed_names
            ]
    else:
        clamped = 0

    # ---- cameras ----------------------------------------------------------------------------
    frames: dict[str, np.ndarray] = {}
    shapes: dict[str, tuple[int, int, int]] = {}
    rotations: dict[str, int] = {}
    reuse: dict[str, int] = {}
    for camera in cameras:
        rows = camera.pick(grid)
        frames[camera.name] = rows
        cam_meta = camera.spec["meta"]
        rotations[camera.name] = int(cam_meta["rotation_deg"])
        shapes[camera.name] = features.oriented_shape(
            int(cam_meta["height"]), int(cam_meta["width"]), rotations[camera.name]
        )
        reuse[camera.name] = int((np.diff(rows) == 0).sum())

    # ---- report -----------------------------------------------------------------------------
    streams = {t.name: t.report() for t in (arm_state, arm_action, hand, *boards, *cameras)}
    for name, count in reuse.items():
        streams[name]["frames_reused"] = count
        streams[name]["dropped_write"] = int(
            episode.spec(name).get("stats", {}).get("dropped_write", 0)
        )
    worst = max(s["stale_max_ms"] for s in streams.values())
    problems = [
        f"{name}: a value was {s['stale_max_ms']:.0f} ms old (limit {cfg.max_staleness_ms:.0f})"
        for name, s in streams.items() if s["stale_max_ms"] > cfg.max_staleness_ms
    ]
    flags = meta.get("flags", {})
    for name, count in flags.get("dropouts", {}).items():
        problems.append(f"{name}: dropped out {count} time(s) while recording")
    if flags.get("forced_start"):
        problems.append("recording was started although the pre-check failed")
    report = {
        "episode": episode.name,
        "result": meta.get("result"),
        "steps": int(grid.size),
        "duration_s": round((int(grid[-1]) - int(grid[0])) / 1e9, 3),
        "skipped_start_ms": round((start_ns - int(meta["start"]["mono_ns"])) / 1e6, 1),
        "stale_max_ms": worst,
        "tactile_hr_clamped": clamped,
        "streams": streams,
        "problems": problems,
        "ok": not problems,
    }
    return Converted(grid, arrays, names, frames, shapes, rotations, report)
