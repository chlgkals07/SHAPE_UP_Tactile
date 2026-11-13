"""Stream: the common shape of every device.

An adapter only has to call `push()` from its own thread. Buffering, subscriptions, rate and
gap accounting live here, so they are tested once without hardware.

Two kinds of consumer:
  latest() / recent()  - policy, monitor, preview: "what is the value now"
  subscribe()          - recorder: "every sample, in order"
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable

import numpy as np

from tactile_rec.clock import Clock
from tactile_rec.types import (
    NO_TIME,
    STATUS_ERROR,
    STATUS_OFF,
    STATUS_OK,
    STATUS_SLOW,
    STATUS_STALE,
    Health,
    Sample,
    StreamSpec,
)

Subscriber = Callable[[Sample], None]

RATE_WINDOW_S = 2.0
SLOW_FRACTION = 0.8  # below this fraction of nominal_hz the stream is "slow"


class Stream:
    def __init__(self, spec: StreamSpec, clock: Clock | None = None, buffer_s: float = 2.0):
        self.spec = spec
        self.clock = clock or Clock()
        self._lock = threading.Lock()
        self._buffer: deque[Sample] = deque()
        self._buffer_ns = int(buffer_s * 1e9)
        self._subscribers: list[Subscriber] = []
        self._count = 0
        self._missed = 0
        self._last_src_seq = NO_TIME
        self._subscriber_errors = 0
        self._error = ""
        # A stream is stale after 3 missed periods, but never sooner than 0.3 s.
        self.stale_after_s = max(3.0 / spec.nominal_hz, 0.3)

    @property
    def name(self) -> str:
        return self.spec.name

    # ---- lifecycle (adapters override) ------------------------------------------------------

    def start(self) -> None:
        """Begin producing samples. The base stream is passive (driven by push())."""

    def stop(self) -> None:
        """Stop producing samples and release the device."""

    # ---- producer side ----------------------------------------------------------------------

    def push(
        self,
        data: dict[str, np.ndarray],
        *,
        t_src_ns: int = NO_TIME,
        src_seq: int = NO_TIME,
        t_recv_ns: int | None = None,
    ) -> Sample:
        """Stamp and publish one reading. Call this as soon as the reading is in hand."""
        if t_recv_ns is None:
            t_recv_ns = self.clock.now_ns()
        with self._lock:
            sample = Sample(t_recv_ns, self._count, data, t_src_ns, src_seq)
            self._count += 1
            if src_seq != NO_TIME:
                if self._last_src_seq != NO_TIME and src_seq > self._last_src_seq + 1:
                    self._missed += src_seq - self._last_src_seq - 1
                self._last_src_seq = src_seq
            self._buffer.append(sample)
            horizon = t_recv_ns - self._buffer_ns
            while len(self._buffer) > 1 and self._buffer[0].t_recv_ns < horizon:
                self._buffer.popleft()
            self._error = ""
            # Subscribers run under the lock so that subscribe(replay_since_ns=...) can hand
            # over the buffered samples and the live ones without a gap or a duplicate.
            for fn in self._subscribers:
                try:
                    fn(sample)
                except Exception:  # noqa: BLE001 - a consumer must never stop the device thread
                    self._subscriber_errors += 1
        return sample

    def set_error(self, message: str) -> None:
        with self._lock:
            self._error = message

    # ---- consumer side ----------------------------------------------------------------------

    def latest(self) -> Sample | None:
        with self._lock:
            return self._buffer[-1] if self._buffer else None

    def recent(self, since_ns: int) -> list[Sample]:
        with self._lock:
            return [s for s in self._buffer if s.t_recv_ns >= since_ns]

    def subscribe(self, fn: Subscriber, replay_since_ns: int | None = None) -> Callable[[], None]:
        """Call `fn` for every new sample. With replay_since_ns, first replay the buffered
        samples from that time on (used for the pre-roll). Returns an unsubscribe function."""
        with self._lock:
            if replay_since_ns is not None:
                for sample in self._buffer:
                    if sample.t_recv_ns >= replay_since_ns:
                        fn(sample)
            self._subscribers.append(fn)

        def unsubscribe() -> None:
            with self._lock:
                if fn in self._subscribers:
                    self._subscribers.remove(fn)

        return unsubscribe

    def health(self, now_ns: int | None = None) -> Health:
        if now_ns is None:
            now_ns = self.clock.now_ns()
        with self._lock:
            count, missed, error = self._count, self._missed, self._error
            last = self._buffer[-1].t_recv_ns if self._buffer else None
            window_start = now_ns - int(RATE_WINDOW_S * 1e9)
            in_window = [s.t_recv_ns for s in self._buffer if s.t_recv_ns >= window_start]
        if error:
            age = None if last is None else (now_ns - last) / 1e9
            return Health(STATUS_ERROR, 0.0, age, count, missed, error)
        if last is None:
            return Health(STATUS_OFF, 0.0, None, count, missed)
        age_s = (now_ns - last) / 1e9
        # Rate over the samples actually seen in the window. With fewer than two samples the
        # span is undefined, so report 0 rather than a made-up number.
        hz = 0.0
        if len(in_window) >= 2 and in_window[-1] > in_window[0]:
            hz = (len(in_window) - 1) / ((in_window[-1] - in_window[0]) / 1e9)
        if age_s > self.stale_after_s:
            return Health(STATUS_STALE, hz, age_s, count, missed)
        if hz < SLOW_FRACTION * self.spec.nominal_hz:
            return Health(STATUS_SLOW, hz, age_s, count, missed)
        return Health(STATUS_OK, hz, age_s, count, missed)


class ThreadedStream(Stream):
    """A stream that owns a device and a reader thread.

    Subclasses implement `_open`, `_read_once` and `_close`. If the device fails, the error is
    shown in health() and the thread reopens it after a pause, so a replugged sensor comes back
    without restarting the recorder.
    """

    retry_s = 1.0

    def __init__(self, spec: StreamSpec, clock: Clock | None = None, buffer_s: float = 2.0):
        super().__init__(spec, clock, buffer_s)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name=f"stream-{self.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._thread = None

    @property
    def stopping(self) -> bool:
        return self._stop_event.is_set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._open()
            except Exception as error:  # noqa: BLE001 - reported through health()
                self.set_error(f"open failed: {error}")
                self._stop_event.wait(self.retry_s)
                continue
            try:
                while not self._stop_event.is_set():
                    self._read_once()
            except Exception as error:  # noqa: BLE001 - reported through health()
                self.set_error(f"read failed: {error}")
            finally:
                try:
                    self._close()
                except Exception:  # noqa: BLE001 - best-effort release
                    pass
            self._stop_event.wait(self.retry_s)

    def _open(self) -> None:
        raise NotImplementedError

    def _read_once(self) -> None:
        """Block for at most a short timeout, then push() zero or one sample."""
        raise NotImplementedError

    def _close(self) -> None:
        raise NotImplementedError
