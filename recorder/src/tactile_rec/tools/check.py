"""`tactile-rec check <stream>`: run one stream for a few seconds and report what arrived.

This is the first thing to run on real hardware for each device (field checklist 1-3): it
answers "does data arrive, at what rate, with what delay and how many gaps" without starting
the whole recorder.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from tactile_rec.clock import Clock
from tactile_rec.config import Config
from tactile_rec.hub import build_streams
from tactile_rec.stream import Stream
from tactile_rec.types import NO_TIME, SRC_HOST_WALL, SRC_MONO, Sample


def summarise(samples: list[Sample], spec_src_clock: str, anchor: dict[str, int]) -> dict[str, Any]:
    """Rate, interval and delay statistics of a list of samples. Pure, so it is tested."""
    out: dict[str, Any] = {"count": len(samples)}
    if len(samples) < 2:
        return out
    recv = np.array([s.t_recv_ns for s in samples], dtype=np.int64)
    gaps_ms = np.diff(recv) / 1e6
    out["hz"] = round((len(samples) - 1) / ((recv[-1] - recv[0]) / 1e9), 2)
    out["interval_ms"] = {
        "median": round(float(np.median(gaps_ms)), 2),
        "p99": round(float(np.percentile(gaps_ms, 99)), 2),
        "max": round(float(gaps_ms.max()), 2),
    }
    src_seq = np.array([s.src_seq for s in samples], dtype=np.int64)
    known = src_seq[src_seq != NO_TIME]
    out["missed"] = int(np.clip(np.diff(known) - 1, 0, None).sum()) if known.size >= 2 else 0
    src = np.array([s.t_src_ns for s in samples], dtype=np.int64)
    has = src != NO_TIME
    out["source_stamps"] = f"{int(has.sum())}/{len(samples)}"
    if has.any() and spec_src_clock in (SRC_MONO, SRC_HOST_WALL):
        # Both clocks are on this PC, so receive - source is the real delay.
        offset = 0 if spec_src_clock == SRC_MONO else anchor["mono_ns"] - anchor["wall_ns"]
        delay_ms = (recv[has] - (src[has] + offset)) / 1e6
        out["delay_ms"] = {
            "median": round(float(np.median(delay_ms)), 2),
            "max": round(float(delay_ms.max()), 2),
        }
    elif has.any():
        # Another PC's clock: only the variation of the delay is meaningful, not its value.
        delta_ms = (recv[has] - src[has]) / 1e6
        out["delay_jitter_ms"] = round(float(delta_ms.max() - delta_ms.min()), 2)
    return out


def run(config: Config, name: str, seconds: float, out=print) -> int:
    clock = Clock()
    streams = build_streams(config, clock)
    if name not in streams:
        out(f"error: no stream named {name!r}. Known: {', '.join(streams)}")
        return 2
    # hand_udp creates `hand` and `glove` together; start the stream that owns the device.
    owner = next(
        (s for s in streams.values() if getattr(s, "glove", None) is streams[name]), streams[name]
    )
    stream: Stream = streams[name]
    collected: list[Sample] = []
    stream.subscribe(collected.append)
    anchor = clock.anchor()
    owner.start()
    out(f"checking {name} for {seconds:.0f} s (expected {stream.spec.nominal_hz:.0f} Hz) ...")
    try:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            time.sleep(1.0)
            health = stream.health()
            out(f"  {health.status:6s} {health.hz:6.1f} Hz  count {health.count}"
                + (f"  {health.message}" if health.message else ""))
    finally:
        owner.stop()
    result = summarise(collected, stream.spec.src_clock, anchor)
    out("")
    for key, value in result.items():
        out(f"{key:16s} {value}")
    if collected:
        out("")
        for field, array in collected[-1].data.items():
            array = np.asarray(array)
            preview = "" if array.size > 16 else f"  {np.round(array.astype(float), 3).tolist()}"
            out(f"  {field:12s} shape {array.shape} {array.dtype}{preview}")
        for key, value in stream.spec.meta.items():
            out(f"  meta.{key}: {value}")
    expected = stream.spec.nominal_hz
    ok = result["count"] >= 2 and abs(result["hz"] - expected) <= 0.2 * expected
    out("")
    out("PASS" if ok else f"FAIL: expected about {expected:.0f} Hz"
        + ("" if result["count"] else " but nothing arrived"))
    return 0 if ok else 1
