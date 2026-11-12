# lerobot integration

A drop-in `PaxiniSensor` for the `Jingyi-Z/lerobotac` `hall-sensor` branch
sensor framework. Mirrors the existing `MLX90393Sensor` structure so it
fits the rest of the project without code-style changes.

## Files

| File | Purpose | Where it goes in lerobotac |
| --- | --- | --- |
| `paxini.py` | `PaxiniSensor` class (the driver) | `src/lerobot/sensors/paxini.py` |
| `_config_patch.py` | `PaxiniSensorConfig` dataclass | append into `src/lerobot/sensors/configs.py` |
| `_init_patch.py` | Re-export wiring | extend `src/lerobot/sensors/__init__.py` |

## Install steps in the `hall-sensor` branch

```bash
# 1. Make sure paxini-sdk is installed in lerobotac's Python env
pip install paxini-sdk

# 2. Copy paxini.py in
cp paxini.py src/lerobot/sensors/

# 3. Append the config block from _config_patch.py to src/lerobot/sensors/configs.py
#    (everything between '# --- begin paste ---' and '# --- end paste ---')

# 4. Update src/lerobot/sensors/__init__.py per _init_patch.py

# 5. Verify
python -c "from lerobot.sensors import PaxiniSensor, PaxiniSensorConfig; print('OK')"
```

## Usage

Once installed, the Paxini sensor is selectable from anywhere lerobot picks
sensors by `type:` field:

```yaml
sensors:
  - type: paxini
    port: /dev/cu.usbserial-0001
    output_format: resultant     # or "distributed" or "both"
    buffer_size: 10
    auto_calibrate: true
```

Programmatic use:

```python
from lerobot.sensors import PaxiniSensor, PaxiniSensorConfig

cfg = PaxiniSensorConfig(port="/dev/cu.usbserial-0001",
                          output_format="distributed",
                          buffer_size=10)
with PaxiniSensor(cfg) as sensor:
    sensor.start_continuous_read()
    sensor.wait_for_calibration(timeout_s=2.0)
    data = sensor.get_latest_data()    # (10, 52, 3) for DP-S2015-Elite
```

## Output shapes

| `output_format` | Shape | Contents |
| --- | --- | --- |
| `"resultant"` | `(buffer_size, 3)` | Resultant Fx, Fy, Fz in N |
| `"distributed"` | `(buffer_size, P, 3)` | Per-taxel Fx, Fy, Fz in N (P = 52 for DP-S2015-Elite) |
| `"both"` | `(buffer_size, 3 + P*3)` | Resultant followed by flattened distributed |

`P` is auto-discovered from the board's reported point count.

## Threading model

Mirrors `MLX90393Sensor` exactly:

- One background thread drives `hand.stream_auto_push()`.
- A `deque(maxlen=buffer_size)` ring buffer holds the latest frames.
- A `threading.Lock` guards reads / writes.
- `get_latest_data()` returns a stacked numpy array, oldest first.

## Calibration semantics

Two layers (independent, both opt-in):

1. **Firmware** (`auto_calibrate=True`, default): sends the vendor's
   calibration frame at connect. Zeros the magnetic-field baseline inside
   the sensor MCU. Sub-LSB precision; recommended on every session.
2. **Software** (`software_baseline_frames=N`, default 0): after connect,
   accumulates N samples and subtracts their mean from all subsequent
   readings. Catches any residual ~1 LSB offset left after firmware
   calibration. Adds N-frame startup latency.

`is_calibrated` is true once both layers are done; `wait_for_calibration()`
polls for it.
