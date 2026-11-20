from __future__ import annotations

import numpy as np
import pytest
from tactile_rec.clock import FakeClock

from policy_runner.align_obs import ObsAligner, to_request

from conftest import passive_rig

MS = 1_000_000
AGES = {"cam_wrist": 200, "cam_ext": 200, "arm_state": 50, "hand": 100}
CAMERAS = ("cam_wrist", "cam_ext")


@pytest.fixture
def rig(tmp_path):
    clock = FakeClock(start_ns=10_000 * MS)
    hub, makers = passive_rig(tmp_path, clock)
    return hub, makers, clock


def push(hub, makers, name, t_ns, **change):
    data = makers[name].make(t_ns / 1e9)
    data.update(change)
    hub.streams[name].push(data, t_src_ns=t_ns, t_recv_ns=t_ns)


def push_all(hub, makers, t_ns, skip=()):
    for name in ("arm_state", "hand", "cam_wrist", "cam_ext", "tactile_a"):
        if name not in skip:
            push(hub, makers, name, t_ns)


def aligner(hub, **kwargs):
    return ObsAligner(hub, kwargs.pop("cameras", CAMERAS), kwargs.pop("max_age_ms", AGES),
                      kwargs.pop("max_skew_ms", 200))


def test_align_never_uses_a_sample_after_t_obs(rig):
    hub, makers, clock = rig
    t0 = clock.now_ns()
    push_all(hub, makers, t0)
    push(hub, makers, "arm_state", t0 + 10 * MS)
    obs = aligner(hub).align(t0 + 5 * MS)
    assert obs.picks["arm_state"].t_ns == t0
    assert obs.picks["arm_state"].age_ns == 5 * MS
    assert all(p.t_ns <= obs.t_obs_ns for p in obs.picks.values())


def test_state_is_arm_rad_then_hand_rad_in_float32(rig):
    hub, makers, clock = rig
    t0 = clock.now_ns()
    push_all(hub, makers, t0)
    obs = aligner(hub).align(t0)
    arm = hub.streams["arm_state"].latest().data["pos"]
    hand = hub.streams["hand"].latest().data["pos"]
    expected = np.concatenate([arm[:6], np.deg2rad(hand.astype(np.float64))]).astype(np.float32)
    assert obs.ok, obs.problems
    assert obs.state.dtype == np.float32
    assert np.array_equal(obs.state, expected)


def test_images_are_upright_rgb_copies(rig):
    hub, makers, clock = rig
    t0 = clock.now_ns()
    push_all(hub, makers, t0)
    obs = aligner(hub).align(t0)
    raw = hub.streams["cam_wrist"].latest().data["image"]
    assert obs.images["cam_wrist"].shape == (raw.shape[1], raw.shape[0], 3)
    assert obs.images["cam_ext"].shape == raw.shape
    stored = hub.streams["cam_ext"].latest().data["image"]
    assert not np.shares_memory(obs.images["cam_ext"], stored)


def test_old_stream_makes_obs_not_ok_and_names_it(rig):
    hub, makers, clock = rig
    t0 = clock.now_ns()
    push_all(hub, makers, t0)
    push_all(hub, makers, t0 + 300 * MS, skip=("cam_wrist",))
    obs = aligner(hub).align(t0 + 300 * MS)
    assert not obs.ok
    assert any("cam_wrist" in p for p in obs.problems)
    assert not any("cam_ext" in p for p in obs.problems)


def test_skew_over_budget_is_reported(rig):
    hub, makers, clock = rig
    t0 = clock.now_ns()
    push_all(hub, makers, t0)
    push_all(hub, makers, t0 + 150 * MS, skip=("cam_wrist", "cam_ext"))
    obs = aligner(hub, max_skew_ms=100).align(t0 + 150 * MS)
    assert not obs.ok
    assert any("skew" in p for p in obs.problems)


def test_missing_required_stream_is_not_zero_filled(rig):
    hub, makers, clock = rig
    t0 = clock.now_ns()
    push_all(hub, makers, t0, skip=("arm_state",))
    obs = aligner(hub).align(t0)
    assert not obs.ok
    assert obs.state is None
    assert any("arm_state" in p for p in obs.problems)


def test_missing_camera_is_not_zero_filled(rig):
    hub, makers, clock = rig
    t0 = clock.now_ns()
    push_all(hub, makers, t0, skip=("cam_ext",))
    obs = aligner(hub).align(t0)
    assert not obs.ok
    assert "cam_ext" not in obs.images
    assert any("cam_ext" in p for p in obs.problems)


def test_hand_state_skips_samples_without_feedback(rig):
    hub, makers, clock = rig
    t0 = clock.now_ns()
    push_all(hub, makers, t0)
    nan = np.full(16, np.nan, dtype=np.float32)
    push(hub, makers, "hand", t0 + 20 * MS, pos=nan)
    obs = aligner(hub).align(t0 + 20 * MS)
    assert obs.picks["hand"].t_ns == t0
    assert np.isfinite(obs.state).all()


def test_hand_without_any_feedback_is_a_problem(rig):
    hub, makers, clock = rig
    t0 = clock.now_ns()
    push_all(hub, makers, t0, skip=("hand",))
    push(hub, makers, "hand", t0, pos=np.full(16, np.nan, dtype=np.float32))
    obs = aligner(hub).align(t0)
    assert not obs.ok
    assert any("hand" in p for p in obs.problems)


def test_optional_tactile_absence_does_not_block(rig):
    hub, makers, clock = rig
    t0 = clock.now_ns()
    push_all(hub, makers, t0, skip=("tactile_a",))
    obs = aligner(hub).align(t0)
    assert obs.ok, obs.problems


def test_obs_ids_increase(rig):
    hub, makers, clock = rig
    t0 = clock.now_ns()
    push_all(hub, makers, t0)
    a = aligner(hub)
    assert a.align(t0).obs_id < a.align(t0).obs_id


def test_request_carries_state_images_and_prompt(rig):
    hub, makers, clock = rig
    t0 = clock.now_ns()
    push_all(hub, makers, t0)
    obs = aligner(hub).align(t0)
    request = to_request(obs, "Pick up the cup")
    assert set(request) == {"state", "images", "prompt"}
    assert set(request["images"]) == set(CAMERAS)
    assert request["prompt"] == "Pick up the cup"
    assert request["state"] is obs.state
