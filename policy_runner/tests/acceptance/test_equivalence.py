from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from tactile_rec import features
from tactile_rec.clock import FakeClock
from tactile_rec.config import parse_config
from tactile_rec.convert.episode import convert_episode
from tactile_rec.convert.load import Episode
from tactile_rec.hub import Hub
from tactile_rec.record.session import Recorder
from tactile_rec.stream import Stream

from policy_runner.align_obs import ObsAligner

from conftest import Replay, episode_samples, fresh_hub_like, rig_dict, spec_from_json

CAMERAS = ("cam_wrist", "cam_ext")
WIDE = {"cam_wrist": 10_000, "cam_ext": 10_000, "arm_state": 10_000, "hand": 10_000}
SAMPLES = Path(__file__).resolve().parents[3] / "data" / "samples" / "2026-11-17" / "sync_test"
CLEAN = SAMPLES / "2026-11-17_2035_hamin" / "ep_0001"
DROPPED = SAMPLES / "2026-11-17_1852_hamin" / "ep_0001"


def record_and_convert(rig, seconds=3.0):
    recorder = Recorder(rig.hub)
    rig.run(1.5)
    recorder.start()
    rig.run(seconds, on_step=recorder.tick)
    recorder.stop()
    episode = Episode(recorder.save(True))
    return episode, convert_episode(episode, rig.hub.config.dataset)


def online_at_grid(rig, converted):
    clock = FakeClock()
    replay_hub = fresh_hub_like(rig.hub, clock)
    replay = Replay(replay_hub, clock, rig.collected)
    aligner = ObsAligner(replay_hub, CAMERAS, WIDE, 10_000)
    out = []
    for t in converted.grid_ns:
        replay.until(int(t))
        out.append(aligner.align(int(t)))
    return out


@pytest.mark.parametrize("latency", [{}, {"cam_wrist": 35}])
def test_online_obs_matches_converted_episode(timed_rig, latency):
    rig = timed_rig(latency_ms=latency)
    episode, converted = record_and_convert(rig)
    online = online_at_grid(rig, converted)
    assert len(online) == converted.steps > 60
    not_arrived = 0
    for step, obs in enumerate(online):
        t = int(converted.grid_ns[step])
        assert obs.ok, (step, obs.problems)
        assert np.array_equal(obs.state, converted.arrays[features.KEY_STATE][step]), step
        for camera in CAMERAS:
            recv = episode.arrays(camera)["t_recv_ns"]
            frame = int(converted.frames[camera][step])
            if recv[frame] > t:
                not_arrived += 1
                frame = int(np.searchsorted(recv, t, side="right")) - 1
            offline = features.orient_image(episode.frame(camera, frame),
                                            converted.rotations[camera])
            assert np.array_equal(obs.images[camera], offline), (step, camera)
    assert (not_arrived > 0) == bool(latency)


def sample_hub(episode: Episode, clock: FakeClock) -> Hub:
    raw = rig_dict(Path("/tmp"), cameras=[], tactile=[], time={"hand": "src"})
    del raw["streams"]["cam_ext"]
    config = parse_config(raw)
    streams = {name: Stream(spec_from_json(name, episode.spec(name)), clock, buffer_s=2.0)
               for name in ("arm_state", "arm_action", "hand")}
    return Hub(config, clock, streams)


@pytest.mark.parametrize("path", [CLEAN, DROPPED], ids=["clean", "dropped"])
def test_recorded_episode_replays_to_the_same_state(path):
    if not (path / "hand.npz").is_file() or (path / "hand.npz").stat().st_size < 1024:
        pytest.skip("11/17 samples not pulled (git lfs pull)")
    episode = Episode(path)
    clock = FakeClock()
    hub = sample_hub(episode, clock)
    converted = convert_episode(episode, hub.config.dataset)
    recorded = episode_samples(episode, ["arm_state", "hand"])
    replay = Replay(hub, clock, recorded)
    aligner = ObsAligner(hub, (), WIDE, 10_000)
    hand = episode.arrays("hand")
    mismatches = 0
    for step, t in enumerate(converted.grid_ns):
        replay.until(int(t))
        obs = aligner.align(int(t))
        if np.array_equal(obs.state, converted.arrays[features.KEY_STATE][step]):
            continue
        mismatches += 1
        later = (hand["t_src_ns"] <= t) & (hand["t_recv_ns"] > t)
        assert later.any(), f"step {step}: mismatch not explained by an unarrived sample"
    assert mismatches < 0.05 * converted.steps
