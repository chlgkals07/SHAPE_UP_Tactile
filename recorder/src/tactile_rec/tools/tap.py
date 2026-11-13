"""`tactile-rec tap <episode>`: measure how far the streams are apart in time.

Record a short episode in which sharp events happen several times, with pauses:
  - close the fingers quickly from rest   -> glove, hand command, hand position, camera motion
  - tap a fingertip sensor on the table   -> tactile force, hand motor current
For every stream this finds the moment its "activity" rises, pairs the events with those of a
reference stream and prints the time differences. A positive number means the stream shows the
event LATER than the reference; put it into `dataset.latency_ms` to cancel it.

The numbers describe the recorded timestamps as they are (receive time). They include real
physical delays too (a motor moves after it is commanded), so judge each pair by what it
physically is: tactile vs motor current should be near zero, command vs position should not.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from tactile_rec.convert.load import Episode
from tactile_rec.tactile import decode_payload
from tactile_rec.types import KIND_VIDEO

REFRACTORY_S = 0.7
MATCH_WINDOW_S = 0.4


def onsets(times_s: np.ndarray, activity: np.ndarray) -> np.ndarray:
    """Times at which `activity` rises out of its resting level.

    The threshold sits halfway between the resting level (median) and the strong events (99th
    percentile). Rises closer than REFRACTORY_S to the previous one are the same event.
    Returns an empty array if the signal never clearly leaves its resting level.
    """
    activity = np.asarray(activity, dtype=np.float64)
    if activity.size < 3:
        return np.zeros(0)
    rest, peak = np.median(activity), np.percentile(activity, 99)
    spread = np.median(np.abs(activity - rest)) * 1.4826
    if peak - rest <= max(8 * spread, 1e-9):
        return np.zeros(0)
    above = activity > (rest + peak) / 2
    rising = np.flatnonzero(above[1:] & ~above[:-1]) + 1
    out: list[float] = []
    for index in rising:
        if not out or times_s[index] - out[-1] >= REFRACTORY_S:
            out.append(float(times_s[index]))
    return np.asarray(out)


def pair_offsets(reference: np.ndarray, other: np.ndarray) -> np.ndarray:
    """other - reference for each reference event that has a partner within MATCH_WINDOW_S."""
    if reference.size == 0 or other.size == 0:
        return np.zeros(0)
    out = []
    for moment in reference:
        nearest = other[np.argmin(np.abs(other - moment))]
        if abs(nearest - moment) <= MATCH_WINDOW_S:
            out.append(nearest - moment)
    return np.asarray(out)


def _speed(times_s: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Summed absolute rate of change; the first entry is 0 so lengths match."""
    values = np.nan_to_num(np.asarray(values, dtype=np.float64).reshape(len(values), -1))
    dt = np.clip(np.diff(times_s), 1e-4, None)
    rate = np.abs(np.diff(values, axis=0)).sum(axis=1) / dt
    return np.concatenate([[0.0], rate])


def activities(episode: Episode) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """{signal name: (times_s, activity)} for every stream this episode has."""
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for name in episode.streams:
        spec = episode.spec(name)
        data = episode.arrays(name)
        times = data["t_recv_ns"] / 1e9
        if times.size < 3:
            continue
        if spec["kind"] == KIND_VIDEO:
            previous, motion = None, []
            for index in range(times.size):
                small = cv2.resize(
                    cv2.cvtColor(episode.frame(name, index), cv2.COLOR_BGR2GRAY), (64, 48)
                ).astype(np.float32)
                motion.append(0.0 if previous is None else float(np.abs(small - previous).mean()))
                previous = small
            out[name] = (times, np.asarray(motion))
        elif "payload" in data:
            decoded = decode_payload(data["payload"], episode.layout(name))
            force = sum(v["distributed"][:, :, 2].sum(axis=1) for v in decoded.values())
            out[f"{name}.force"] = (times, np.asarray(force, dtype=np.float64))
        elif "cur" in data:
            current = np.nan_to_num(data["cur"])
            out[f"{name}.current"] = (times, np.abs(current - np.median(current, axis=0)).sum(axis=1))
            out[f"{name}.cmd"] = (times, _speed(times, data["cmd"]))
            out[f"{name}.pos"] = (times, _speed(times, data["pos"]))
        elif "ergo" in data:
            out[name] = (times, _speed(times, data["ergo"]))
        elif "pos" in data:
            out[name] = (times, _speed(times, data["pos"]))
    return out


def analyse(episode: Episode, reference: str | None = None) -> dict[str, Any]:
    signals = activities(episode)
    events = {name: onsets(times, activity) for name, (times, activity) in signals.items()}
    if reference is None:
        reference = max(events, key=lambda name: events[name].size, default="")
    if reference not in events:
        raise ValueError(f"no signal named {reference!r}; available: {sorted(events)}")
    rows = {}
    for name, moments in events.items():
        offsets = pair_offsets(events[reference], moments)
        rows[name] = {
            "events": int(moments.size),
            "paired": int(offsets.size),
            "offset_ms": round(float(np.median(offsets)) * 1e3, 1) if offsets.size else None,
            "spread_ms": round(float(offsets.max() - offsets.min()) * 1e3, 1)
            if offsets.size else None,
        }
    return {"reference": reference, "signals": rows}


def run(path: str, reference: str | None, out=print) -> int:
    episode = Episode(path)
    try:
        result = analyse(episode, reference)
    except ValueError as error:
        out(f"error: {error}")
        return 2
    finally:
        episode.close()
    out(f"episode   {episode.name}")
    out(f"reference {result['reference']}  (offset = signal - reference; + means later)")
    out("")
    out(f"{'signal':24s} {'events':>6s} {'paired':>6s} {'offset':>10s} {'spread':>10s}")
    for name, row in result["signals"].items():
        offset = "-" if row["offset_ms"] is None else f"{row['offset_ms']:+.1f} ms"
        spread = "-" if row["spread_ms"] is None else f"{row['spread_ms']:.1f} ms"
        out(f"{name:24s} {row['events']:6d} {row['paired']:6d} {offset:>10s} {spread:>10s}")
    if result["signals"][result["reference"]]["events"] < 3:
        out("")
        out("Few events found. Record 5 or more sharp events with a second of rest between them.")
    return 0
