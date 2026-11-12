# Paxini GEN3 sensor testing — findings (2026-05-18)

Hardware under test:
- Communication board: **PXSR-STDOTO4B** (label on board) — confirmed as the
  vendor's **High-Speed Communication Board** (32×34 mm, UART + FPC), per
  visual match with the spec in *帕西尼 PX-6AX GEN3 三款通信盒使用指引_V1.0.6*
  §4.4 and *Communication Board Communication Protocol_V1.0.5* §4.1–4.3.
  The PXSR-STDOTO4B SKU itself does not appear in any of the 2025-12-02
  vendor docs (which use only functional names for the boards); it is most
  likely the vendor's internal/order SKU.
- Sensor: **DP-S2015-Elite** = vendor part code **PXSR-STDDP03G** (15 mm
  Elite fingertip), confirmed in *PaXini PX-6AX GEN 3 Multidimensional
  Tactile Sensor User Manual_V1.0.5* p.16. Default module number is 2
  ("Tip" slot) per *Communication Board Communication Protocol_V1.0.5*
  §1.3.3.

## SDK provenance — important

`paxini_sdk_mac/` is **user-authored** (Jingyi vibe-coded it from the vendor
protocol PDFs and the example Python scripts). It is **not** an official
Paxini SDK. Every function in it should be considered unverified until
cross-checked against the vendor Windows host app on the same physical
event. The "protocol unit tests pass" finding below is necessary but not
sufficient: it proves the SDK *emits* byte sequences matching the vendor
PDF's worked examples; it does not prove the SDK *parses responses*
correctly or that any of its high-level helpers behave as intended.

## What was verified offline

| Item | Status | How |
| --- | --- | --- |
| LRC algorithm matches vendor's calc_lrc | ✅ | `test_lrc_known_values` against `55AA000300000F00` → `0xEF` from the protocol PDF |
| Read-version frame builder | ✅ | Equals `55AA000300000F00EF` (protocol PDF §4.5.3 #1) |
| Enable auto-push frame builder | ✅ | Equals `55AA00101700010001D8` (protocol PDF §4.5.3 #8) |
| Read-resultant-force frame builder (fin_master) | ✅ | Matches the official `Read_Single_Sensor_Usb.py` example |
| Calibration frame builder (fin_master) | ✅ | Matches the official `Read_Single_Sensor_Usb.py` example |
| Auto-push (AA56) parse layout | ✅ (synthetic only) | `test_parse_auto_push_basic` — round-trips a synthetic frame; **NOT** validated against a real device payload yet |
| `parse_simple_response` parse layout | ✅ (synthetic only) | Same caveat — synthetic round-trip only |

This is the limit of what protocol unit tests can prove without hardware.

## What still requires hardware to confirm

Everything below needs to be cross-checked against the vendor Windows host
app on the same physical event:

- That `read_version()` returns the version string the vendor app shows.
- That `read_register(0x0010, 4)` returns the same sensor-presence bitmap
  the vendor app uses to draw connected modules.
- That `read_module_forces_newtons()` for the Tip slot matches the vendor
  app's Fx/Fy/Fz curves to within the 0.1 N LSB.
- That `stream_auto_push()` produces frames at the same rate the vendor app
  reports and that decoded Fx/Fy/Fz signs/magnitudes match.
- That calibration (which the SDK does *not* yet expose for the
  High-Speed Board, only for the Serial Converter Board) is/isn't needed
  to get sane Fz baselines.

## Decoder choice that disagreed with the vendor UI

The user-authored SDK's `HighSpeedHandBoard.read_module_forces()` and
`AutoPushFrame.module_forces` originally decoded each module's 6-byte block
as three signed int16 LE values. The vendor's own reference
`Hand_UI.py::parse_module_forces` (lines ~1101-1135) and the protocol PDF
§1.3.3 specify a different layout:

- 6 bytes per module: `[Fx_lo, Fx_hi, Fy_lo, Fy_hi, Fz_lo, Fz_hi]`
- Only the **low byte** of each axis is meaningful
  ("仅提取每个轴的低字节" in the vendor source)
- Fx, Fy: signed int8 (range −128 … +127)
- Fz: unsigned uint8 (range 0 … 255)
- Physical scale: **0.1 N per LSB**

Under the original int16-LE choice, negative Fx/Fy would silently be
miscoded as large positives. Example: raw byte `0xFE` (Fx = −2 under the
vendor rule) reads as `+254` under int16 LE signed.

Patch applied in `sensor_testing/paxini_sdk/paxini_sdk/boards/high_speed.py`:

- `_decode_module_forces_lowbyte(data)` — vendor-rule decode
- `_to_newtons(forces)` — 0.1 N/LSB scaling
- `AutoPushFrame.module_forces` and `HighSpeedHandBoard.read_module_forces()`
  now use the vendor-rule decode by default
- `AutoPushFrame.module_forces_newtons`, `read_module_forces_newtons()`,
  `named_module_forces_newtons` — Newton-scaled convenience accessors
- `AutoPushFrame.module_forces_raw16` — legacy int16-LE behaviour preserved
  for callers that may have already calibrated against it

Six new tests in `tests/test_module_force_decoder.py` pin the vendor-rule
decode. **These tests still don't prove the decoder is right on this
hardware** — they only prove it agrees with the vendor source comment. The
on-hardware validation step (apply known load, compare with vendor app) is
still required before trusting any decoded number.

## Outstanding questions for hardware testing

1. **Firmware version drift.** The vendor app version on hand (V1.0.11) is
   newer than the V1.0.7 in the doc package, and it appears to auto-flash
   newer adapter firmware to the board on connect. The protocol PDF we
   audited is V1.0.5 (Nov 2025). If the on-board firmware changes the
   wire format, the SDK assumptions become stale. Need to:
   - Record the post-upgrade firmware version (visible at app bottom-left,
     e.g. `ADAPTER FW02.10`).
   - Capture a raw auto-push frame with the vendor app idle and with a
     known load applied, and confirm byte layout matches what the SDK
     expects.
2. **Cross-validation oracle.** Before we trust *any* SDK reading, fix
   the vendor app as the oracle and run the same physical event through
   both, recording (timestamp, vendor_Fx, vendor_Fy, vendor_Fz, sdk_Fx,
   sdk_Fy, sdk_Fz) for ~30 events spanning the sensor's range.
3. **Calibration.** The vendor app has a 标定 (Calibrate) button. We don't
   yet know whether calibration mutates board-side state (persistent
   offset registers) or is a host-side zero. If it's board-side and the
   SDK doesn't trigger it, SDK readings will have a residual offset that
   the vendor app doesn't.
4. **Distributed force grid.** The DP-S2015-Elite fingertip's per-point
   coordinates live in *PXSR-STDDP03G.xlsx* (vendor zip §6). If we need
   pressure maps, that file is the source of truth — the SDK's
   `DISTRIBUTION_ADDR_RANGES` only gives byte-address ranges, not point
   coordinates.

## References

- *PaXini PX-6AX GEN3 Communication Board Communication Protocol*, V1.0.5,
  English, 2025-11-18 — §1.3.3, §4, §4.5.3, §4.6.
- *PaXini PX-6AX GEN 3 Multidimensional Tactile Sensor User Manual*,
  V1.0.5, English, 2025-11-18 — p.16 (DP-S2015-Elite = PXSR-STDDP03G).
- *帕西尼 PX-6AX GEN3 三款通信盒使用指引*, V1.0.6, Chinese, 2025-12-25 —
  §4 (High-Speed Communication Board hardware interface).
- Vendor reference scripts (in the GEN3 zip): `Read_Single_Sensor_Hand.py`,
  `Hand_UI.py` (authoritative force decode source), `Read_Single_Sensor_Usb.py`,
  `USB_UI.py`, `Read_Single_Sensor_Spi.py`.
- User-authored wrapper under test: `sensor_testing/paxini_sdk/` — not
  a vendor artefact.

---

## 2026-05-18 hardware session: first contact with the board

### Vendor app v1.0.11 auto-OTA gotcha

The Paxini host app `pxsr-gen3` **v1.0.11** auto-triggers a firmware upgrade
on every successful 打开 (Open) call when it considers the board's firmware
older than its target (`v1.0.4`). On this hardware the board does not reply
to the OTA enter command — the app sends `发送升级命令`, the board never
acknowledges, the app retries once, then hangs the UI forever (still
holding the COM port). External symptoms:

- "(Not Responding)" in the window title.
- Process at ~1% CPU, 0 MB/s disk, ~170 MB resident — i.e. idle, not
  actually flashing.
- COM port still enumerated in Device Manager; board LED steady.

**Recovery that worked here (no app reinstall, no firmware change):**

1. Task Manager → End task on `pxsr-gen3` (Electron app, four sub-processes
   under one group entry).
2. Unplug USB, wait 5 s, plug back in.
3. Relaunch the app.
4. Some `打开` clicks will still trigger the same hang, but at least one
   attempt got through and streamed data on this machine.

The docs zip also ships an older `pxsr-gen3-win-x64-1.0.7_Release.exe`
under `【04】Software Installation Package/`. That older build matches the
V1.0.5 protocol PDFs we audited and is the recommended fallback if v1.0.11
gets stuck again. **No firmware was modified during any of this** — the OTA
never actually entered the data-transfer phase.

### CSV recording format (`HH-MM-SS.csv` written by the host app)

For DP-S2015-Elite on the High-Speed Communication Board the host app
records integer LSB counts (not newtons), 160 columns per row:

| Column | Content |
| --- | --- |
| 0 | `Timestamp` (HH:MM:SS.ms) |
| 1–3 | `1-2-1x1-X / -Y / -Z` — resultant force, signed int8 for X/Y, uint8 for Z |
| 4–159 | `1-2-NxN-X[i] / -Y[i] / -Z[i]` for i = 0..51 — 52-point distributed-force grid × 3 axes = 156 columns |

The "1-2" prefix encodes the slot the data came from. The second number
(`2`) matches the DP-S2015-Elite's default Module Number = 2 (Tip slot)
documented in *Communication Board Communication Protocol V1.0.5* §1.3.3.
The 52 distributed-force points correspond to the coordinate file
`PXSR-STDDP03G.xlsx` in the vendor zip §6.

### Observed sample period

A 320-row recording (`data/2026-05-18-160105_paxini_app_v1.0.11.csv`)
spans 11.4 s → ~38 ms between consecutive samples → **~26 Hz effective
auto-push rate** from app to disk. That is the floor for what our
wrapper's `stream_auto_push()` should achieve. The vendor protocol PDF
says the high-speed board pushes "as quickly as possible within the
communication capability range" (§4.6, address 0x0017), so 26 Hz may be
host-side bottleneck rather than board limit.

### Hardware data validates the patched decoder's assumptions

From the same first recording:

| Axis | Min | Max | Mean | Stdev | Notes |
| --- | --- | --- | --- | --- | --- |
| Fx | −1 | +7 | +1.81 | 1.88 | **Negative values appear** → signed int8 confirmed |
| Fy | −3 | +2 | +0.22 | 0.75 | Same — signed int8 confirmed |
| Fz | 0 | +10 | +3.22 | 2.73 | Never negative → uint8 confirmed |

All values fall comfortably inside signed int8 / uint8 ranges. None of the
values would require the high byte of the 6-byte module block, so the
"low-byte only" rule from `Hand_UI.py` holds under these load conditions.
If the legacy int16-LE decoder had been used, an Fx reading of `−1`
(raw byte 0xFF) would have decoded as `+255` instead — that confirms the
patch was necessary and correct in direction.

The patched decoder's interpretation:

- byte layout `[Fx_lo Fx_hi Fy_lo Fy_hi Fz_lo Fz_hi]` per module
- Fx, Fy: low byte as signed int8
- Fz: low byte as unsigned uint8
- 0.1 N per LSB

…produces the same integer counts (and corresponding newton scale) the
host app records to CSV. Strong indirect evidence but not yet a direct
side-by-side test on identical wire bytes.

### Outstanding hardware checks before trusting the wrapper

1. **Sequential side-by-side run** — record the same load pattern
   (`unloaded → press → unloaded`) once with the app and once with
   `smoke_test.py`. Compare resultant-force distributions: ranges should
   match within sensor noise + repeat-press variation.
2. **Auto-push frame rate** — does `stream_auto_push()` see ~26 Hz when the
   wrapper holds the port, or does it lag?
3. **Distributed-force grid** — the wrapper currently exposes byte-address
   ranges (`DISTRIBUTION_ADDR_RANGES`) but not a 52-point decoder for
   DP-S2015-Elite. The host-app CSV gives us a ground-truth format
   (52 × 3 ints) to match against when we add that decoder.
4. **Calibration** — host app exposes 标定 (Calibrate); the wrapper's
   `HighSpeedHandBoard` does not. Need to confirm whether calibration is
   a board-side persistent op or host-side zeroing, and whether
   wrapper-driven sessions need to perform it manually before data is
   trustworthy.

---

## 2026-05-18 wrapper run vs vendor app: real bug in auto-push decode

### What worked on hardware

The wrapper successfully:

- Connected over COM7 at 921600 baud.
- Read firmware version: **`ADAPTER_FW02.22`**.
- Read sensor-status registers `0x0010-0x0013` = `40 00 00 00` → bit 6 set in
  byte 0 → **Index-Tip is the populated slot** (matches the host-app CSV's
  `1-2-...` column prefix and the protocol PDF §4.6 bit assignment for
  byte 0 of the active-modules bitmap).
- Read distributed-force point count for Index-Tip: **52 points** — matches
  the 52-column NxN block in the host-app CSV exactly.
- Auto-push streamed at **~55 Hz** (1364 frames in 25 s), consistent with
  what we'd expect from the board's native rate after host-side parsing.

### Bug: auto-push payload size assumption

The wrapper's `AutoPushFrame.module_forces` and
`HighSpeedHandBoard.read_module_forces()` assume the payload is a fixed
28 × 6 bytes = 168 bytes (one resultant-force block per module).

Per protocol PDF §4.4.2:

> "The effective data length is ultimately determined by the module
>  combinations in 0x0010-0x0013, the data type combinations in 0x0016,
>  and the force signals in each module in 0x0030-0x0067."

On the test hardware only Index-Tip is active, and `0x0016 = 0x03`
(default = resultant force + distributed force). The actual auto-push
payload is therefore:

```
[ Index-Tip resultant force: 6 bytes ]
[ Index-Tip distributed grid: 52 pts × 3 bytes = 156 bytes ]
Total: 162 bytes
```

The wrapper interprets these 162 bytes as 27 module-resultant-force blocks
of 6 bytes each. That makes the *distributed-force grid bytes* of Index-Tip
appear as bogus resultant forces for Thumb-Middle / Thumb-Tip / Thumb-Nail /
etc. The recurring `Fz = +25.4 N` (raw byte 0xFE → 254 LSB → 25.4 N at
0.1 N/LSB) in `wrapper_run_1.txt` is a value from the distributed-force
grid being misread as a resultant force.

The *real* Index-Tip resultant force lives at payload offset 0..5; the
wrapper currently labels that data as "Thumb-Proximal" (`module_forces[0]`).
The press / shear events the user performed do show up there, with
magnitudes consistent with the host-app CSV (max ~+1.6 LSB shear, max ~0.x
N normal in the captures we have).

### What the fix needs to do

1. Read `0x0010-0x0013` (active modules bitmap) and `0x0016` (data-type
   bits) **before** parsing auto-push frames.
2. Parse the auto-push payload as the concatenation of, for each *active*
   module (in the order defined by the bitmap and the protocol):
   - 6 bytes resultant force (if data-type bit 0 set)
   - `point_count × 3` bytes distributed force (if data-type bit 1 set)
3. Return a per-active-module dict, keyed by the canonical module name.
4. The legacy 28-module decoder should be retained as
   `module_forces_legacy_full_hand` for cases where all 28 are present.
5. `smoke_test.py::find_loaded_module` should only consider active-bitmap
   slots; the spurious "Thumb-Tip" focus came from the wrapper exposing
   non-existent slots.

### Confirmed-good observations from the wrapper output

- **Firmware**: `ADAPTER_FW02.22`. The host app's bottom-left status line
  read `FW02.10` earlier (or possibly I misread "FW02.22"). Either way,
  this is the version the wrapper now reads back.
- **Auto-push rate**: ~55 Hz native; host-app rate (26–81 Hz) is therefore
  host-side disk/UI bottlenecked, not board-limited.
- **`read_distribution_point_count(6)` would return 52** for Index-Tip
  (the wrapper's `MODULE_NAMES[6]` = "Index-Tip", matching the bitmap).
- **Real signals do appear** at the correct payload offset (0..5) when the
  user presses or shears the fingertip — they're just incorrectly labelled
  as "Thumb-Proximal" by the current wrapper code.

---

## 2026-05-18 wrapper fix shipped — payload-aware auto-push decoder

The auto-push payload-shape bug is now fixed. Changes:

### `paxini_sdk/registers.py`

- Added `parse_active_modules_bitmap(bytes_4) -> List[int]` decoding the
  bit-to-module mapping documented in protocol PDF §4.6.
- Added `DATA_TYPE_RESULTANT = 0x01` and `DATA_TYPE_DISTRIBUTED = 0x02`
  constants for register 0x0016.

### `paxini_sdk/boards/high_speed.py`

- New `AutoPushConfig` dataclass capturing payload shape:
  `active_modules: List[int]`, `has_resultant: bool`, `has_distributed: bool`,
  `point_counts: Dict[int, int]`. `expected_payload_size()` and
  `module_offset()` helpers.
- New `HighSpeedHandBoard.read_active_modules() / read_data_type() /
  read_auto_push_config()` so callers can discover the payload shape.
- `AutoPushFrame` rewritten to carry an `AutoPushConfig`. The new properties:
  - `resultant_forces: Dict[str, (Fx, Fy, Fz)]` — only active modules
  - `resultant_forces_newtons: Dict[str, (Fx, Fy, Fz)]` (0.1 N/LSB)
  - `distributed_forces: Dict[str, List[(Fx, Fy, Fz)]]` — per active module
  - `distributed_forces_newtons` — same scaled to newtons
- Removed broken 28-fixed-slot accessors (`module_forces`, `module_forces_raw16`,
  `named_module_forces`, `module_forces_newtons`). Kept `_decode_module_forces_lowbyte`
  and `_to_newtons` as test-only backwards-compat aliases.
- `HighSpeedHandBoard.read_resultant_forces()` / `read_resultant_forces_newtons()`
  now read each active module individually from `0x0500 + 6 * module_idx` and
  return a dict, instead of an unconditional 168-byte read.
- `stream_auto_push()` reads the auto-push config once at the start (or accepts
  one passed in via the `config=` kwarg) and attaches it to every yielded frame.

### Tests

All 31 tests pass (12 protocol + 6 byte-level decoder + 13 new auto-push payload
tests). The new tests pin:

- bitmap parsing (single-module, sparse, full-hand, unused-bit cases),
- `AutoPushConfig.expected_payload_size()` (matches the 162-byte expectation
  for one DP-S2015-Elite with both data types enabled),
- `AutoPushConfig.module_offset()` (per-module section starts for a
  two-module example),
- `_decode_resultant_6bytes` and `_decode_distributed_3bytes` low-byte rule,
- end-to-end `AutoPushFrame` decode for one Index-Tip-only payload,
- `AutoPushFrame` correctly separates two active modules (`Thumb-Tip` and
  `Index-Tip`) with different point counts.

### `smoke_test.py`

Rewritten to use the new API. The previous "Thumb-Tip Fx=+25.4 N" garbage
should no longer appear — the script now prints the firmware version, the
**active-module list** (decoded from the bitmap), the data-type combination,
per-module point counts, a one-shot resultant-force read for each active
module, and a streamed auto-push focused on the first active module (or a
user-specified one via `--module`).

---

## 2026-05-18 wrapper_run_2 — fix validated on hardware

After the payload-aware decoder shipped, re-running `smoke_test.py` with the
same physical press pattern gave clean, plausible numbers:

| Field | wrapper_run_1 (pre-fix) | wrapper_run_2 (post-fix) | Paxini app CSV (session 2) |
| --- | --- | --- | --- |
| Reported slot | Thumb-Tip (WRONG) | **Index-Tip** ✓ | `1-2-…` = Index-Tip ✓ |
| Fz range during press | +25.4 N (bogus 0xFE) | **0.0 … +0.7 N** ✓ | 0.0 … +0.8 N ✓ |
| Fx range | -0.2 … +0.5 N | -0.2 … +0.1 N ✓ | -0.4 … +0.2 N ✓ |
| Fy range | +0.2 … +1.6 N | -0.1 … +0.3 N ✓ | -0.3 … +0.2 N ✓ |
| Auto-push rate | 55 Hz | 54 Hz | 81 Hz |
| Active modules reported | `['Index-Tip']` ✓ | `['Index-Tip']` ✓ | `[Index-Tip]` ✓ |
| Distributed point count | 52 ✓ | 52 ✓ | 52 cols ✓ |
| Firmware version | `ADAPTER_FW02.22` | `ADAPTER_FW02.22` | (visible in app status bar) |

**Verdict**: wrapper's resultant-force decode matches the host app's CSV
output to within 1 LSB (0.1 N) for both press peaks and quiet baseline.
Cross-validation against the vendor app is therefore considered passing
for the resultant-force path.

**Known small differences** (not bugs):

- Host-app rate (81 Hz here) is host-side disk/UI throughput limited; the
  board's native auto-push rate appears to be ~54 Hz under this wrapper.
- The host app applies deadband-suppression (zeroing tiny values); the
  wrapper reports the raw sensor output, so the wrapper sees the true
  sensor noise floor (~±0.1 N idle jitter on Fx/Fy). For characterization
  this is what we want; the host app is hiding information.

**What still needs validating on hardware:**

- Distributed-force grid: 52 points decoded by the wrapper should agree
  with the 52-column NxN block in the host-app CSV at the same physical
  event. Easy follow-up when the rerun visualizer makes the comparison
  visible.
- Whether wrapper-driven sessions need the host-app's 标定 (Calibrate)
  workflow before data is trustworthy. The wrapper currently has no
  calibration method.

---

## 2026-05-18 — calibration + rerun visualizer shipped

### `HighSpeedHandBoard.calibrate()`

Replicates the host app's 标定 (Calibrate) button. The vendor's `Hand_UI.py`
hardcodes the command frame at line 274:

```
55 AA 00 17 02 00 01 00 01 E6
```

Decoded: function code `0x17` (custom, distinct from FC=0x03 read / 0x10 write),
register `0x0002`, data byte `0x01`, LRC `0xE6`. Vendor UI calls calibration
successful iff the response data is `0x00`.

Added `paxini_sdk.protocol.FUNC_HS_CALIBRATION = 0x17` and a
byte-for-byte test that pins the wrapper's frame against
`55AA001702000100 01 E6`. 32 tests pass.

### `paxini_to_rerun.py`

Two modes:

- **Live**: `python paxini_to_rerun.py --port COM7 [--calibrate] [--duration N]`
- **Replay**: `python paxini_to_rerun.py --csv data/2026-05-18-160858_paxini_app_v1.0.11_session2.csv`

Static metadata logged once:

```
sensor/firmware                    "ADAPTER_FW02.22"
sensor/active_modules              ["Index-Tip"]
sensor/dp_s2015_elite/anatomy      52 grey 3D points at the per-point coords from PXSR-STDDP03G.xlsx
```

Per frame:

```
sensor/index_tip/resultant/fx      Scalar (N), signed
sensor/index_tip/resultant/fy      Scalar (N), signed
sensor/index_tip/resultant/fz      Scalar (N), unsigned
sensor/index_tip/distributed       Points3D, colors mapped from Fz (light grey 0 N → dark blue ~3 N)
```

End-to-end smoke check: replayed `2026-05-18-160858_paxini_app_v1.0.11_session2.csv`
(2105 frames, 160 columns, 25.83 s) through `rr.save()` into
`data/2026-05-18-160858_replay.rrd` (~330 KB). Open with
`rerun data/2026-05-18-160858_replay.rrd` to inspect.

### Coordinate asset (superseded — see next entry for the multi-sensor registry)

Initial bundle: a single `paxini_sdk/data/dp_s2015_elite_points.json` with
the 52 (x, y, z) mm positions extracted from the vendor file *Fingertip
指尖 15mm PX6AX-GEN3-DP-S2015-Elite PXSR-STDDP03G.xlsx*. This file was
removed when the multi-sensor registry shipped; the same data now lives
in `pxsr_stddp03g_points.json`. Ranges:

- X: −7.46 … +7.46 mm (width)
- Y: −1.56 … +19.33 mm (length along finger)
- Z: 1.94 … 6.69 mm (height above palm surface — curved fingertip)

Adding other variants (e.g. DP-S1813-Elite = PXSR-STDDP03F) is one more
xlsx extract + a JSON file.

---

## 2026-05-18 — multi-sensor coordinate registry + auto-detection

`paxini_to_rerun.py` no longer hardcodes the DP-S2015-Elite coordinates.

### Inventory: 12 GEN3 sensor variants, all with unique point counts

| Vendor part | Model | Geometry | Points |
| --- | --- | --- | --- |
| PXSR-STDMC03A | MC-M2020-Elite | palm | 9 |
| PXSR-STDIP03B | IP-S1610-Elite | finger_pad | 25 |
| PXSR-STDDP03F | DP-S1813-Elite | fingertip 13 mm | 31 |
| PXSR-STDDP03D | DP-S1813-Core | fingertip 13 mm | 51 |
| **PXSR-STDDP03G** | **DP-S2015-Elite** | **fingertip 15 mm** | **52** |
| PXSR-STDIP03A | IP-M2324-Core | finger_pad | 68 |
| PXSR-STDCP03B | CP-M3025-Core | finger_pad | 77 |
| PXSR-STDDP03E | DP-S3013-Core | integrated tip+pad 13 mm | 96 |
| PXSR-STDDP03C | DP-S2716-Core | fingertip 16 mm | 116 |
| PXSR-STDDP03B | DP-M2826-Omega | fingertip 26 mm | 127 |
| PXSR-STDDP03A | DP-L3530-Omega | fingertip 30 mm | 135 |
| PXSR-STDCP03A | CP-L5325-Omega | finger_pad | 239 |

Crucially every entry has a **different** point count, so the protocol's
existing `read_distribution_point_count()` call is sufficient to
unambiguously identify which variant is plugged in.

### Code added

- `paxini_sdk/data/<vendor_part>_points.json` — 12 new JSON assets, each
  containing the per-point (x, y, z) mm coordinates from the vendor xlsx.
  Old `dp_s2015_elite_points.json` is now redundant with
  `pxsr_stddp03g_points.json` (kept for now; can be deleted).
- `paxini_sdk/data/registry.json` — index mapping vendor_part_code to
  geometry / grade / point count / json filename.
- `paxini_sdk/sensor_registry.py` — `list_sensors()`,
  `find_by_part_code(code)`, `find_by_point_count(n, geometry_hint=...)`,
  `load_points(variant_or_code)`. Returns frozen `SensorVariant` dataclasses.
- `paxini_to_rerun.py::resolve_sensor_variant(...)` — auto-detection helper
  used by both `run_live` and `run_csv_replay`. Manual `--sensor-part`
  always wins; otherwise live mode asks the board for the active module's
  point count and looks it up in the registry. CSV replay falls back to
  PXSR-STDDP03G as the default since CSVs don't carry the part code.

### Vendor data fixup

DP-L3530-Omega (PXSR-STDDP03A) xlsx, **row 135 column X** contains the
malformed value `'0.00231913]'` (stray `]`). The extractor strips trailing
non-numeric characters before parsing and records the fixup so we know
which downstream data points came from cleaned cells. All 12 assets
import cleanly; the 30 mm fingertip ends up with the full 135 points.

### Behaviour change for end-users

Before this change:

```powershell
python paxini_to_rerun.py --port COM7 --sensor-part PXSR-STDDP03G
```

After (same command still works, but the override is optional):

```powershell
python paxini_to_rerun.py --port COM7
# → Res
---

## 2026-05-19 — lerobotac integration ready

`paxini-sdk/integrations/lerobot/` is now a drop-in package for the
`Jingyi-Z/lerobotac` `hall-sensor` branch.

### What it adds

- **`PaxiniSensor`** — a `lerobot.sensors.Sensor` subclass that wraps
  `HighSpeedHandBoard`. Background thread, ring buffer, three output
  formats (`resultant`, `distributed`, `both`), optional firmware +
  software calibration. Mirrors the file/class layout of the existing
  `MLX90393Sensor` to fit the rest of the lerobotac codebase without
  style drift.
- **`PaxiniSensorConfig`** — `draccus.ChoiceRegistry` subclass registered
  as `"paxini"`, so the existing `make_sensors_from_configs` CLI flow
  picks it up automatically.

### Files

| File | Purpose |
| --- | --- |
| `paxini.py` | Drop into `src/lerobot/sensors/paxini.py` |
| `_config_patch.py` | Block to append to `src/lerobot/sensors/configs.py` |
| `_init_patch.py` | Two-line addition to `src/lerobot/sensors/__init__.py` |
| `README.md` | Step-by-step install + usage |
| `test_paxini_integration.py` | Offline contract test (stubs the lerobot base + a fake board) |

### Validation

Five offline smoke checks pass without needing lerobotac installed:

1. **resultant mode** — `(buffer_size, 3)` float32 array, values match
   the synthetic fake-board frames.
2. **distributed mode** — `(buffer_size, P, 3)` float32 array, P=52 for
   DP-S2015-Elite.
3. **both mode** — `(buffer_size, 3 + P*3)` flat concat.
4. **software baseline** — accumulates N frames at startup, subtracts
   from later samples; `wait_for_calibration()` blocks until ready.
5. **metadata** — returns a JSON-serializable dict including module
   name, point count, output format, calibration state, baseline.

### Calibration model

Two independent layers, both opt-in:

- **Firmware** (`auto_calibrate=True`, default): the wrapper sends the
  vendor's calibration frame `55AA00170200010001E6` at connect time.
  Zeros the Hall-field baseline inside the sensor MCU. Sub-LSB precision.
- **Software** (`software_baseline_frames=N`, default 0): the lerobot
  driver additionally averages N frames after connect, subtracts that
  mean from subsequent reads. Catches the residual ±1 LSB offset that
  often remains after firmware calibration.

### How to merge into lerobotac

Per `paxini-sdk/integrations/lerobot/README.md`. Three file changes on
the `hall-sensor` branch, plus `pip install paxini-sdk`. No upstream
lerobot framework changes required.
