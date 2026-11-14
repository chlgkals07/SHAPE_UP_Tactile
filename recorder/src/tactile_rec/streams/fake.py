"""Synthetic devices, so the whole recorder runs and is tested without hardware.

All fake streams derive their signal from the shared clock, so a "tap" (a short pulse every
few seconds) happens at the same instant in tactile, hand current and the camera image. That
makes time alignment visible in the UI and measurable in tests.
"""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

from tactile_rec.clock import Clock
from tactile_rec.stream import ThreadedStream
from tactile_rec.streams import specs
from tactile_rec.tactile import Module, TactileLayout, encode_payload, taxel_xy
from tactile_rec.types import NO_TIME, SRC_NONE, StreamSpec

TAP_WIDTH_S = 0.08
POINTS_BY_SEGMENT = {"tip": 52, "pad": 25}  # DP-S2015-Elite / IP-S1610-Elite


def tap_level(t_s: float, period_s: float) -> float:
    """1.0 during the first TAP_WIDTH_S of every period, else 0.0."""
    if period_s <= 0:
        return 0.0
    return 1.0 if (t_s % period_s) < TAP_WIDTH_S else 0.0


def fake_layout(places: dict[str, str]) -> TactileLayout:
    modules = tuple(
        Module(name, POINTS_BY_SEGMENT.get(place.rsplit("_", 1)[-1], 25), place, "fake")
        for name, place in places.items()
    )
    return TactileLayout(modules)


def _spec(name: str, cfg: dict[str, Any]) -> StreamSpec:
    like, hz, required = cfg["like"], float(cfg["hz"]), bool(cfg["required"])
    joints = cfg.get("joints") or [f"joint{i}" for i in range(1, 7)]
    if like == "arm_state":
        return specs.arm_spec(name, "joint_state", joints, hz, required)
    if like == "arm_action":
        return specs.arm_spec(name, "joint_trajectory", joints, hz, required)
    if like == "hand":
        return specs.hand_spec(name, hz, required)
    if like == "glove":
        return specs.glove_spec(name, hz)
    if like == "tactile":
        return specs.tactile_spec(name, hz, required, fake_layout(cfg["places"]))
    spec = specs.camera_spec(
        name, int(cfg["width"]), int(cfg["height"]), hz, int(cfg["rotation_deg"]), required
    )
    spec.src_clock = SRC_NONE
    return spec


class FakeStream(ThreadedStream):
    def __init__(self, name: str, cfg: dict[str, Any], clock: Clock | None = None):
        super().__init__(_spec(name, cfg), clock)
        self.like = cfg["like"]
        self.period_ns = int(1e9 / float(cfg["hz"]))
        self.tap_period_s = float(cfg["tap_period_s"])
        self.drop_after_s = float(cfg["drop_after_s"])
        self._next_ns = 0
        self._started_ns = 0
        self._tick = 0
        self._zero_requested = False
        if self.like == "tactile":
            self.layout = fake_layout(cfg["places"])
            self._xy = {}
            for module in self.layout.modules:  # taxel positions scaled into the unit square
                xy = np.asarray(taxel_xy(module.points), dtype=np.float64)
                span = np.ptp(xy, axis=0).max() or 1.0
                self._xy[module.place] = (xy - xy.min(axis=0)) / span

    def zero(self) -> None:
        self._zero_requested = True

    def _open(self) -> None:
        self._next_ns = self._started_ns = self.clock.now_ns()

    def _close(self) -> None:
        pass

    def _read_once(self) -> None:
        wait_s = (self._next_ns - self.clock.now_ns()) / 1e9
        if wait_s > 0 and self._stop_event.wait(wait_s):
            return
        now_ns = self.clock.now_ns()
        self._next_ns += self.period_ns
        if self._next_ns < now_ns - 10 * self.period_ns:  # fell far behind: do not burst
            self._next_ns = now_ns
        self._tick += 1
        if self._zero_requested:
            self._zero_requested = False
        elapsed_s = (now_ns - self._started_ns) / 1e9
        if self.drop_after_s > 0 and (elapsed_s % (self.drop_after_s + 2.0)) > self.drop_after_s:
            return  # simulated dropout: silent for 2 s after every drop_after_s
        self.push(self.make(now_ns / 1e9), src_seq=self._tick,
                  t_src_ns=now_ns if self.spec.src_clock != SRC_NONE else NO_TIME)

    def make(self, t_s: float) -> dict[str, np.ndarray]:
        """The fake reading at time t_s. Pure, so tests can call it with exact times."""
        tap = tap_level(t_s, self.tap_period_s)
        if self.like in ("arm_state", "arm_action"):
            count = self.spec.fields["pos"].shape[0]
            lead = 0.05 if self.like == "arm_action" else 0.0
            phase = np.arange(count) * 0.7
            pos = 0.4 * np.sin(0.5 * (t_s + lead) + phase)
            data = {"pos": pos}
            if "vel" in self.spec.fields:
                data["vel"] = 0.2 * np.cos(0.5 * t_s + phase)
                data["eff"] = np.zeros(count)
            return data
        if self.like == "hand":
            phase = np.arange(specs.HAND_DOF) * 0.4
            cmd = (35 + 25 * np.sin(0.8 * t_s + phase)).astype(np.float32)
            pos = (35 + 25 * np.sin(0.8 * (t_s - 0.06) + phase)).astype(np.float32)
            return {
                "cmd": cmd, "sent": cmd, "pos": pos,
                "vel": (20 * np.cos(0.8 * t_s + phase)).astype(np.float32),
                "cur": np.full(specs.HAND_DOF, 40 + 300 * tap, dtype=np.float32),
                "mode": np.int8(0),
            }
        if self.like == "glove":
            ergo = (30 + 20 * np.sin(0.8 * t_s + np.arange(specs.GLOVE_ANGLES) * 0.3))
            return {
                "ergo": ergo.astype(np.float32),
                "nodes": np.full((specs.GLOVE_MAX_NODES, 7), np.nan, dtype=np.float32),
                "n_nodes": np.int16(0),
            }
        if self.like == "tactile":
            forces = {}
            for index, module in enumerate(self.layout.modules):
                # A fingertip-sized contact patch that wanders over the sensor surface while
                # the press strength rises and falls, plus the shared tap pulse.
                xy = self._xy[module.place]
                press = max(0.0, math.sin(0.6 * t_s + index * 0.9))
                centre = np.array([
                    0.5 + 0.3 * math.sin(0.9 * t_s + index), 0.5 + 0.3 * math.cos(0.7 * t_s + index)
                ])
                distance2 = ((xy - centre) ** 2).sum(axis=1)
                bump = np.exp(-distance2 / (2 * 0.18**2))
                fz = np.clip(np.round(press * 28 * bump + tap * 25), 0, 255)
                taxels = np.zeros((module.points, 3), dtype=np.int16)
                taxels[:, 2] = fz
                taxels[:, 0] = np.round(4 * press * bump * math.cos(t_s))
                taxels[:, 1] = np.round(4 * press * bump * math.sin(t_s))
                resultant = np.array(
                    [taxels[:, 0].sum() // 4, taxels[:, 1].sum() // 4,
                     min(255, int(fz.sum() // 6))], dtype=np.int16,
                )
                forces[module.place] = (resultant, taxels)
            return {
                "payload": encode_payload(self.layout, forces),
                "error_code": np.int16(0),
            }
        height, width, _ = self.spec.fields["image"].shape
        image = np.full((height, width, 3), 235 if tap else 60, dtype=np.uint8)
        x = int((0.5 + 0.45 * math.sin(0.8 * t_s)) * (width - 20))
        cv2.rectangle(image, (x, height // 3), (x + 20, 2 * height // 3), (40, 160, 90), -1)
        cv2.putText(image, f"{self.name} {self._tick}", (8, 22), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (20, 20, 20) if tap else (230, 230, 230), 1, cv2.LINE_AA)
        return {"image": image, "ts_domain": np.int8(-1)}
