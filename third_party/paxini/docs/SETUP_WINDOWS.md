# Windows setup — Paxini PXSR-STDOTO4B + DP-S2015-Elite

Target machine: Windows. The vendor ships a Windows host app
(`pxsr-gen3-win-x64-1.0.7_Release.exe`) that you should install **both** for
day-to-day inspection and as the SDK cross-check oracle.

## 1. Install the USB-serial driver

The High-Speed Communication Board uses a USB-to-UART bridge. The vendor doc
*帕西尼 PX-6AX GEN3 三款通信盒使用指引_V1.0.6* §4 implies a CH340/CH341 bridge
(the most common choice on Chinese-built dev boards). Recent Windows 10/11
images usually include a CH340 driver out of the box, but it is *not*
guaranteed to be the right version.

1. Install the WCH CH341SER Windows driver from <https://www.wch.cn/downloads/CH341SER_EXE.html>
   (run as admin).
2. If your board enumerates as a Silicon Labs CP210x instead, install
   <https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers>.
3. Plug the board into a USB port, open **Device Manager → Ports (COM & LPT)**,
   and note the COM number assigned (e.g. `COM5`).

> If the device shows under **Other devices** with a yellow exclamation mark,
> the driver hasn't bound. Re-run the installer; reboot if needed.

## 2. Install the vendor Windows host app

From the product zip, double-click
`【04】Software Installation Package/pxsr-gen3-win-x64-1.0.7_Release.exe`.
Smoke-test with **DP-S2015-Elite plugged in**:

1. Launch the app, select the COM port from step 1.
2. Click **Open** / 打开. Firmware version should appear in the top right;
   the Fx/Fy/Fz curves on the right pane should respond to a light press on
   the fingertip.
3. Click **Calibrate** / 标定 to zero out, then re-press.

This confirms the board, driver, sensor, and physical connection are all
working **before** we trust the SDK output.

## 3. Install Python + the patched SDK

This project assumes Python 3.10 or newer (the SDK works back to 3.9).

```powershell
# In an admin PowerShell, ideally in a fresh virtualenv
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install pyserial pytest

# Install the patched SDK from this folder
cd "C:\Users\jingy\Documents\Claude\Projects\Tactile VLA based on SO-101\sensor_testing\paxini_sdk"
pip install -e .
```

Verify the patched protocol/decoder tests pass without hardware:

```powershell
pytest tests/ -v
```

You should see 18 tests passing — 12 from `test_protocol.py` + 6 from
`test_module_force_decoder.py`.

## 4. Discover the COM port from Python

```powershell
paxini list
```

Or in a Python REPL:

```python
from paxini_sdk import list_serial_ports
for p in list_serial_ports():
    print(p)
```

Use the COM number that matches the one you saw in Device Manager.

## 5. Smoke test the SDK against the board

With **the vendor host app closed** (it holds the COM port exclusively),
run:

```powershell
python "C:\Users\jingy\Documents\Claude\Projects\Tactile VLA based on SO-101\sensor_testing\smoke_test.py" --port COM5
```

(replace `COM5` with your port). The script:

1. Reads firmware version.
2. Reads register `0x0010-0x0013` (connected-sensor status bits).
3. Reads register `0x0030-0x0067` (per-module distributed-force point counts).
4. One-shot read of all 28 module forces (raw counts + newtons).
5. Streams auto-push for 2 seconds and prints the named force on the
   "Tip" slot the DP-S2015-Elite is attached to.

If steps 1–3 succeed but 4–5 show only zeros, the fingertip isn't physically
contributing to the channel you expect — check the FPC cable orientation.

## 6. Cross-check vs the vendor app

This is the validation step. With the fingertip under a known load (e.g.
gentle press, then a known reference weight), the SDK's
`read_module_forces_newtons()` value for the Tip slot should match the
vendor app's displayed value within ±0.1 N (the LSB).

If they disagree by orders of magnitude or sign, capture the raw auto-push
bytes (`paxini hand stream --verbose --duration 1`) and report; it would
indicate the byte layout assumption from the vendor UI source no longer
holds for this firmware revision.
