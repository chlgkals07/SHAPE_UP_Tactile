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


def test_old_manus_names_are_rejected():
    old = dict(ERGONOMICS)
    old["RightFingerThumbMCPSpread"] = old.pop("RightFingerThumbSpread")
    assert human_from_glove(old) is None


def test_frozen_feed_stops_updating_the_reading():
    import threading
    from types import SimpleNamespace as NS

    from leap_teleop.sources.manus import FROZEN_AFTER_S, Ros2ManusSource

    t = [0.0]
    src = object.__new__(Ros2ManusSource)  # skip rclpy setup
    src._side, src._clock, src._lock = "Right", lambda: t[0], threading.Lock()
    src._latest, src._last_values, src._changed_at = None, None, 0.0
    msg = NS(
        side="Right", raw_nodes=[],
        ergonomics=[NS(type=k, value=v) for k, v in ERGONOMICS.items()],
    )
    src._on_message(msg)
    assert src._latest.timestamp == 0.0
    t[0] = FROZEN_AFTER_S + 0.1
    src._on_message(msg)  # identical values for too long -> not refreshed
    assert src._latest.timestamp == 0.0
    msg.ergonomics[0].value += 1.0
    src._on_message(msg)  # a change revives it
    assert src._latest.timestamp == t[0]
