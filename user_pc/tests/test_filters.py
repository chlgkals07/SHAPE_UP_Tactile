import numpy as np
import pytest

from leap_teleop.filters import OneEuroFilter


def test_constant_input_passes_through():
    f = OneEuroFilter()
    for t in range(1, 6):
        out = f.filter(np.full(3, 2.0), t * 0.02)
    assert out == pytest.approx([2.0, 2.0, 2.0])


def test_step_input_is_smoothed():
    f = OneEuroFilter()
    f.filter(0.0, 0.0)
    assert 0.0 < float(f.filter(10.0, 0.02)) < 10.0


def test_timestamps_must_increase():
    f = OneEuroFilter()
    f.filter(0.0, 1.0)
    with pytest.raises(ValueError):
        f.filter(0.0, 1.0)
