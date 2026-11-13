"""Raw episodes -> a dataset on disk.

Two outputs:
  lerobot  LeRobot v2.1, written with the `lerobot` version that openpi pins. Run this inside
           the openpi environment (training server); `lerobot` is imported only here.
  npz      one .npz per episode with the same arrays. No extra dependency; used for checking
           the alignment and by our own training code.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from tactile_rec import features
from tactile_rec.config import DatasetConfig
from tactile_rec.convert.episode import ConvertError, Converted, convert_episode
from tactile_rec.convert.load import Episode, find_episodes

Log = Callable[[str], None]


def lerobot_features(
    converted: Converted, image_mode: str = "image"
) -> dict[str, dict[str, Any]]:
    """Feature definitions in the form LeRobotDataset.create() expects (v2.1)."""
    out: dict[str, dict[str, Any]] = {}
    for key, array in converted.arrays.items():
        out[key] = {
            "dtype": "float32", "shape": (int(array.shape[1]),), "names": converted.names[key]
        }
    for camera, shape in converted.image_shapes.items():
        out[features.KEY_IMAGE + camera] = {
            "dtype": image_mode, "shape": tuple(shape), "names": ["height", "width", "channel"]
        }
    return out


def iter_frames(converted: Converted, episode: Episode, text: str):
    """Yield one dataset row per grid step: arrays, upright RGB images and the task text."""
    last: dict[str, tuple[int, np.ndarray]] = {}
    for step in range(converted.steps):
        row: dict[str, Any] = {key: array[step] for key, array in converted.arrays.items()}
        for camera, index in converted.frames.items():
            frame_index = int(index[step])
            if camera not in last or last[camera][0] != frame_index:  # decode each frame once
                image = features.orient_image(
                    episode.frame(camera, frame_index), converted.rotations[camera]
                )
                last[camera] = (frame_index, image)
            row[features.KEY_IMAGE + camera] = last[camera][1]
        row["task"] = text
        yield row


class NpzWriter:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        self.count = 0

    def add(self, converted: Converted, episode: Episode, text: str) -> None:
        arrays = {key: array for key, array in converted.arrays.items()}
        arrays["timestamp_ns"] = converted.grid_ns
        for camera, index in converted.frames.items():
            arrays[f"frame_index.{camera}"] = index
        name = f"episode_{self.count:06d}"
        np.savez(self.out_dir / f"{name}.npz", **arrays)
        info = {
            "source": str(episode.path), "task": text, "names": converted.names,
            "image_shapes": converted.image_shapes, "rotations": converted.rotations,
        }
        (self.out_dir / f"{name}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        self.count += 1

    def finish(self) -> None:
        pass


class LeRobotV21Writer:
    """Writes with LeRobotDataset.create / add_frame / save_episode (the v2.1 API that openpi's
    own conversion examples use)."""

    def __init__(
        self, repo_id: str, root: Path, fps: float, robot_type: str, image_mode: str = "image",
        dataset_cls: Any = None,
    ):
        if dataset_cls is None:
            try:
                from lerobot.common.datasets.lerobot_dataset import LeRobotDataset as dataset_cls
            except ImportError as error:
                raise ConvertError(
                    "lerobot is not installed here. Run the conversion inside the openpi "
                    "environment (it pins the v2.1 lerobot), or use --format npz."
                ) from error
        if fps != int(fps):
            raise ConvertError(f"LeRobot needs an integer fps, got {fps}")
        self._cls = dataset_cls
        self._args = {"repo_id": repo_id, "root": root, "fps": int(fps), "robot_type": robot_type}
        self.image_mode = image_mode
        self.dataset: Any = None
        self.features: dict[str, Any] = {}
        self.count = 0

    def add(self, converted: Converted, episode: Episode, text: str) -> None:
        wanted = lerobot_features(converted, self.image_mode)
        if self.dataset is None:
            self.features = wanted
            extra = {"image_writer_threads": 4} if converted.frames else {}
            self.dataset = self._cls.create(features=wanted, **self._args, **extra)
        elif wanted != self.features:
            changed = sorted(k for k in set(wanted) | set(self.features)
                             if wanted.get(k) != self.features.get(k))
            raise ConvertError(
                f"{episode.name}: features differ from the first episode in {changed} "
                "(different sensors, camera size or joints cannot share one dataset)"
            )
        for row in iter_frames(converted, episode, text):
            self.dataset.add_frame(row)
        self.dataset.save_episode()
        self.count += 1

    def finish(self) -> None:
        pass


def convert_many(
    inputs: list[Path],
    cfg: DatasetConfig,
    writer: NpzWriter | LeRobotV21Writer,
    *,
    include_failed: bool = False,
    include_flagged: bool = False,
    log: Log = print,
) -> dict[str, Any]:
    """Convert every episode under `inputs`. Returns the conversion report."""
    paths = [p for root in inputs for p in find_episodes(root)]
    if not paths:
        raise ConvertError(f"no episodes found under {[str(p) for p in inputs]}")
    reports: list[dict[str, Any]] = []
    mounts: dict[str, str] = {}
    written = 0
    for path in paths:
        episode = Episode(path)
        try:
            mount = str(episode.meta.get("mount", ""))
            mounts.setdefault(mount, episode.name)
            if len(mounts) > 1:
                raise ConvertError(
                    "episodes with different mounts cannot be mixed in one dataset: "
                    + ", ".join(f"{m!r} (e.g. {e})" for m, e in mounts.items())
                )
            result = episode.meta.get("result")
            if result != "success" and not include_failed:
                reports.append({"episode": episode.name, "result": result, "skipped": "not success"})
                log(f"skip  {episode.name}: labelled {result}")
                continue
            try:
                converted = convert_episode(episode, cfg)
            except ConvertError as error:
                reports.append({"episode": episode.name, "result": result, "skipped": str(error)})
                log(f"skip  {episode.name}: {error}")
                continue
            report = converted.report
            if not report["ok"] and not include_flagged:
                report["skipped"] = "; ".join(report["problems"])
                reports.append(report)
                log(f"skip  {episode.name}: {report['skipped']}")
                continue
            writer.add(converted, episode, str(episode.meta.get("text") or episode.meta["task"]))
            written += 1
            reports.append(report)
            log(
                f"ok    {episode.name}: {report['steps']} steps, "
                f"oldest value {report['stale_max_ms']:.0f} ms"
            )
        finally:
            episode.close()
    writer.finish()
    return {
        "found": len(paths),
        "written": written,
        "skipped": len(paths) - written,
        "mount": next(iter(mounts), ""),
        "fps": cfg.fps,
        "episodes": reports,
    }


def prepare_output(path: Path, overwrite: bool) -> None:
    if path.exists():
        if not overwrite:
            raise ConvertError(f"{path} already exists (use --overwrite to replace it)")
        shutil.rmtree(path)
