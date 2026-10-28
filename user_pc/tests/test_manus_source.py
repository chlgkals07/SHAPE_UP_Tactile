import numpy as np

from leap_teleop.sources.manus import KEYPOINT_NODES, human_from_glove
from leap_teleop.types import HUMAN_ANGLE_NAMES, KEYPOINT_NAMES

ERGONOMICS = {f"RightFinger{name}": float(i) for i, name in enumerate(HUMAN_ANGLE_NAMES)}
NODES = {KEYPOINT_NODES[name]: (i, i, i) for i, name in enumerate(KEYPOINT_NAMES)}


def test_reads_angles_by_name_with_a_side_prefix():
    human = human_from_glove(ERGONOMICS)
    assert human.angles.tolist() == list(range(20))
    assert human.keypoints is None


def test_reads_keypoints_in_keypoint_order():
    human = human_from_glove(ERGONOMICS, NODES)
    i = float(KEYPOINT_NAMES.index("thumb_tip"))
    assert human.point("thumb_tip").tolist() == [i, i, i]


def test_missing_angle_gives_no_reading():
    partial = dict(ERGONOMICS)
    partial.pop("RightFingerIndexPIPStretch")
    assert human_from_glove(partial) is None


def test_nan_angle_gives_no_reading():
    bad = dict(ERGONOMICS, RightFingerIndexPIPStretch=float("nan"))
    assert human_from_glove(bad) is None


def test_missing_or_bad_keypoints_only_drop_the_keypoints():
    partial = dict(NODES)
    partial.pop(KEYPOINT_NODES["thumb_tip"])
    assert human_from_glove(ERGONOMICS, partial).keypoints is None
    bad = dict(NODES)
    bad[KEYPOINT_NODES["wrist"]] = (np.nan, 0.0, 0.0)
    assert human_from_glove(ERGONOMICS, bad).keypoints is None


def test_renamed_ergonomics_types_are_accepted():
    renamed = dict(ERGONOMICS)
    renamed["RightFingerThumbSpread"] = renamed.pop("RightFingerThumbMCPSpread")
    assert human_from_glove(renamed).angles.tolist() == list(range(20))
