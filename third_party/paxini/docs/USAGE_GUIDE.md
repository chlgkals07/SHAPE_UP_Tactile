# Usage guide — Paxini sensor testing

Written for someone who hasn't read the vendor docs. Covers what's in
this folder, how to use it, and what the wrapper functions do.

For deeper context on protocol decisions and the bugs found / fixed,
see `FINDINGS.md`. For a one-page status snapshot, see `README.md`.

---

## 1. What the hardware does, in one paragraph

The **Paxini DP-S2015-Elite** is a 15 mm fingertip-shaped tactile sensor.
Under the silicone surface are 52 force-sensing points laid out in a 3D
grid that follows the curvature of the fingertip. Each frame the sensor
reports two things:

1. A **resultant force** vector `(Fx, Fy, Fz)` — the total force on the
   fingertip, with Fx/Fy being shear (sideways) and Fz being normal
   (pressing in).
2. A **distributed-force grid** — the per-point `(Fx, Fy, Fz)` at each
   of the 52 measurement locations.

Force unit on the wire is **0.1 N per LSB** (so a raw value of 10 = 1.0 N).

The sensor talks to a small **High-Speed Communication Board**
(your `PXSR-STDOTO4B`) over an FPC cable. That board converts the
sensor's I²C/SPI traffic into a serial protocol over USB at 921600 baud,
which is what Python reads through `pyserial`.

---

## 2. What's in this folder

```
sensor_testing/
├── README.md             ← one-page status + folder map (start here for a quick look)
├── USAGE_GUIDE.md        ← this file (the friendly walkthrough)
├── FINDINGS.md           ← chronological session log: bugs found, protocol decisions, citations
├── SETUP_WINDOWS.md      ← Windows driver install + Python env steps
├── smoke_test.py         ← end-to-end hardware check on the command line
├── paxini_to_rerun.py    ← visualizer (live stream into rerun, or replay a CSV)
├── paxini_sdk/           ← the Python wrapper (a package you can `pip install -e .`)
│   ├── paxini_sdk/
│   │   ├── __init__.py            (re-exports the public API)
│   │   ├── boards/
│   │   │   ├── high_speed.py      ← HighSpeedHandBoard — main class you use
│   │   │   └── serial_converter.py ← SingleSensorBoard (other board variant, untested here)
│   │   ├── protocol.py            ← Builds & parses on-the-wire frames; LRC checksum
│   │   ├── transport.py           ← Serial I/O, port discovery, fast frame reader
│   │   ├── registers.py           ← Register addresses + module-name table + bitmap parser
│   │   ├── sensor_registry.py     ← Lookup table for the 12 sensor variants
│   │   ├── exceptions.py          ← PaxiniError / FrameError / LRCError / DeviceError
│   │   ├── cli.py                 ← `paxini` console-script entry point
│   │   └── data/                  ← 12 *_points.json files + registry.json
│   ├── pyproject.toml             ← Tells `pip install -e .` how to install
│   └── tests/                     ← 32 offline unit tests (run with pytest)
└── data/                 ← Captured CSVs (from Paxini host app), wrapper logs, .rrd files
```

---

## 3. One-time setup on Windows

Open a PowerShell:

```powershell
cd "C:\Users\jingy\Documents\Claude\Projects\Tactile VLA based on SO-101\sensor_testing\paxini_sdk"
pip install pyserial rerun-sdk
pip install -e .
```

The first `pip install` brings in `pyserial` (talks to the COM port) and
`rerun-sdk` (the visualization library). The `-e .` line installs the
local wrapper in "editable" mode, so any edits you make to the
`paxini_sdk/` source take effect on the next run without re-installing.

To check it worked:

```powershell
python -c "from paxini_sdk import HighSpeedHandBoard; print('SDK OK')"
```

You should see `SDK OK`. Now run the offline tests:

```powershell
pytest tests/ -q
```

You should see `32 passed`. These tests don't need hardware — they just
verify the wrapper builds the right bytes for each protocol command and
decodes them correctly.

If you ever need to set up a Windows machine from scratch (driver,
Python install), `SETUP_WINDOWS.md` has the longer version of these
steps.

---

## 4. Day-to-day operations

The three things you'll do most often:

### 4a. Run a quick sanity check on the hardware

```powershell
cd ..  # back to sensor_testing/
python smoke_test.py --port COM7 --duration 25 --calibrate
```

This script prints six things in order:

1. **Firmware version** of the comm board (`ADAPTER_FW02.22` on yours).
2. **Active modules** — which sensor slot has a sensor plugged in
   (e.g. `['Index-Tip']`).
3. **Data-type register** — which kinds of force data the board is
   emitting (`resultant` + `distributed`).
4. **Distributed-force point counts** per active module (52 for your
   DP-S2015-Elite).
5. **One-shot force read** for each active module right now.
6. **25 seconds of streaming** at ~5 Hz print rate (the board itself
   pushes at ~91 Hz; the script just prints a subset so the terminal
   isn't unreadable).

Add `--calibrate` to zero the sensor before measuring (matches the host
app's 标定 button). Without it, the sensor keeps whatever offset it had
from the last calibration.

If you want to redirect everything to a file for later analysis:

```powershell
python smoke_test.py --port COM7 --duration 25 --calibrate *> my_run.txt
```

### 4b. Open the rerun visualizer (live)

```powershell
python paxini_to_rerun.py --port COM7 --calibrate
```

This spawns the rerun viewer window automatically. You'll see:

- A **left rail** with an entity tree. Expand `sensor/index_tip/` to see
  the live data paths.
- **Time-series panels** (`resultant/fx`, `resultant/fy`, `resultant/fz`)
  that scroll as new samples arrive.
- A **3D point cloud** (`distributed`) showing the 52 tactile points
  laid out in the actual fingertip geometry, each colored by Fz (light
  grey = no load, blue gets darker as Fz goes up).

Press the fingertip and you should see the resultant Fz spike on the
time-series chart and the relevant points light up on the 3D view. Drag
to rotate the 3D view; use the timeline scrubber at the bottom to step
back through recent frames.

To stop the live stream: Ctrl+C in the PowerShell window. The rerun
viewer stays open so you can keep inspecting the captured data.

Optional flags:

- `--duration 60` — stop streaming after 60 seconds.
- `--sensor-part PXSR-STDDP03F` — manual override if you swap to a
  different sensor (auto-detection from point count should usually be
  enough; only needed if you have a sensor with a custom point count).

### 4c. Replay a CSV recorded by the Paxini host app

If you saved a recording from the vendor's Windows host app (the 开始
button writes a `HH-MM-SS.csv` file), you can replay it through the
rerun viewer without touching the hardware:

```powershell
python paxini_to_rerun.py --csv "data\2026-05-18-160858_paxini_app_v1.0.11_session2.csv"
```

Same viewer, same panels, but driven by the historical timestamps in the
CSV instead of real-time arrival. Useful for re-examining a press or a
session that's already complete.

A pre-rendered replay is in `data/2026-05-18-160858_replay.rrd`. You
can open it directly:

```powershell
rerun "data\2026-05-18-160858_replay.rrd"
```

---

## 5. Common questions

### How do I know which COM port to use?

Open **Device Manager → Ports (COM & LPT)** with the board plugged in;
the entry under it (likely `USB-SERIAL CH340 (COM7)`) gives you the
number. Pass it to any of the scripts as `--port COM7`.

If you forget, both scripts will list available ports when you run them
without `--port`:

```powershell
python smoke_test.py
```

### What does `--calibrate` actually do?

It sends the exact frame `55 AA 00 17 02 00 01 00 01 E6` over the
serial port. The sensor uses that to record its current load as the
zero point. Without it, you're measuring relative to whatever offset
was there before. The vendor's GUI calls this 标定 (Calibrate).

It's the same single-button operation the host app does when you click
标定 — there's no further setup or wait time involved.

### I swapped sensors. Do I need to change anything?

No. Run any of the scripts and the wrapper will:

1. Read the active-module bitmap → confirms a sensor is plugged in.
2. Read that sensor's point count from register 0x0030 + 2·module_idx.
3. Look that count up in the registry to find the matching variant.
4. Load the right coordinate file from `paxini_sdk/data/`.

All 12 GEN3 sensor variants ship as JSON assets, and each one has a
distinct point count, so the lookup is unambiguous.

The smoke test will print which variant was identified. The rerun viz
will use the right 3D positions automatically.

### How do I save what I see to a CSV?

Two options:

- **Use the vendor host app** for its `开始` / `停止` recording. The
  CSV format is what `paxini_to_rerun.py --csv` reads.
- The wrapper does not yet have a built-in CSV writer. If you need one,
  it's ~20 lines: take `frame.resultant_forces` and `frame.distributed_forces`
  from each frame in `hand.stream_auto_push()` and write them to disk.
  Happy to add this if it would help.

### Where do force values come from, in newtons?

Two layers of decoding:

1. The wrapper grabs the 6 byte resultant-force block for each module
   from the auto-push payload and decodes it as:
   - `Fx = signed_int8(byte_0)` (range −128…+127)
   - `Fy = signed_int8(byte_2)` (range −128…+127)
   - `Fz = uint8(byte_4)` (range 0…255)
2. Multiplying by 0.1 N/LSB gives newtons. Use `frame.resultant_forces_newtons`
   (and similarly `..._newtons` on the distributed variants) to skip the
   manual conversion.

The 3 unused "high bytes" of each 6-byte block are reserved by the
vendor and currently always zero in practice.

---

## 6. Writing your own Python on top of the wrapper

The wrapper is a regular Python package — you can use it directly from
any script. Minimal example:

```python
from paxini_sdk import HighSpeedHandBoard

with HighSpeedHandBoard("COM7") as hand:
    print("Firmware:", hand.read_version())
    hand.calibrate()
    for frame in hand.stream_auto_push(duration=10.0):
        for name, (fx, fy, fz) in frame.resultant_forces_newtons.items():
            print(f"{name}  Fx={fx:+.1f}  Fy={fy:+.1f}  Fz={fz:+.1f}")
```

The `with` block handles `open()` / `close()` automatically (including
disabling auto-push when you exit, so the board is in a clean state
for the next session).

Key methods on `HighSpeedHandBoard`:

| Method | What it does |
| --- | --- |
| `read_version()` | Returns the firmware string like `'ADAPTER_FW02.22'`. |
| `read_active_modules()` | Returns a list of module indices that have sensors plugged in (e.g. `[6]` for Index-Tip only). |
| `read_data_type()` | Returns the data-type byte from register 0x0016. |
| `read_distribution_point_count(module_idx)` | How many tactile points the sensor in `module_idx` reports. |
| `read_auto_push_config()` | Bundles the three reads above into an `AutoPushConfig` you can inspect or pass around. |
| `read_resultant_forces()` | One-shot read of every active module's resultant force, returns `{module_name: (Fx, Fy, Fz)}` in LSB counts. |
| `read_resultant_forces_newtons()` | Same, in newtons. |
| `calibrate()` | Zeros the baseline at the current load. Raises `DeviceError` if the board reports failure. |
| `enable_auto_push()` / `disable_auto_push()` | Low-level toggles; usually you don't call these directly. |
| `reset_board()` | Reboots the comm board (USB will drop). |
| `stream_auto_push(duration=..., max_frames=..., config=...)` | Generator that yields one `AutoPushFrame` per auto-push burst. |

Each `AutoPushFrame` carries the original byte buffer plus four
properties for the decoded data:

| Property | Returns |
| --- | --- |
| `frame.resultant_forces` | `{module_name: (Fx_lsb, Fy_lsb, Fz_lsb)}` |
| `frame.resultant_forces_newtons` | Same, in newtons |
| `frame.distributed_forces` | `{module_name: [(Fx_lsb, Fy_lsb, Fz_lsb), ...]}` (one tuple per tactile point) |
| `frame.distributed_forces_newtons` | Same, in newtons |

Sensor coordinate lookup:

```python
from paxini_sdk import sensor_registry

# By point count
v = sensor_registry.find_by_point_count(52)
print(v.vendor_part_code, v.sensor_model, v.geometry)
# PXSR-STDDP03G  PX6AX-GEN3-DP-S2015-Elite  fingertip

# By part code
v = sensor_registry.find_by_part_code("PXSR-STDDP03F")

# Get the (x, y, z) mm positions of each tactile point
pts = sensor_registry.load_points(v)  # list of 52 tuples for DP-S2015-Elite
```

---

## 7. Troubleshooting

### "No serial ports detected"

The CH340 USB-serial driver isn't installed, or the board isn't plugged
in. Open Device Manager; if the board shows up under "Other devices"
with a yellow exclamation mark, install the CH340 driver from
<https://www.wch.cn/downloads/CH341SER_EXE.html>.

### "ImportError: cannot import name 'HighSpeedHandBoard' from 'paxini_sdk' (unknown location)"

You're running Python from a directory whose subfolder shadows the
package. Easiest fix: `pip install -e .` from inside `sensor_testing/paxini_sdk/`.
Alternatively, just run scripts from `sensor_testing/` — the shipped
scripts have a sys.path tweak that handles this case.

### `paxini_to_rerun.py` prints "rerun-sdk is not installed"

`pip install rerun-sdk`.

### Smoke test prints `[2] active modules (0): []`

The board sees no sensor on any slot. Check:

1. FPC cable is fully seated on both ends (board side and sensor side).
2. FPC cable polarity — the cable is keyed but easy to insert at an
   angle if you're not deliberate.
3. The sensor itself isn't damaged (try the Paxini host app to confirm).

### Paxini host app hangs on Open

The v1.0.11 host app auto-triggers a firmware upgrade if the board's
firmware is older than its target. On this hardware that upgrade times
out without applying anything, and the UI freezes. Recovery: Task
Manager → End task on `pxsr-gen3`, then unplug/replug USB. See
`FINDINGS.md` section "Vendor app v1.0.11 auto-OTA gotcha" for full
detail.

### Wrapper crashes with `FrameError: LRC mismatch`

The serial line dropped bytes mid-frame. Try:

1. A shorter USB cable.
2. Plug straight into the laptop (not through a hub).
3. Reduce other USB traffic during the run.

This isn't normal on a healthy connection — if it persists, capture
`wrapper_run_X.txt` and we can debug.

---

## 8. When you need to grow this

A few extension points the wrapper anticipates:

- **More sensors**: a new GEN3 variant just needs its xlsx extracted to
  a `pxsr_*_points.json` and an entry in `registry.json`. The visualizer
  picks it up automatically because the lookup goes by point count.
- **Other comm boards**: `SingleSensorBoard` (for the Serial Converter
  Board) is in `paxini_sdk/boards/serial_converter.py`. Untested on
  current hardware but follows the same shape.
- **Different output format**: `paxini_to_rerun.py` is one consumer of
  `stream_auto_push()`. Write your own loop if you want CSV output,
  Kafka, ROS, etc. — the wrapper has no opinion.
- **Higher rate**: if you need the wire's max ~545 Hz, disable the
  distributed-force grid by writing `0x01` to register 0x0016
  (`hand.write_register(0x0016, b"\x01")`). Each frame shrinks to 6 bytes
  of resultant force; many hundreds of Hz are then possible.

---

## 9. Recording per-taxel data to CSV (added 2026-05-18)

Three entry points, all use the same `paxini_sdk.recording.CsvRecorder`
under the hood. Default format is vendor-compatible — files are
drop-in replayable through `paxini_to_rerun.py --csv`.

```powershell
# Smoke-test + record in one go
python smoke_test.py --port COM7 --duration 25 --record runs/sm.csv

# Dedicated recorder (no terminal noise, run-until-Ctrl-C)
python record.py --port COM7 --out runs/session1.csv --calibrate

# Live rerun viewer + record simultaneously
python paxini_to_rerun.py --port COM7 --record runs/with_viz.csv
```

Each row contains: `Timestamp` + per-active-module `(Fx, Fy, Fz)` resultant
plus the full N×3 distributed-force grid (so for DP-S2015-Elite that's
1 + 3 + 156 = 160 columns per row). Values are **raw LSB counts**
(multiply by 0.1 for newtons), matching the Paxini host-app's recordings.

Add `--native` to any of the three for wrapper-native column names
(`index_tip_resultant_fx_lsb`, `index_tip_pt000_fz_lsb`, etc.) plus a
`#`-prefixed JSON metadata header with the firmware version, active
modules, point counts, and timestamp of the recording start. Easier to
parse in pandas, but not replayable through `--csv`.

Rows are flushed to disk after every frame, so Ctrl+C at any point loses
at most the last frame.
