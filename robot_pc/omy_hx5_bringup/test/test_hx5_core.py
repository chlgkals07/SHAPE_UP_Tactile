"""Behavior checks for HX5-D20's hardware-independent teleop controller."""

import math

import pytest

from hx5_teleop.core import (
    Hx5CoreConfig,
    Hx5GraspCore,
    TactileFrame,
    joint_names,
    reference_open_pose,
)


def frame(timestamp, *, finger=None, count=0.0):
    values = [[0.0] * 9 for _ in range(5)]
    if finger is not None:
        values[finger][0] = count
    return TactileFrame(timestamp, values)


def make_core(**overrides):
    parameters = dict(
        baseline_frames=2, pressure_ema_alpha=1.0,
        max_joint_speed_rad_s=1000.0, pressure_deadband=2.0,
    )
    parameters.update(overrides)
    config = Hx5CoreConfig(**parameters)
    core = Hx5GraspCore(config)
    core.initialize((0.0,) * 20, now=0.0)
    core.step(0.0, frame(0.01), 0.01)
    core.step(0.0, frame(0.02), 0.02)
    assert core.baseline_ready
    return core


def test_official_joint_order_and_model_safe_reference_pose():
    assert joint_names("left") == tuple(f"finger_l_joint{i}" for i in range(1, 21))
    assert joint_names("right") == tuple(f"finger_r_joint{i}" for i in range(1, 21))
    assert reference_open_pose("left")[:4] == (-0.15, 1.5, 0.0, 0.0)
    assert reference_open_pose("right")[:4] == (0.297, -1.5, 0.0, 0.0)
    assert reference_open_pose("left")[4:8] == (0.0, 0.8, 0.0, 0.0)
    with pytest.raises(ValueError, match="hand_side"):
        joint_names("unknown")


def test_default_zero_bringup_pose_can_collect_baseline_before_closing():
    core = Hx5GraspCore(Hx5CoreConfig(baseline_frames=30))
    with pytest.raises(RuntimeError, match="initialize"):
        core.step(1.0, None, 0.0)
    core.initialize((0.0,) * 20, 0.0)
    assert core.command == (0.0,) * 20
    for index in range(29):
        out = core.step(0.0, frame((index + 1) * 0.01), (index + 1) * 0.01)
        assert out == (0.0,) * 20
        assert not core.baseline_ready
    core.step(0.0, frame(0.30), 0.30)
    assert core.baseline_ready
    assert core.baseline_samples == 30


def test_duplicate_samples_do_not_finish_baseline_and_trigger_must_be_released():
    core = Hx5GraspCore(Hx5CoreConfig(baseline_frames=2))
    core.initialize((0.0,) * 20, 0.0)
    core.step(1.0, frame(0.01), 0.01)
    assert core.baseline_samples == 0
    core.step(0.0, frame(0.02), 0.02)
    core.step(0.0, frame(0.02), 0.03)
    assert core.baseline_samples == 1
    core.step(0.0, frame(0.04), 0.04)
    assert core.baseline_ready


def test_stale_sample_cannot_accumulate_baseline():
    core = Hx5GraspCore(Hx5CoreConfig(baseline_frames=2, tactile_timeout_s=0.05))
    core.initialize((0.0,) * 20, 0.0)
    core.step(0.0, frame(0.01), 0.10)
    assert core.baseline_samples == 0
    core.step(0.0, frame(0.11), 0.11)
    assert core.baseline_samples == 1
    core.step(0.0, frame(0.12), 0.12)
    assert core.baseline_ready


def test_stale_new_sample_cannot_update_pressure_or_drive_closure():
    core = make_core(tactile_timeout_s=0.05)
    before = core.step(0.5, frame(0.03), 0.03)
    stale = core.step(1.0, frame(0.04, finger=1, count=20.0), 0.10)
    assert core.pressure_sums[1] == pytest.approx(0.0)
    assert stale[6] <= before[6]
    assert not core.contacted[1]


def test_scalar_grasp_interpolates_model_safe_positions_with_side_specific_thumb_sign():
    left = make_core()
    out = left.step(0.5, frame(0.03), 0.03)
    assert out[:4] == pytest.approx((-0.432, 0.432, -0.6, -0.6))
    assert out[4:8] == pytest.approx((0.0, 0.65, 0.39, 0.26))
    assert out[8:12] == pytest.approx(out[4:8])
    assert left.step(1.0, frame(0.04), 0.04)[4:8] == pytest.approx((0.0, 1.3, 0.78, 0.52))

    right = make_core(hand_side="right")
    assert right.step(0.5, frame(0.03), 0.03)[:4] == pytest.approx((0.432, -0.432, 0.6, 0.6))


def test_contact_caps_only_that_finger_and_trigger_release_opens_even_with_pressure():
    core = make_core()
    core.step(0.4, frame(0.03), 0.03)
    core.step(0.4, frame(0.04, finger=1, count=12.0), 0.04)
    assert core.contacted == (False, True, False, False, False)
    out = core.step(1.0, frame(0.05, finger=1, count=12.0), 0.05)
    assert out[6] == pytest.approx(0.312)  # Index stays at the contact pose.
    assert out[10] == pytest.approx(0.78)  # Middle finger follows the trigger.
    released = core.step(0.1, frame(0.06, finger=1, count=12.0), 0.06)
    assert released[6] == pytest.approx(0.078)
    assert released[10] == pytest.approx(0.078)


def test_contact_pressure_regulation_moves_cap_slowly_but_never_beyond_trigger():
    core = make_core()
    core.step(0.4, frame(0.03), 0.03)
    core.step(0.4, frame(0.04, finger=1, count=12.0), 0.04)
    assert core.step(1.0, frame(0.05, finger=1, count=12.0), 0.05)[6] == pytest.approx(0.312)
    under = core.step(1.0, frame(0.06, finger=1, count=5.0), 0.06)[6]
    assert 0.312 < under < 0.313  # Slow pressure correction, in radians.
    over = core.step(1.0, frame(0.07, finger=1, count=25.0), 0.07)[6]
    assert over < under
    hard = core.step(1.0, frame(0.08, finger=1, count=40.0), 0.08)[6]
    assert hard < over
    assert core.pressure_sums[1] == pytest.approx(40.0)  # Counts, not newtons.


def test_missing_leader_or_stale_tactile_never_adds_closure_but_opening_continues():
    core = make_core(tactile_timeout_s=0.05, max_joint_speed_rad_s=1.0)
    started = core.step(1.0, frame(0.03), 0.03)
    missing_leader = core.step(None, frame(0.04), 0.04)
    assert missing_leader[6] <= started[6]
    stale = core.step(1.0, None, 0.20)
    assert stale[6] <= missing_leader[6]
    opened = core.step(0.0, None, 0.21)
    assert opened[6] < stale[6]


def test_freshness_and_rate_limit_prevent_large_motion_after_a_timer_pause():
    core = make_core(max_joint_speed_rad_s=0.5, max_control_dt_s=0.1)
    out = core.step(1.0, frame(0.03), 0.03)
    assert out[6] <= 0.005 + 1e-12
    after_pause = core.step(1.0, frame(20.0), 20.0)
    assert after_pause[6] - out[6] <= 0.05 + 1e-12


def test_saturation_and_lost_contact_latch_fault_until_clean_released_frame():
    core = make_core()
    core.step(0.4, frame(0.03), 0.03)
    core.step(0.4, frame(0.04, finger=1, count=255.0), 0.04)
    assert core.faulted[1]
    before = core.command[6]
    assert core.step(1.0, frame(0.04, finger=1, count=255.0), 0.05)[6] <= before
    core.step(0.0, frame(0.04, finger=1, count=255.0), 0.06)
    assert core.faulted[1]  # Release alone does not clear a saturated sensor.
    core.step(0.0, frame(0.07), 0.07)
    assert not core.faulted[1]

    core.step(0.4, frame(0.08), 0.08)
    core.step(0.4, frame(0.09, finger=1, count=12.0), 0.09)
    assert core.contacted[1]
    core.step(1.0, frame(0.10), 0.10)
    assert core.faulted[1]  # Contact pressure disappeared; do not chase it.


def test_invalid_sensor_shapes_values_and_joint_states_are_rejected():
    with pytest.raises(ValueError, match="five fingers"):
        TactileFrame(0.0, [[0.0] * 9] * 4)
    with pytest.raises(ValueError, match="nine taxels"):
        TactileFrame(0.0, [[0.0] * 8] * 5)
    with pytest.raises(ValueError, match="taxel values"):
        TactileFrame(0.0, [[math.nan] * 9] * 5)
    with pytest.raises(ValueError, match="taxel values"):
        TactileFrame(0.0, [[256.0] * 9] * 5)
    core = Hx5GraspCore()
    with pytest.raises(ValueError, match="20 joint"):
        core.initialize([0.0] * 19, 0.0)
    with pytest.raises(ValueError, match="outside model limits"):
        core.initialize([0.0, 1.792] + [0.0] * 18, 0.0)


def test_initialize_accepts_only_tiny_simulator_noise_at_zero_limit():
    core = Hx5GraspCore()
    measured = [0.0] * 20
    measured[2] = 9e-11  # Left thumb joint3 has an upper limit of 0.
    core.initialize(measured, 0.0)
    assert core.command[2] == 0.0
    rejected = Hx5GraspCore()
    measured[2] = 1e-4
    with pytest.raises(ValueError, match="outside model limits"):
        rejected.initialize(measured, 0.0)


def test_invalid_control_input_or_timestamps_cannot_drive_closure():
    core = make_core()
    before = core.step(0.3, frame(0.03), 0.03)[6]
    assert core.step(math.nan, frame(0.04), 0.04)[6] <= before
    assert core.step(1.2, frame(0.05), 0.05)[6] <= before
    assert core.step(1.0, frame(0.10), 0.06)[6] <= before  # Future-dated sensor.
    with pytest.raises(ValueError, match="monotonic"):
        core.step(1.0, None, 0.01)


def test_config_rejects_out_of_limit_or_reversed_closing_spans():
    with pytest.raises(ValueError, match="model limits"):
        Hx5CoreConfig(open_positions=(0.0, 1.792) + (0.0,) * 18)
    with pytest.raises(ValueError, match="wrong direction"):
        Hx5CoreConfig(closing_spans=(0.0, 0.0, 0.2, 0.2) + (0.0, 0.2, 0.3, 0.3) * 4)
    with pytest.raises(ValueError, match="pressure_hard_cap"):
        Hx5CoreConfig(pressure_hard_cap=10.0)
