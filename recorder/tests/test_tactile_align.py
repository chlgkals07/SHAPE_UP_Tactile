from __future__ import annotations

import numpy as np
import pytest

from tactile_rec.convert import align
from tactile_rec.tactile import (
    Module,
    TactileLayout,
    decode_payload,
    encode_payload,
    to_newtons,
)
from tactile_rec.types import NO_TIME, SRC_HOST_WALL, SRC_MONO, SRC_NONE, SRC_REMOTE_WALL

MS = 1_000_000


# ---- tactile payload ---------------------------------------------------------------------------


def test_decode_matches_the_vendor_low_byte_rule():
    # One DP-S2015-Elite on Index-Tip: 6 resultant bytes + 52 x 3 taxel bytes = 162, the size
    # measured on hardware (third_party/paxini/docs/FINDINGS.md).
    layout = TactileLayout((Module("Index-Tip", 52, "index_tip"),))
    assert layout.payload_size == 162
    payload = np.zeros(162, dtype=np.uint8)
    payload[0:6] = [0xFE, 0x99, 0x03, 0x99, 0xFE, 0x99]  # Fx=-2, Fy=+3, Fz=254; high bytes junk
    payload[6:9] = [0xFF, 0x80, 0xC8]  # first taxel: Fx=-1, Fy=-128, Fz=200
    out = decode_payload(payload, layout)["index_tip"]
    assert out["resultant"].tolist() == [[-2, 3, 254]]
    assert out["distributed"].shape == (1, 52, 3)
    assert out["distributed"][0, 0].tolist() == [-1, -128, 200]
    np.testing.assert_allclose(to_newtons(out["resultant"])[0], [-0.2, 0.3, 25.4], atol=1e-6)


def test_two_modules_with_different_point_counts_are_separated(layout_a):
    rng = np.random.default_rng(0)
    forces = {}
    for module in layout_a.modules:
        taxels = rng.integers(-100, 100, size=(module.points, 3)).astype(np.int16)
        taxels[:, 2] = rng.integers(0, 255, size=module.points)
        resultant = np.array([-5, 7, 200], dtype=np.int16)
        forces[module.place] = (resultant, taxels)
    payload = encode_payload(layout_a, forces)
    assert payload.shape == (layout_a.payload_size,) == (2 * (6 + 52 * 3) + 2 * (6 + 25 * 3),)
    decoded = decode_payload(np.stack([payload, payload]), layout_a)
    for place, (resultant, taxels) in forces.items():
        np.testing.assert_array_equal(decoded[place]["resultant"][1], resultant)
        np.testing.assert_array_equal(decoded[place]["distributed"][1], taxels)


def test_decode_rejects_a_payload_of_the_wrong_size(layout_a):
    with pytest.raises(ValueError, match="bytes per frame"):
        decode_payload(np.zeros(10, dtype=np.uint8), layout_a)


def test_layout_json_round_trip(layout_a):
    assert TactileLayout.from_json(layout_a.to_json()) == layout_a


# ---- grid and picking --------------------------------------------------------------------------


def test_grid_has_exact_steps_and_does_not_drift():
    grid = align.make_grid(0, 10 * 10**9, 30)
    assert grid[0] == 0 and len(grid) == 301
    assert grid[300] == 10 * 10**9  # 300 steps of 1/30 s is exactly 10 s
    assert align.make_grid(5, 4, 30).size == 0


def test_pick_latest_is_causal():
    times = np.array([10, 20, 30]) * MS
    grid = np.array([5, 10, 19, 20, 99]) * MS
    index = align.pick_latest(times, grid)
    assert index.tolist() == [-1, 0, 0, 1, 2]  # never a sample from the future
    stale = align.staleness_s(times, grid, index)
    assert np.isnan(stale[0])
    np.testing.assert_allclose(stale[1:], [0.0, 0.009, 0.0, 0.069])


def test_monotone_clamps_backward_steps():
    assert align.monotone(np.array([1, 5, 3, 7])).tolist() == [1, 5, 5, 7]


# ---- time sources ------------------------------------------------------------------------------


def test_respread_recovers_a_constant_rate_from_bunched_arrivals():
    period = 11 * MS
    true = 1_000 * MS + np.arange(90) * period
    # Samples arrive in groups of 3: each group is received when its last sample is emitted.
    recv = true.reshape(-1, 3)[:, -1].repeat(3)
    times, ok = align.respread(recv)
    assert ok
    assert np.abs(times - true).max() <= 2 * period  # recv alone is off by up to 2 periods
    assert np.abs(np.diff(times) - period).max() < MS  # evenly spaced again
    assert (times <= recv).all()  # never moved later than received


def test_respread_leaves_a_stall_alone():
    recv = np.concatenate([np.arange(50) * 11 * MS, 2_000 * MS + np.arange(50) * 11 * MS])
    times, ok = align.respread(recv, period_ns=11 * MS)
    assert ok
    np.testing.assert_array_equal(times, recv)  # evenly received samples are not moved


def test_respread_never_places_a_sample_before_it_was_produced_when_frames_are_lost():
    """Lost frames must not pull later samples into the past: a dataset step would then see a
    tactile value from its own future."""
    period = 11 * MS
    produced = 1_000 * MS + np.arange(120) * period
    kept = np.ones(120, dtype=bool)
    kept[[40, 41, 42, 43, 80]] = False  # four frames lost in a row, later one more
    produced = produced[kept]
    recv = produced.reshape(-1, 5)[:, -1].repeat(5)  # arrives in bursts of five
    times, _ = align.respread(recv)  # period estimated from the data, as the converter does
    assert abs(align.estimate_period(recv) - period) < 0.02 * period  # lost frames ignored
    assert (times - produced).min() >= -MS // 10  # never earlier than produced (0.1 ms slack)
    assert (times <= recv).all()
    assert np.abs(times - produced).max() <= 4 * period + MS  # still bounded by the burst length


def test_src_time_by_clock_kind():
    recv = np.array([1000, 1010, 1020]) * MS
    anchor = {"mono_ns": 500 * MS, "wall_ns": 9_000_500 * MS}
    # Same-PC monotonic stamps are used as they are.
    mono = np.array([998, 1008, 1018]) * MS
    np.testing.assert_array_equal(
        align.src_on_recorder_clock(recv, mono, SRC_MONO), mono
    )
    # Host wall-clock stamps are shifted by the anchor: true capture was 15 ms before receive.
    wall = recv - 15 * MS + (anchor["wall_ns"] - anchor["mono_ns"])
    np.testing.assert_array_equal(
        align.src_on_recorder_clock(recv, wall, SRC_HOST_WALL, anchor), recv - 15 * MS
    )
    # Another PC's clock: unknown offset, delays 4, 2, 9 ms -> the 2 ms sample defines it.
    remote = recv - np.array([4, 2, 9]) * MS + 123_456_789 * MS
    np.testing.assert_array_equal(
        align.src_on_recorder_clock(recv, remote, SRC_REMOTE_WALL),
        recv - np.array([2, 0, 7]) * MS,
    )


def test_samples_without_a_stamp_fall_back_to_receive_time():
    recv = np.array([1000, 1010]) * MS
    src = np.array([NO_TIME, 1008 * MS])
    out = align.src_on_recorder_clock(recv, src, SRC_MONO)
    assert out.tolist() == [1000 * MS, 1008 * MS]


def test_stream_times_applies_latency_and_explains_fallbacks():
    recv = np.array([1000, 1010, 1020]) * MS
    none = np.full(3, NO_TIME)
    times, note = align.stream_times(recv, none, mode="recv", latency_ns=20 * MS)
    assert times.tolist() == [980 * MS, 990 * MS, 1000 * MS] and note == ""
    times, note = align.stream_times(recv, none, mode="src", src_clock=SRC_NONE)
    assert times.tolist() == recv.tolist() and "no source stamp" in note
    with pytest.raises(ValueError):
        align.stream_times(recv, none, mode="nearest")
