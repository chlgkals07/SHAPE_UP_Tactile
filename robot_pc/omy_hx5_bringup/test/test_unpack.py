"""Unpack starts must match the official poses, never an arbitrary arm pose."""

import math

from omy_hx5_bringup.unpack import PACK_POSITION, UNPACK_POSITION, allowed_start


def test_official_packed_and_unpacked_starts_are_accepted():
    assert allowed_start(PACK_POSITION)
    assert allowed_start(UNPACK_POSITION)
    assert allowed_start(tuple(x + 0.02 for x in PACK_POSITION))


def test_arbitrary_missing_and_nonfinite_arm_states_are_rejected():
    assert not allowed_start((1.0,) * 6)
    assert not allowed_start((0.0,) * 5)
    assert not allowed_start((math.nan,) * 6)
    assert not allowed_start((math.inf,) * 6)
