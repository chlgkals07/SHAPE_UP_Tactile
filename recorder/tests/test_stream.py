from __future__ import annotations

import threading

import numpy as np

from conftest import numeric_stream, value
from tactile_rec.clock import FakeClock
from tactile_rec.stream import ThreadedStream
from tactile_rec.streams import specs
from tactile_rec.types import STATUS_ERROR, STATUS_OFF, STATUS_OK, STATUS_SLOW, STATUS_STALE


def feed(stream, clock, hz, seconds, start=0):
    for i in range(int(hz * seconds)):
        clock.advance(1.0 / hz)
        stream.push(value(start + i))


def test_push_stamps_with_the_clock_and_counts_from_zero():
    clock = FakeClock(start_ns=5_000)
    stream = numeric_stream(clock=clock)
    first = stream.push(value(1.0))
    clock.advance(0.01)
    second = stream.push(value(2.0), t_src_ns=77)
    assert (first.t_recv_ns, first.seq) == (5_000, 0)
    assert (second.t_recv_ns, second.seq, second.t_src_ns) == (5_000 + 10_000_000, 1, 77)
    assert stream.latest() is second


def test_health_goes_off_ok_slow_stale():
    clock = FakeClock()
    stream = numeric_stream(hz=100.0, clock=clock)
    assert stream.health().status == STATUS_OFF
    feed(stream, clock, 100, 1.0)
    health = stream.health()
    assert health.status == STATUS_OK and abs(health.hz - 100) < 1
    feed(stream, clock, 50, 2.5)  # half the expected rate, long enough to fill the window
    assert stream.health().status == STATUS_SLOW
    clock.advance(1.0)
    stale = stream.health()
    assert stale.status == STATUS_STALE and stale.age_s >= 1.0


def test_error_is_reported_until_the_next_sample():
    stream = numeric_stream()
    stream.set_error("port busy")
    health = stream.health()
    assert health.status == STATUS_ERROR and health.message == "port busy"
    stream.push(value(0.0))
    assert stream.health().message == ""


def test_missed_counts_gaps_in_the_device_sequence():
    stream = numeric_stream()
    for src_seq in (10, 11, 14, 15, 20):
        stream.push(value(0.0), src_seq=src_seq)
    assert stream.health().missed == 2 + 4


def test_buffer_keeps_only_the_recent_window():
    clock = FakeClock()
    stream = numeric_stream(clock=clock)
    feed(stream, clock, 100, 5.0)
    recent = stream.recent(0)
    assert 195 <= len(recent) <= 205  # 2 s at 100 Hz
    assert recent[-1] is stream.latest()


def test_subscribe_replays_the_preroll_then_delivers_live_without_gap_or_duplicate():
    clock = FakeClock()
    stream = numeric_stream(clock=clock)
    feed(stream, clock, 100, 1.5)
    got = []
    since = clock.now_ns() - int(0.5e9)
    unsubscribe = stream.subscribe(got.append, replay_since_ns=since)
    replayed = len(got)
    assert 49 <= replayed <= 51 and got[0].t_recv_ns >= since
    feed(stream, clock, 100, 0.2, start=1000)
    seqs = [s.seq for s in got]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))  # contiguous
    assert len(got) == replayed + 20
    unsubscribe()
    stream.push(value(0.0))
    assert len(got) == replayed + 20


def test_a_failing_subscriber_does_not_stop_the_stream():
    stream = numeric_stream()

    def broken(_sample):
        raise RuntimeError("consumer bug")

    seen = []
    stream.subscribe(broken)
    stream.subscribe(seen.append)
    stream.push(value(1.0))
    assert len(seen) == 1 and stream.latest() is not None


class Flaky(ThreadedStream):
    """Fails to open twice, then yields three samples and fails once while reading."""

    retry_s = 0.01

    def __init__(self):
        super().__init__(specs.arm_spec("flaky", "joint_trajectory", ["j1", "j2"], 100, True))
        self.opens = 0
        self.closes = 0
        self.done = threading.Event()

    def _open(self):
        self.opens += 1
        if self.opens <= 2:
            raise OSError("no device")

    def _read_once(self):
        if self._count >= 3:
            self.done.set()
            self._stop_event.wait(0.01)
            return
        if self._count == 1 and self.opens == 3:
            self.opens += 0  # keep count; fail once below
            self._fail_once = getattr(self, "_fail_once", 0) + 1
            if self._fail_once == 1:
                raise OSError("unplugged")
        self.push({"pos": np.zeros(2)})

    def _close(self):
        self.closes += 1


def test_threaded_stream_reopens_after_open_and_read_failures():
    stream = Flaky()
    stream.start()
    assert stream.done.wait(3.0)
    stream.stop()
    assert stream.opens >= 4  # two failed opens, one read failure, one clean run
    assert stream.closes >= 2  # closed after the read failure and at stop
    assert stream.health().count == 3
