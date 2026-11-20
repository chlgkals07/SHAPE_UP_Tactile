from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import cv2
import numpy as np
from tactile_rec import features
from tactile_rec.convert import align
from tactile_rec.hub import Hub
from tactile_rec.types import NO_TIME, SRC_NONE, Sample

MS = 1_000_000


@dataclass(frozen=True)
class Pick:
    seq: int
    t_ns: int
    age_ns: int


@dataclass(frozen=True)
class AlignedObs:
    obs_id: int
    t_obs_ns: int
    picks: dict[str, Pick]
    state: np.ndarray | None
    images: dict[str, np.ndarray]
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def has_hand_feedback(sample: Sample) -> bool:
    return bool(np.isfinite(sample.data["pos"]).all())


def any_sample(sample: Sample) -> bool:
    return True


class ObsAligner:
    def __init__(self, hub: Hub, cameras: Iterable[str], max_age_ms: dict[str, float],
                 max_skew_ms: float):
        dataset = hub.config.dataset
        self.hub = hub
        self.arm, self.hand, self.arm_dof = dataset.arm_state, dataset.hand, dataset.arm_dof
        self.cameras = tuple(cameras)
        self.max_age_ns = {name: int(ms * MS) for name, ms in max_age_ms.items()}
        self.max_skew_ns = int(max_skew_ms * MS)
        self.mode = {name: dataset.time.get(name, align.TIME_RECV) for name in self.streams}
        self.latency_ns = {name: int(dataset.latency_ms.get(name, 0.0) * MS)
                           for name in self.streams}
        self.rotation = {name: int(hub.streams[name].spec.meta["rotation_deg"])
                         for name in self.cameras}
        self.jpeg = [int(cv2.IMWRITE_JPEG_QUALITY), int(hub.config.record.jpeg_quality)]
        self._ids = itertools.count(1)

    @property
    def streams(self) -> tuple[str, ...]:
        return (self.arm, self.hand, *self.cameras)

    def align(self, t_obs_ns: int) -> AlignedObs:
        usable = {self.hand: has_hand_feedback}
        chosen: dict[str, tuple[Sample, Pick]] = {}
        problems = []
        for name in self.streams:
            found = self.pick(name, t_obs_ns, usable.get(name, any_sample))
            if found is None:
                problems.append(f"{name}: nothing usable at or before the observation time")
                continue
            chosen[name] = found
            age_ns, limit_ns = found[1].age_ns, self.max_age_ns[name]
            if age_ns > limit_ns:
                problems.append(f"{name}: {age_ns / MS:.0f} ms old (limit {limit_ns / MS:.0f})")
        problems += self.skew_problems([pick for _, pick in chosen.values()])
        return AlignedObs(
            obs_id=next(self._ids),
            t_obs_ns=t_obs_ns,
            picks={name: pick for name, (_, pick) in chosen.items()},
            state=self.state(chosen),
            images={name: self.image(name, chosen[name][0]) for name in self.cameras
                    if name in chosen},
            problems=problems,
        )

    def pick(self, name: str, t_obs_ns: int,
             usable: Callable[[Sample], bool]) -> tuple[Sample, Pick] | None:
        stream = self.hub.streams[name]
        arrived = [s for s in stream.recent(0) if s.t_recv_ns <= t_obs_ns]
        if not arrived:
            return None
        times = self.sample_times(name, arrived)
        rows = [i for i, sample in enumerate(arrived) if usable(sample)]
        if not rows:
            return None
        index = int(np.searchsorted(times[rows], t_obs_ns, side="right")) - 1
        if index < 0:
            return None
        row = rows[index]
        t_ns = int(times[row])
        return arrived[row], Pick(seq=arrived[row].seq, t_ns=t_ns, age_ns=t_obs_ns - t_ns)

    def sample_times(self, name: str, samples: list[Sample]) -> np.ndarray:
        recv = np.array([s.t_recv_ns for s in samples], dtype=np.int64)
        times = recv
        if self.mode[name] == align.TIME_SRC and self.hub.streams[name].spec.src_clock != SRC_NONE:
            src = np.array([s.t_src_ns for s in samples], dtype=np.int64)
            times = np.where(src != NO_TIME, src, recv)
        return align.monotone(times - self.latency_ns[name])

    def skew_problems(self, picks: list[Pick]) -> list[str]:
        if len(picks) < 2:
            return []
        skew_ns = max(p.t_ns for p in picks) - min(p.t_ns for p in picks)
        if skew_ns <= self.max_skew_ns:
            return []
        return [f"skew {skew_ns / MS:.0f} ms across streams (limit {self.max_skew_ns / MS:.0f})"]

    def measured(self, t_ns: int) -> np.ndarray | None:
        arm = self.pick(self.arm, t_ns, any_sample)
        hand = self.pick(self.hand, t_ns, has_hand_feedback)
        if arm is None or hand is None:
            return None
        return self.state({self.arm: arm, self.hand: hand})

    def state(self, chosen: dict[str, tuple[Sample, Pick]]) -> np.ndarray | None:
        if self.arm not in chosen or self.hand not in chosen:
            return None
        arm, hand = chosen[self.arm][0], chosen[self.hand][0]
        return features.joint_vector(arm.data["pos"], hand.data["pos"], self.arm_dof)

    def image(self, name: str, sample: Sample) -> np.ndarray:
        ok, encoded = cv2.imencode(".jpg", sample.data["image"], self.jpeg)
        if not ok:
            raise RuntimeError(f"{name}: JPEG encode failed")
        decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        return features.orient_image(decoded, self.rotation[name])


def to_request(obs: AlignedObs, prompt: str) -> dict:
    return {"state": obs.state, "images": dict(obs.images), "prompt": prompt}
