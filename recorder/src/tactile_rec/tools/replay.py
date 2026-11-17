"""`tactile-rec replay <episode>`: look at a recorded episode in the Rerun viewer.

Every stream is logged on one timeline (seconds since recording started) at its own receive
times, so what you see is the raw data before any alignment: camera frames (upright), tactile
resultant force per sensor, hand command vs position, motor current, arm joints.

Needs `pip install rerun-sdk` (the `viz` extra). Use --save to write an .rrd file instead of
opening the viewer, e.g. on a PC without a display.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from tactile_rec import features
from tactile_rec.convert.load import Episode
from tactile_rec.tactile import decode_payload, to_newtons
from tactile_rec.types import KIND_VIDEO

TIMELINE = "time"


def _set_time(rr: Any, seconds: float) -> None:
    # The time API was renamed in rerun 0.23; support both.
    if hasattr(rr, "set_time"):
        rr.set_time(TIMELINE, duration=seconds)
    else:
        rr.set_time_seconds(TIMELINE, seconds)


def _scalar(rr: Any, value: float) -> Any:
    return rr.Scalars(value) if hasattr(rr, "Scalars") else rr.Scalar(value)


def log_episode(rr: Any, episode: Episode, image_stride: int = 1) -> dict[str, int]:
    """Log the episode into the current Rerun recording. Returns how many items per stream."""
    start_ns = int(episode.meta["start"]["mono_ns"])
    counts: dict[str, int] = {}
    for name in episode.streams:
        spec = episode.spec(name)
        data = episode.arrays(name)
        seconds = (data["t_recv_ns"] - start_ns) / 1e9
        count = 0
        if spec["kind"] == KIND_VIDEO:
            rotation = int(spec["meta"].get("rotation_deg", 0))
            for index in range(0, seconds.size, image_stride):
                _set_time(rr, float(seconds[index]))
                rr.log(f"camera/{name}", rr.Image(
                    features.orient_image(episode.frame(name, index), rotation)
                ))
                count += 1
        elif "payload" in data:
            decoded = decode_payload(data["payload"], episode.layout(name))
            for place, values in decoded.items():
                newtons = to_newtons(values["resultant"])
                for index in range(seconds.size):
                    _set_time(rr, float(seconds[index]))
                    for axis, column in zip(("fx", "fy", "fz"), newtons[index], strict=True):
                        rr.log(f"tactile/{place}/{axis}", _scalar(rr, float(column)))
                    count += 1
        else:
            for field in ("cmd", "pos", "cur", "ergo"):
                if field not in data:
                    continue
                values = np.nan_to_num(np.asarray(data[field], dtype=np.float64))
                for index in range(seconds.size):
                    _set_time(rr, float(seconds[index]))
                    for joint in range(values.shape[1]):
                        value = float(values[index, joint])
                        rr.log(f"{name}/{field}/{joint:02d}", _scalar(rr, value))
                    count += 1
        counts[name] = count
    return counts


def run(path: str, save: str | None, image_stride: int, out=print) -> int:
    try:
        import rerun as rr
    except ImportError:
        out("error: rerun is not installed. Run: pip install rerun-sdk")
        return 2
    episode = Episode(path)
    rr.init("tactile_rec_" + episode.name.replace("/", "_"), spawn=save is None)
    if save is not None:
        rr.save(save)
    try:
        counts = log_episode(rr, episode, image_stride)
    finally:
        episode.close()
    for name, count in counts.items():
        out(f"{name:12s} {count} items")
    if save is not None:
        out(f"saved {save}  (open with: rerun {save})")
    return 0
