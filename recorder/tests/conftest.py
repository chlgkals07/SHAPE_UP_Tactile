"""Shared test rig: passive streams driven by a fake clock, so timing is exact."""

from __future__ import annotations

import numpy as np
import pytest

from tactile_rec.clock import FakeClock
from tactile_rec.config import parse_config
from tactile_rec.hub import Hub
from tactile_rec.stream import Stream
from tactile_rec.streams import specs
from tactile_rec.streams.fake import FakeStream, fake_layout

PLACES_A = {
    "Thumb-Tip": "thumb_tip", "Thumb-Middle": "thumb_pad",
    "Index-Tip": "index_tip", "Index-Middle": "index_pad",
}
PLACES_B = {
    "Middle-Tip": "middle_tip", "Middle-Middle": "middle_pad",
    "Ring-Tip": "ring_tip", "Ring-Middle": "ring_pad",
}


def fake_config_dict(tmp_path, **overrides):
    raw = {
        "rig": {"name": "test_rig", "mount": "wrist_flip"},
        "data_root": str(tmp_path / "data"),
        "session": {"task": "pick_cup", "text": "Pick up the cup", "operator": "tester"},
        "record": {"preroll_s": 1.0, "min_free_gb": 0},
        "streams": {
            "arm_state": {"type": "fake", "like": "arm_state", "hz": 100},
            "arm_action": {"type": "fake", "like": "arm_action", "hz": 100},
            "hand": {"type": "fake", "like": "hand", "hz": 50},
            "glove": {"type": "fake", "like": "glove", "hz": 50, "required": False},
            "tactile_a": {"type": "fake", "like": "tactile", "hz": 90, "places": PLACES_A},
            "tactile_b": {"type": "fake", "like": "tactile", "hz": 90, "places": PLACES_B},
            "cam_wrist": {"type": "fake", "like": "camera", "hz": 30, "width": 64, "height": 48,
                          "rotation_deg": 90},
            "cam_ext": {"type": "fake", "like": "camera", "hz": 30, "width": 64, "height": 48},
        },
        "dataset": {
            "tactile": ["tactile_a", "tactile_b"],
            "cameras": ["cam_wrist", "cam_ext"],
            "time": {"hand": "src"},
        },
    }
    raw.update(overrides)
    return raw


class ManualRig:
    """A Hub whose streams only produce a sample when the test says so."""

    def __init__(self, tmp_path, **overrides):
        self.clock = FakeClock()
        self.config = parse_config(fake_config_dict(tmp_path, **overrides))
        # FakeStream objects are used only for their spec and their make(); never started.
        self.makers = {
            name: FakeStream(name, cfg, self.clock) for name, cfg in self.config.streams.items()
        }
        self.streams = {
            name: Stream(maker.spec, self.clock) for name, maker in self.makers.items()
        }
        self.hub = Hub(self.config, self.clock, self.streams)
        self._due = {name: self.clock.now_ns() for name in self.streams}

    def run(self, seconds: float, skip: tuple[str, ...] = (), on_step=None) -> None:
        """Advance time, emitting every stream at its nominal rate (exact periods)."""
        end_ns = self.clock.now_ns() + int(seconds * 1e9)
        while True:
            name = min(self._due, key=self._due.get)
            due = self._due[name]
            if due > end_ns:
                break
            self.clock.set_ns(max(due, self.clock.now_ns()))
            period = int(1e9 / self.streams[name].spec.nominal_hz)
            self._due[name] = due + period
            if name not in skip:
                maker = self.makers[name]
                maker._tick += 1
                self.streams[name].push(maker.make(due / 1e9), t_src_ns=due, src_seq=maker._tick)
            if on_step is not None:
                on_step()
        self.clock.set_ns(end_ns)


@pytest.fixture
def rig(tmp_path):
    return ManualRig(tmp_path)


@pytest.fixture
def layout_a():
    return fake_layout(PLACES_A)


def numeric_stream(name="s", hz=100.0, clock=None):
    spec = specs.arm_spec(name, "joint_trajectory", ["j1", "j2"], hz, True)
    return Stream(spec, clock or FakeClock())


def value(x: float) -> dict:
    return {"pos": np.array([x, -x])}
