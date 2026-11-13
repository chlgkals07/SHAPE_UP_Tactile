"""Smoke test the integrations/lerobot/paxini.py against a mock lerobot
sensor framework. Verifies the class implements the abstract contract
and exposes the right shapes for each output_format."""
import os, sys, types, threading, time
import numpy as np
from dataclasses import dataclass, field

# ---- stub the lerobot sensor framework so paxini.py can import .configs and .sensor
SENSOR_PKG = "lerobot_sensors_stub"

# Build a fake "configs" module
configs_mod = types.ModuleType(f"{SENSOR_PKG}.configs")
@dataclass
class PaxiniSensorConfig:
    port: str = "FAKE_PORT"
    baud_rate: int = 921_600
    buffer_size: int = 4
    module_index: int | None = None
    output_format: str = "resultant"
    auto_calibrate: bool = False  # disable for the test
    software_baseline_frames: int = 0
configs_mod.PaxiniSensorConfig = PaxiniSensorConfig

# Build a fake "sensor" module
sensor_mod = types.ModuleType(f"{SENSOR_PKG}.sensor")
import abc
class Sensor(abc.ABC):
    def __init__(self, config):
        self.config = config
    def __enter__(self):
        self.connect()
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()
    def metadata(self):
        return {"type": self.__class__.__name__, "shape": list(self.shape)}
sensor_mod.Sensor = Sensor

# Wire up the stub package so the relative imports in paxini.py resolve
parent_pkg = types.ModuleType(SENSOR_PKG)
parent_pkg.configs = configs_mod
parent_pkg.sensor = sensor_mod
sys.modules[SENSOR_PKG] = parent_pkg
sys.modules[f"{SENSOR_PKG}.configs"] = configs_mod
sys.modules[f"{SENSOR_PKG}.sensor"] = sensor_mod

# Read paxini.py source, retarget its relative imports onto our stub package
import importlib.util
SRC = "/sessions/gracious-happy-maxwell/mnt/Tactile VLA based on SO-101/paxini-sdk/integrations/lerobot/paxini.py"
text = open(SRC).read()
text = text.replace("from .configs import PaxiniSensorConfig",
                     f"from {SENSOR_PKG}.configs import PaxiniSensorConfig")
text = text.replace("from .sensor import Sensor",
                     f"from {SENSOR_PKG}.sensor import Sensor")
mod = types.ModuleType("paxini_lerobot_under_test")
exec(compile(text, SRC, "exec"), mod.__dict__)
PaxiniSensor = mod.PaxiniSensor

# ---- Mock HighSpeedHandBoard + AutoPushFrame + registers
import paxini_sdk.registers as registers
from paxini_sdk.boards.high_speed import AutoPushConfig, AutoPushFrame

class FakeBoard:
    def __init__(self, port, baudrate=None):
        self.port = port
        self._calibrated = False
    def open(self): return self
    def close(self): return None
    def read_active_modules(self): return [6]  # Index-Tip
    def read_distribution_point_count(self, m): return 52
    def read_auto_push_config(self):
        return AutoPushConfig(active_modules=[6], has_resultant=True,
                               has_distributed=True, point_counts={6: 52})
    def calibrate(self):
        self._calibrated = True
    def stream_auto_push(self, **kw):
        # Yield 8 synthetic frames over ~0.4 s
        cfg = self.read_auto_push_config()
        for i in range(8):
            # Build a payload: resultant (fx=i, fy=-i, fz=i*3) + 52 distributed pts of zeros
            payload = bytes([i & 0xFF, 0, (-i) & 0xFF, 0, (i * 3) & 0xFF, 0])
            payload += bytes([0] * (52 * 3))
            yield AutoPushFrame(config=cfg, error_code=0, valid_data=payload, raw=b"")
            time.sleep(0.05)

# Inject the mock into the under-test module's namespace
import paxini_sdk
paxini_sdk_real_HSHB = paxini_sdk.HighSpeedHandBoard
paxini_sdk.HighSpeedHandBoard = FakeBoard

# ---- Now actually test each output_format
print("=== [1] resultant mode ===")
cfg = PaxiniSensorConfig(output_format="resultant", buffer_size=4)
with PaxiniSensor(cfg) as s:
    print(f"  shape: {s.shape}  is_connected: {s.is_connected}  is_calibrated: {s.is_calibrated}")
    assert s.shape == (4, 3)
    s.start_continuous_read()
    time.sleep(0.5)  # let the read loop accumulate frames
    data = s.get_latest_data()
    s.stop_continuous_read()
    print(f"  data.shape: {data.shape}  dtype: {data.dtype}")
    print(f"  last 4 frames (newtons):")
    for row in data:
        print(f"    Fx={row[0]:+.1f}  Fy={row[1]:+.1f}  Fz={row[2]:+.1f}")
    assert data.shape == (4, 3)
    assert data.dtype == np.float32

print("\n=== [2] distributed mode ===")
cfg = PaxiniSensorConfig(output_format="distributed", buffer_size=3)
with PaxiniSensor(cfg) as s:
    print(f"  shape: {s.shape}")
    assert s.shape == (3, 52, 3)  # (buffer, taxels, axes)
    s.start_continuous_read()
    time.sleep(0.5)
    data = s.get_latest_data()
    s.stop_continuous_read()
    print(f"  data.shape: {data.shape}  dtype: {data.dtype}")
    assert data.shape == (3, 52, 3)

print("\n=== [3] both mode ===")
cfg = PaxiniSensorConfig(output_format="both", buffer_size=2)
with PaxiniSensor(cfg) as s:
    expected_dim = 3 + 52 * 3
    print(f"  shape: {s.shape}  (expected (2, {expected_dim}))")
    assert s.shape == (2, expected_dim)
    s.start_continuous_read()
    time.sleep(0.5)
    data = s.get_latest_data()
    s.stop_continuous_read()
    print(f"  data.shape: {data.shape}")
    assert data.shape == (2, expected_dim)

print("\n=== [4] software baseline ===")
cfg = PaxiniSensorConfig(output_format="resultant", buffer_size=4,
                          software_baseline_frames=3)
with PaxiniSensor(cfg) as s:
    s.start_continuous_read()
    ok = s.wait_for_calibration(timeout_s=2.0, poll_s=0.05)
    s.stop_continuous_read()
    print(f"  wait_for_calibration returned: {ok}")
    print(f"  is_calibrated after wait: {s.is_calibrated}")
    print(f"  software baseline shape: {s._sw_baseline.shape if s._sw_baseline is not None else None}")
    assert ok
    assert s._sw_baseline is not None

print("\n=== [5] metadata round-trip ===")
cfg = PaxiniSensorConfig(output_format="resultant", buffer_size=4, auto_calibrate=False)
with PaxiniSensor(cfg) as s:
    md = s.metadata()
    import json
    j = json.dumps(md, indent=2)
    print(j[:400])

print("\nAll integration smoke checks pass.")
