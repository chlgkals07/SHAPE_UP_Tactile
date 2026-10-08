import numpy as np
import pytest

from leap_teleop.app import run_teleop
from leap_teleop.config import make_posture
from leap_teleop.retarget.scalar_posture import ScalarPostureRetargeter
from leap_teleop.safety import StaleGuard
from leap_teleop.sources.base import Source
from leap_teleop.types import Reading

OPEN = np.zeros(16)
FIST = make_posture({"index_mcp_flex": 60.0})


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeSource(Source):
    def __init__(self, grasp_at, silent_after=None, stop_at=1.0):
        self._grasp_at = grasp_at
        self._silent_after = silent_after
        self._stop_at = stop_at
        self._now = 0.0
        self._latest = None
        self.closed = False

    def poll(self, now):
        # Source contract: return the latest reading (even if old); None only before the first.
        self._now = now
        if self._silent_after is None or now < self._silent_after:
            self._latest = Reading(timestamp=now, grasp=self._grasp_at(now))
        return self._latest

    @property
    def stop_requested(self):
        return self._now >= self._stop_at

    def close(self):
        self.closed = True


class FakeDriver:
    def __init__(self, clock, fail_start=False):
        self._clock = clock
        self._fail_start = fail_start
        self.started = False
        self.closed = False
        self.commands = []

    def start(self):
        if self._fail_start:
            raise OSError("no hand")
        self.started = True

    def command(self, angles):
        self.commands.append((self._clock(), np.array(angles)))

    def close(self):
        self.closed = True


def run(source, clock, driver, log=lambda _line: None):
    run_teleop(
        source,
        ScalarPostureRetargeter(OPEN, FIST),
        StaleGuard(OPEN, stale_timeout=0.5, release_timeout=3.0),
        driver,
        rate_hz=10.0,
        clock=clock,
        sleep=clock.sleep,
        log=log,
    )


def test_grasp_changes_reach_the_driver_and_everything_is_closed():
    clock = FakeClock()
    driver = FakeDriver(clock)
    source = FakeSource(lambda t: 0.0 if t < 0.5 else 1.0, stop_at=1.0)
    run(source, clock, driver)
    assert driver.started and driver.closed and source.closed
    np.testing.assert_array_equal(driver.commands[0][1], OPEN)
    np.testing.assert_array_equal(driver.commands[-1][1], FIST)


def test_silent_source_holds_then_releases_to_open():
    clock = FakeClock()
    driver = FakeDriver(clock)
    source = FakeSource(lambda t: 1.0, silent_after=0.3, stop_at=4.0)
    run(source, clock, driver)
    at_one_and_a_half = [cmd for t, cmd in driver.commands if abs(t - 1.5) < 0.05][0]
    np.testing.assert_array_equal(at_one_and_a_half, FIST)  # hold
    np.testing.assert_array_equal(driver.commands[-1][1], OPEN)  # released


def test_no_reading_at_all_keeps_the_hand_open():
    clock = FakeClock()
    driver = FakeDriver(clock)
    source = FakeSource(lambda t: 1.0, silent_after=0.0, stop_at=0.5)
    run(source, clock, driver)
    assert driver.commands
    assert all(not cmd.any() for _, cmd in driver.commands)


def test_error_in_the_loop_still_closes_source_and_driver():
    clock = FakeClock()
    driver = FakeDriver(clock)

    class Exploding(FakeSource):
        def poll(self, now):
            raise RuntimeError("boom")

    source = Exploding(lambda t: 0.0)
    with pytest.raises(RuntimeError, match="boom"):
        run(source, clock, driver)
    assert source.closed and driver.closed


def test_failed_start_closes_source_but_not_driver():
    clock = FakeClock()
    driver = FakeDriver(clock, fail_start=True)
    source = FakeSource(lambda t: 0.0)
    with pytest.raises(OSError, match="no hand"):
        run(source, clock, driver)
    assert source.closed
    assert not driver.closed
    assert driver.commands == []


def test_mode_changes_are_logged_once_each():
    clock = FakeClock()
    driver = FakeDriver(clock)
    source = FakeSource(lambda t: 1.0, silent_after=0.3, stop_at=4.0)
    lines = []
    run(source, clock, driver, log=lines.append)
    assert [line.split()[-1] for line in lines] == ["live", "hold", "release"]
