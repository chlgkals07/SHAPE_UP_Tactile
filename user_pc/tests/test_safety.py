import numpy as np
import pytest

from leap_teleop.safety import StaleGuard

OPEN = np.zeros(16)
FIST = np.full(16, 50.0)


def test_no_reading_yet_outputs_open_and_waits():
    guard = StaleGuard(OPEN)
    np.testing.assert_array_equal(guard.resolve(0.0, None, None), OPEN)
    assert guard.mode == "waiting"


def test_fresh_reading_passes_through():
    guard = StaleGuard(OPEN, stale_timeout=0.5, release_timeout=3.0)
    np.testing.assert_array_equal(guard.resolve(1.0, FIST, 0.9), FIST)
    assert guard.mode == "live"


def test_stale_reading_holds_last_output_then_releases_to_open():
    guard = StaleGuard(OPEN, stale_timeout=0.5, release_timeout=3.0)
    guard.resolve(1.0, FIST, 1.0)  # live
    np.testing.assert_array_equal(guard.resolve(1.6, FIST, 1.0), FIST)
    assert guard.mode == "hold"
    np.testing.assert_array_equal(guard.resolve(4.1, FIST, 1.0), OPEN)
    assert guard.mode == "release"


def test_recovers_when_fresh_reading_returns():
    guard = StaleGuard(OPEN)
    guard.resolve(0.0, FIST, 0.0)
    guard.resolve(5.0, FIST, 0.0)
    assert guard.mode == "release"
    np.testing.assert_array_equal(guard.resolve(5.1, FIST, 5.1), FIST)
    assert guard.mode == "live"


def test_old_first_reading_without_history_releases_instead_of_holding():
    guard = StaleGuard(OPEN, stale_timeout=0.5, release_timeout=3.0)
    np.testing.assert_array_equal(guard.resolve(2.0, FIST, 1.0), OPEN)
    assert guard.mode == "release"


def test_outputs_are_copies():
    guard = StaleGuard(OPEN)
    out = guard.resolve(0.0, None, None)
    out[0] = 99.0
    assert guard.resolve(0.0, None, None)[0] == 0.0


@pytest.mark.parametrize("stale,release", [(0.0, 1.0), (-1.0, 1.0), (2.0, 1.0)])
def test_invalid_timeouts_are_rejected(stale, release):
    with pytest.raises(ValueError):
        StaleGuard(OPEN, stale_timeout=stale, release_timeout=release)
