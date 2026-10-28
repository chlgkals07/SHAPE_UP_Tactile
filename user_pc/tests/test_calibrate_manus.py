from dataclasses import replace

import numpy as np
import pytest

from leap_teleop.tools.calibrate_manus import fist_thumb_sides_mm, hand_scale, median_hand
from leap_teleop.types import HumanHand
from test_manus_leap import CAL, CFG, CHAIN, FIST, leap_keypoints, make


def test_median_ignores_a_single_glitch():
    good = HumanHand(np.ones(20))
    glitch = HumanHand(np.full(20, 99.0))
    assert median_hand([good, good, glitch]).angles == pytest.approx(np.ones(20))


def test_median_drops_keypoints_unless_every_frame_has_them():
    with_points = HumanHand(np.zeros(20), np.zeros((7, 3)))
    without = HumanHand(np.zeros(20))
    assert median_hand([with_points, without]).keypoints is None


def test_median_needs_samples():
    with pytest.raises(ValueError):
        median_hand([])


def test_scale_is_one_for_a_leap_sized_hand_and_tracks_hand_size():
    leap_hand = HumanHand(np.zeros(20), leap_keypoints(np.zeros(4)))
    assert hand_scale(CHAIN, leap_hand) == pytest.approx(1.0)
    small = HumanHand(np.zeros(20), leap_keypoints(np.zeros(4)) / 1.6)
    assert hand_scale(CHAIN, small) == pytest.approx(1.6)


def test_fist_check_agrees_for_matching_hands_and_flags_a_mirror():
    fist_thumb = FIST[12:16]
    fist_hand = HumanHand(np.zeros(20), leap_keypoints(np.radians(fist_thumb)))
    cal = replace(CAL, scale=1.0)
    target, leap = fist_thumb_sides_mm(make("ik", cal=cal), fist_hand, fist_thumb)
    assert target == pytest.approx(leap, abs=1.0) and leap > 0
    mirrored = make("ik", cfg=replace(CFG, flip_normal=True), cal=cal)
    target, leap = fist_thumb_sides_mm(mirrored, fist_hand, fist_thumb)
    assert target * leap < 0
