"""Read a recorded episode folder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from tactile_rec.record.session import EPISODE_PREFIX, TMP_SUFFIX
from tactile_rec.tactile import TactileLayout


class EpisodeError(ValueError):
    pass


class Episode:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        meta_path = self.path / "episode.json"
        if not meta_path.is_file():
            raise EpisodeError(f"{self.path}: not an episode folder (no episode.json)")
        self.meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        self._arrays: dict[str, dict[str, np.ndarray]] = {}
        self._video: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return f"{self.path.parent.name}/{self.path.name}"

    @property
    def streams(self) -> list[str]:
        return list(self.meta["streams"])

    def spec(self, name: str) -> dict[str, Any]:
        try:
            return self.meta["streams"][name]
        except KeyError:
            raise EpisodeError(f"{self.name}: stream {name!r} was not recorded") from None

    def arrays(self, name: str) -> dict[str, np.ndarray]:
        if name not in self._arrays:
            self.spec(name)
            with np.load(self.path / f"{name}.npz") as data:
                self._arrays[name] = {key: data[key] for key in data.files}
        return self._arrays[name]

    def layout(self, name: str) -> TactileLayout:
        meta = self.spec(name)["meta"]
        if "layout" not in meta:
            raise EpisodeError(f"{self.name}: {name} has no tactile layout (board never connected)")
        return TactileLayout.from_json(meta["layout"])

    def frame(self, name: str, index: int) -> np.ndarray:
        """Stored camera frame `index` as BGR, exactly as captured."""
        arrays = self.arrays(name)
        if name not in self._video:
            self._video[name] = (self.path / f"{name}.mjpeg").open("rb")
        file = self._video[name]
        file.seek(int(arrays["offset"][index]))
        raw = file.read(int(arrays["size"][index]))
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise EpisodeError(f"{self.name}: {name} frame {index} cannot be decoded")
        return image

    def events(self) -> list[dict[str, Any]]:
        path = self.path / "events.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def close(self) -> None:
        for file in self._video.values():
            file.close()
        self._video = {}


def find_episodes(root: str | Path) -> list[Path]:
    """Episode folders under root: root may be an episode, a session, a task or the data root."""
    root = Path(root)
    if (root / "episode.json").is_file():
        return [root]
    found = [
        p.parent for p in root.rglob("episode.json")
        if p.parent.name.startswith(EPISODE_PREFIX) and not p.parent.name.endswith(TMP_SUFFIX)
    ]
    return sorted(found)
