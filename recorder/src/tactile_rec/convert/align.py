"""Time alignment. Pure numpy: no files, no hardware.

All times are int64 nanoseconds on the recording PC's monotonic clock unless said otherwise.
The rule is causal: a grid step only ever uses samples whose time is <= the step time.
"""

from __future__ import annotations

import numpy as np

from tactile_rec.types import NO_TIME, SRC_HOST_WALL, SRC_MONO, SRC_NONE

TIME_RECV = "recv"  # when the sample reached the recorder
TIME_SRC = "src"  # the device's own stamp, mapped onto the recorder clock
TIME_RESPREAD = "respread"  # recv, with USB bunching removed (samples one period apart)
TIME_MODES = (TIME_RECV, TIME_SRC, TIME_RESPREAD)


def make_grid(start_ns: int, end_ns: int, fps: float) -> np.ndarray:
    """Step times start, start + 1/fps, ... not later than end. Empty if end < start."""
    if fps <= 0:
        raise ValueError("fps must be positive")
    if end_ns < start_ns:
        return np.zeros(0, dtype=np.int64)
    steps = int(np.floor((end_ns - start_ns) * fps / 1e9)) + 1
    # Multiply before dividing so the grid does not drift by rounding each period.
    return start_ns + (np.arange(steps, dtype=np.int64) * 1_000_000_000 / fps).astype(np.int64)


def pick_latest(times_ns: np.ndarray, grid_ns: np.ndarray) -> np.ndarray:
    """For each grid time, the index of the last sample at or before it; -1 if there is none.

    times_ns must be non-decreasing (see monotone()).
    """
    return np.searchsorted(times_ns, grid_ns, side="right").astype(np.int64) - 1


def staleness_s(times_ns: np.ndarray, grid_ns: np.ndarray, index: np.ndarray) -> np.ndarray:
    """How old the picked sample is at each grid time, in seconds. NaN where nothing was picked."""
    out = np.full(grid_ns.shape, np.nan, dtype=np.float64)
    ok = index >= 0
    out[ok] = (grid_ns[ok] - times_ns[index[ok]]) / 1e9
    return out


def monotone(times_ns: np.ndarray) -> np.ndarray:
    """Clamp any backwards step so the array is non-decreasing (needed for searchsorted)."""
    return np.maximum.accumulate(np.asarray(times_ns, dtype=np.int64))


def estimate_period(recv_ns: np.ndarray) -> float:
    """Sample period of a constant-rate device, from receive times that may be bunched and may
    have lost frames.

    Samples that arrive together form a burst. A burst of n samples that ends at time e, after
    a burst that ended at e_prev, covers n periods: (e - e_prev) / n. A burst that follows lost
    frames gives a value that is too long, so a value just below the median over all bursts is
    used. The plain mean interval would be too long whenever frames were lost, and a period
    that is too long makes respread() move samples earlier than they were produced; erring
    slightly short is the safe side.
    """
    recv_ns = np.asarray(recv_ns, dtype=np.int64)
    count = recv_ns.size
    mean = float(recv_ns[-1] - recv_ns[0]) / max(1, count - 1)
    if count < 4 or mean <= 0:
        return mean
    last_of_burst = np.flatnonzero(np.diff(recv_ns) > 0.25 * mean)  # index of each burst's end
    ends = np.append(last_of_burst, count - 1)
    if ends.size < 3:
        return mean
    sizes = np.diff(ends)  # samples in each burst after the first
    spans = np.diff(recv_ns[ends])
    return float(np.percentile(spans / sizes, 40))


def respread(recv_ns: np.ndarray, period_ns: float | None = None) -> tuple[np.ndarray, bool]:
    """Undo USB bunching for a constant-rate device.

    A serial device that emits at a steady rate can arrive in bursts, so several samples share
    nearly the same receive time. Sample i was produced at least one period before sample i+1,
    so working backwards from the end:   t[i] = min(recv[i], t[i+1] - period).
    Inside a burst this spaces the samples one period apart, ending at the burst's receive
    time. Outside a burst nothing changes.

    This can only move a sample EARLIER than it was received, and never earlier than it was
    produced: if frames were lost between i and i+1 the true spacing is larger than one period,
    so the bound is merely looser. A dataset step therefore never sees a tactile value from its
    own future, with or without lost frames.

    period_ns defaults to estimate_period(). Returns (times, True); the flag is kept for
    callers that report whether a fallback was used.
    """
    recv_ns = np.asarray(recv_ns, dtype=np.int64)
    count = recv_ns.size
    if count < 3 or recv_ns[-1] <= recv_ns[0]:
        return recv_ns.copy(), True
    if period_ns is None:
        period_ns = estimate_period(recv_ns)
    # t[i] = min over j >= i of (recv[j] - (j - i) * period), computed as a running minimum of
    # (recv[j] - j * period) from the right.
    index = np.arange(count, dtype=np.float64)
    slack = recv_ns - index * period_ns
    times = np.minimum.accumulate(slack[::-1])[::-1] + index * period_ns
    return np.minimum(times.astype(np.int64), recv_ns), True


def src_on_recorder_clock(
    recv_ns: np.ndarray,
    src_ns: np.ndarray,
    src_clock: str,
    anchor: dict[str, int] | None = None,
) -> np.ndarray:
    """Map device stamps onto the recorder's monotonic clock.

    mono       -> used as is (another process on the same PC).
    host_wall  -> shifted by the episode's (monotonic, wall) anchor.
    otherwise  -> shifted so the least-delayed sample lands on its receive time. This leaves a
                  constant bias equal to the smallest transport delay in the episode, which the
                  per-stream latency setting can remove once measured.
    Samples without a stamp fall back to their receive time.
    """
    recv_ns = np.asarray(recv_ns, dtype=np.int64)
    src_ns = np.asarray(src_ns, dtype=np.int64)
    has_src = src_ns != NO_TIME
    if src_clock == SRC_NONE or not has_src.any():
        return recv_ns.copy()
    if src_clock == SRC_MONO:
        offset = 0
    elif src_clock == SRC_HOST_WALL and anchor is not None:
        offset = int(anchor["mono_ns"]) - int(anchor["wall_ns"])
    else:
        offset = int(np.min(recv_ns[has_src] - src_ns[has_src]))
    out = recv_ns.copy()
    out[has_src] = src_ns[has_src] + offset
    return out


def stream_times(
    recv_ns: np.ndarray,
    src_ns: np.ndarray,
    *,
    mode: str = TIME_RECV,
    src_clock: str = SRC_NONE,
    anchor: dict[str, int] | None = None,
    latency_ns: int = 0,
) -> tuple[np.ndarray, str]:
    """Sample times to align on, and a note ("" or why a fallback was used)."""
    if mode not in TIME_MODES:
        raise ValueError(f"unknown time mode {mode!r}; choose from {TIME_MODES}")
    note = ""
    if mode == TIME_SRC:
        if src_clock == SRC_NONE:
            times, note = np.asarray(recv_ns, dtype=np.int64).copy(), "no source stamp; used recv"
        else:
            times = src_on_recorder_clock(recv_ns, src_ns, src_clock, anchor)
    elif mode == TIME_RESPREAD:
        times, _ = respread(recv_ns)
    else:
        times = np.asarray(recv_ns, dtype=np.int64).copy()
    return monotone(times - int(latency_ns)), note
