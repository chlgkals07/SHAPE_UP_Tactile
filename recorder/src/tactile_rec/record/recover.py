"""Unsaved episodes: `ep_NNNN.tmp` folders left behind when the recorder was closed, a write
failed or the PC went down.

Two kinds are found on disk:
  stopped   episode.json is there (the recorder stopped the episode before it ended);
            only the success / failure label is missing.
  cut off   only recording.json and the chunk files are there (the recorder died while
            recording). `finalize()` joins the chunks and writes episode.json; the episode
            ends at its last sample that reached the disk and is flagged `recovered`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from tactile_rec.record.session import (
    EPISODE_FILE,
    EPISODE_PREFIX,
    PROGRESS_FILE,
    TMP_SUFFIX,
    write_json,
)
from tactile_rec.record.writer import PARTS_DIR, assemble


class RecoverError(ValueError):
    pass


def pending_episodes(session_dir: Path) -> list[Path]:
    """Unsaved episode folders of a session, in order."""
    if not session_dir.is_dir():
        return []
    return sorted(
        p for p in session_dir.iterdir()
        if p.is_dir() and p.name.startswith(EPISODE_PREFIX) and p.name.endswith(TMP_SUFFIX)
    )


def describe(tmp_dir: Path) -> dict[str, Any] | None:
    """episode.json of an unsaved episode, or the recording header of one that was cut off
    (then without `end_ns` and stream statistics). None if the folder holds neither."""
    for name in (EPISODE_FILE, PROGRESS_FILE):
        try:
            return json.loads((tmp_dir / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None


def finalize(tmp_dir: Path) -> dict[str, Any]:
    """Make sure the folder has an episode.json, building it from the chunks if the recorder
    never wrote one. Returns the episode metadata. Safe to call again after a failure."""
    episode_file = tmp_dir / EPISODE_FILE
    if episode_file.is_file():
        return json.loads(episode_file.read_text(encoding="utf-8"))
    try:
        meta = json.loads((tmp_dir / PROGRESS_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RecoverError(f"{tmp_dir}: nothing to recover ({error})") from error
    start_ns = int(meta["start"]["mono_ns"])
    end_ns = start_ns
    errors: dict[str, str] = {}
    for name, spec in meta["streams"].items():
        try:
            spec["stats"] = assemble(tmp_dir, spec)
            with np.load(tmp_dir / f"{name}.npz") as data:
                if data["t_recv_ns"].size:
                    end_ns = max(end_ns, int(data["t_recv_ns"][-1]))
        except Exception as error:  # noqa: BLE001 - a damaged chunk costs that stream only
            spec["stats"] = {"count": 0, "hz": 0.0, "max_gap_ms": 0.0, "missed": 0}
            errors[name] = f"{type(error).__name__}: {error}"
    try:
        (tmp_dir / PARTS_DIR).rmdir()
    except OSError:  # absent, or chunks that could not be joined are still there
        pass
    meta["end_ns"] = end_ns
    meta["duration_s"] = round((end_ns - start_ns) / 1e9, 3)
    meta["flags"] = {**meta.get("flags", {}), "recovered": True, "write_errors": errors}
    write_json(episode_file, meta)
    (tmp_dir / PROGRESS_FILE).unlink(missing_ok=True)
    return meta


def keep(tmp_dir: Path, result: str) -> Path:
    """Label an unsaved episode and move it to its final name. Returns the new folder."""
    if result not in ("success", "failure"):
        raise RecoverError("result must be success or failure")
    meta = finalize(tmp_dir)
    meta["result"] = result
    write_json(tmp_dir / EPISODE_FILE, meta)
    final = tmp_dir.with_name(tmp_dir.name.removesuffix(TMP_SUFFIX))
    if final.exists():
        raise RecoverError(f"{final} already exists")
    tmp_dir.rename(final)
    return final
