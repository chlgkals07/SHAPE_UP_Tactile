# paxini-sdk

Cross-platform Python SDK and command-line tools for **Paxini PX-6AX GEN3
multidimensional tactile sensors** — Hall-effect tactile sensors that
report 3-axis resultant force plus a 9–239-point distributed-force grid
depending on the variant.

Talks to the hardware the vendor's Windows host app supports
(Serial Converter Board / High-Speed Communication Board), with byte-exact
protocol match verified against the vendor's reference scripts and
real-hardware cross-checks.

Status: **beta**. Verified on hardware:

- High-Speed Communication Board **PXSR-STDOTO4B** (FW02.22) with the
  **DP-S2015-Elite** fingertip (PXSR-STDDP03G, 15 mm, 52 points) — 2026-05-18.
- Serial Converter Board with the **DP-L3530-Omega** fingertip
  (PXSR-STDDP03A, 30 mm, 135 points) — 2026-05-19.
- Host OS: Windows 10/11 and macOS (both exercised on hardware).

> Disclaimer: this is a community wrapper, not an official Paxini SDK.
> Force-decoding rules cross-checked against the vendor's `Hand_UI.py` and
> `USB_UI.py` reference programs; cross-validation against the vendor host
> app's CSV output is documented in `docs/FINDINGS.md`.

## What ships

```
paxini_sdk/                Importable package
  protocol.py              Frame builders + parsers + LRC + fin error codes
  transport.py             pyserial wrapper; length-based frame readers
  registers.py             Register addresses, module-name table, bitmap parser
  sensor_registry.py       Lookup for 12 GEN3 sensor variants
  recording.py             Streaming CSV writer (vendor + native formats)
  boards/
    high_speed.py          HighSpeedHandBoard + AutoPushFrame + AutoPushConfig
    serial_converter.py    SingleSensorBoard (Serial Converter Board)
  data/                    Per-variant (x, y, z) mm coordinate JSONs
  tools/
    smoke_test.py          → paxini-smoke         console script (high-speed)
    smoke_test_serial.py   → paxini-smoke-serial  console script (serial board)
    record.py              → paxini-record        console script
    to_rerun.py            → paxini-rerun          console script
    characterize.py        → paxini-characterize   console script
tests/                     52 offline unit tests (pytest)
docs/                      Usage guide, Windows + Mac setup, full findings log
```

## Install

```bash
# From a clone (recommended while in beta)
git clone https://github.com/Jingyi-Z/paxini-sdk.git
cd paxini-sdk
pip install -e ".[viz]"        # viz: also installs rerun-sdk

# Or just the core (no visualizer)
pip install -e .
```

Python ≥ 3.9. Only hard dependency is `pyserial`; `rerun-sdk` is optional
for visualization. Use `pip install -e ".[dev]"` for tests + everything.

## Two communication boards

The GEN3 sensors connect through one of two vendor boards; the SDK has a
driver class for each.

| Board | Driver class | Protocol | Rate | Sensors |
| --- | --- | --- | --- | --- |
| High-Speed Communication Board | `HighSpeedHandBoard` | auto-push stream | ~91 Hz | up to 28 modules; reports each module's point count |
| Serial Converter Board | `SingleSensorBoard` | request/response | ~176 Hz round-trip (length-based read) | one sensor; **cannot** report its model |

The High-Speed board reads the point count from register `0x0030`, so it
auto-detects the sensor variant. The Serial Converter Board has no such
register — you must tell `SingleSensorBoard` which sensor is attached
(`sensor="PXSR-..."` or `n_points=...`), exactly as the vendor `USB_UI.py`
makes the operator pick the model from a dropdown.

## Quick start

With USB power disconnected, connect all sensors to the comm board first,
then plug the board into USB. Repeat this power-off sequence when changing
sensors so the board refreshes its sensor configuration.
Make sure the USB-to-UART driver is loaded
(CH340 on Windows, see `docs/SETUP_WINDOWS.md` / `docs/SETUP_MACOS.md`).
For Linux and WSL 2, see [Linux / WSL setup](docs/SETUP_LINUX.md), including
USB forwarding from Windows, reusable commands, and ongoing work notes (Korean).

```bash
# Discover ports
paxini list

# --- High-Speed Communication Board ---
paxini-smoke --port COM7 --calibrate                       # Windows
paxini-smoke --port /dev/cu.usbserial-XXXX --calibrate      # macOS
paxini-smoke --port /dev/ttyACM0 --duration 10              # Linux / WSL (use paxini list)
paxini-rerun --port COM7 --calibrate                        # 3D rerun viewer
paxini-record --port COM7 --out runs/session1.csv --calibrate

# --- Serial Converter Board (must name the sensor) ---
paxini-smoke-serial --port COM3 --sensor PXSR-STDDP03A --calibrate
```

Replay an existing host-app CSV without hardware:

```bash
paxini-rerun --csv data/2026-05-18-160858.csv
```

## Python API

High-Speed Communication Board:

```python
from paxini_sdk import HighSpeedHandBoard

with HighSpeedHandBoard("COM7") as hand:
    print("Firmware:", hand.read_version())
    hand.calibrate()
    for frame in hand.stream_auto_push(duration=10.0):
        forces = frame.resultant_forces_newtons
        # {'Index-Tip': (0.2, -0.1, 0.8)}  in N
        distributed = frame.distributed_forces_newtons
        # {'Index-Tip': [(0.0, 0.0, 0.4), (0.0, 0.0, 0.5), ...]}
```

Serial Converter Board (request/response; name the sensor so the
distributed-force read uses the right length):

```python
from paxini_sdk import SingleSensorBoard

with SingleSensorBoard("COM3", sensor="PXSR-STDDP03A") as board:
    board.calibrate()
    fx, fy, fz = board.read_resultant_force()        # raw counts
    points = board.read_distributed_force()          # list of DistributedPoint
    # multiply counts by 0.1 for newtons
```

Force decoding rules (verified against vendor `Hand_UI.py` / `USB_UI.py`):

- High-speed module: 6 wire bytes `[Fx_lo Fx_hi Fy_lo Fy_hi Fz_lo Fz_hi]`,
  only low bytes meaningful, Fx/Fy signed int8, Fz uint8.
- Each distributed-force point: 3 wire bytes `[Fx_lo Fy_lo Fz_lo]`,
  same signed/unsigned rule.
- Scale: 0.1 N / LSB on every axis.

See `docs/USAGE_GUIDE.md` for the full walkthrough and `docs/FINDINGS.md`
for the protocol-decoding write-up and bugs found during cross-validation.

## Run the tests

```bash
pip install -e ".[test]"
pytest -q
```

Should print `52 passed`. Tests don't need hardware — they verify frame
builders, parsers, LRC, the payload-aware decoder, and the Serial Converter
Board point-count handling against synthetic frames and the vendor protocol
PDF's worked examples.

## Supported hardware

| Sensor variant | Vendor part code | Points |
| --- | --- | --- |
| MC-M2020-Elite (palm) | PXSR-STDMC03A | 9 |
| IP-S1610-Elite (finger pad) | PXSR-STDIP03B | 25 |
| DP-S1813-Elite (13 mm fingertip) | PXSR-STDDP03F | 31 |
| DP-S1813-Core (13 mm fingertip) | PXSR-STDDP03D | 51 |
| **DP-S2015-Elite (15 mm fingertip)** | **PXSR-STDDP03G** | **52** |
| IP-M2324-Core (finger pad) | PXSR-STDIP03A | 68 |
| CP-M3025-Core (finger pad) | PXSR-STDCP03B | 77 |
| DP-S3013-Core (integrated tip+pad) | PXSR-STDDP03E | 96 |
| DP-S2716-Core (16 mm fingertip) | PXSR-STDDP03C | 116 |
| DP-M2826-Omega (26 mm fingertip) | PXSR-STDDP03B | 127 |
| **DP-L3530-Omega (30 mm fingertip)** | **PXSR-STDDP03A** | **135** |
| CP-L5325-Omega (finger pad) | PXSR-STDCP03A | 239 |

All 12 variants have distinct point counts, so the High-Speed board's
reported count resolves the variant unambiguously. The Serial Converter
Board does not report a point count — pass the part code explicitly.

| Comm board | Class | Status |
| --- | --- | --- |
| **High-Speed Communication Board** | `HighSpeedHandBoard` | Verified on hardware (2026-05-18) |
| **Serial Converter Board** | `SingleSensorBoard` | Verified on hardware (2026-05-19) |
| 10-Channel SPI Hub | Not implemented | Patches welcome |

## License

MIT. See `LICENSE`.

## Acknowledgements

Built against the vendor's reference scripts shipped in the
*PaXini PX-6AX GEN3 product package_20251202* (`Hand_UI.py`,
`Read_Single_Sensor_Hand.py`, `Read_Single_Sensor_Usb.py`, `USB_UI.py`,
`Read_Single_Sensor_Spi.py`) and the *Communication Board Communication
Protocol_V1.0.5* PDF. The vendor docs were the source of truth for every
framing decision; the wrapper code is original.
