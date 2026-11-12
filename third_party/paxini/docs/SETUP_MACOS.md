# macOS setup

Step-by-step for Apple Silicon and Intel Macs.

## 1. USB-serial driver

The Paxini High-Speed Communication Board uses a CH340 (or sometimes CP210x)
USB-to-UART bridge chip. Recent macOS (≥ Big Sur) often ships a built-in CH340
DriverKit driver, but it's not guaranteed across all firmware revisions of
the chip. Two options:

### Option A — try without installing anything first

Plug the board in, then in Terminal:

```bash
ls /dev/cu.usbserial-*
# or, more general
ls /dev/cu.* | grep -iE 'usbserial|wch|silab'
```

If you see a `/dev/cu.usbserial-XXXX` entry, you're done — the macOS-builtin
driver picked it up. Skip to step 2.

### Option B — install the WCH CH340 macOS driver

If the device doesn't show up:

1. Download from <https://www.wch.cn/downloads/CH34XSER_MAC_ZIP.html>.
2. Open the `.dmg`, run the installer.
3. **System Settings → Privacy & Security**: look for a "system extension
   was blocked" banner and click Allow. You may need to reboot.
4. Re-plug the board and re-run `ls /dev/cu.usbserial-*`.

For Silicon Labs CP210x bridges instead:
<https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers>.

> Tip — prefer `/dev/cu.*` over `/dev/tty.*` for outgoing connections;
> `cu.*` doesn't block on DCD line.

## 2. Python environment

macOS ships its own Python, but for projects use Homebrew / pyenv:

```bash
# Quickest path with Homebrew
brew install python@3.12
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Then install paxini-sdk:

```bash
git clone https://github.com/Jingyi-Z/paxini-sdk.git
cd paxini-sdk
pip install -e ".[viz]"
```

Confirm it imported cleanly:

```bash
python -c "from paxini_sdk import HighSpeedHandBoard; print('OK')"
```

## 3. Smoke test on hardware

```bash
PORT=$(ls /dev/cu.usbserial-* | head -1)
paxini-smoke --port "$PORT" --calibrate --duration 10
```

Expected output (DP-S2015-Elite on the High-Speed Communication Board):

```
Opening /dev/cu.usbserial-XXXX @ 921600 baud ...
[1] firmware version: 'ADAPTER_FW02.22'
[2] active modules (1): ['Index-Tip']
[3] data-type 0x0016 = 0x03 (resultant, distributed)
[4] Index-Tip distributed-force points: 52
[4b] calibrating (zeroing baseline) ...
      calibration successful
[5] one-shot resultant forces (N):
      Index-Tip        Fx= +0.0  Fy= +0.0  Fz= +0.0
[6] streaming auto-push for 10.0 s, focus = Index-Tip ...
   ... (force readings as you press the silicone) ...
      received ~900 frames (~90 Hz over 10.0 s)
Done.
```

## 4. rerun viewer

Install (already pulled in by `[viz]`):

```bash
pip install rerun-sdk
```

Launch live:

```bash
paxini-rerun --port "$PORT" --calibrate
```

A rerun window will open. macOS may prompt for incoming-network-access
permission on first launch — allow it (it's just the local gRPC socket
between the Python script and the viewer process).

## 5. Things that bit us on Windows that probably won't bite on macOS

- **Vendor app v1.0.11 auto-OTA hang**: macOS has no vendor host app, so
  this doesn't apply. The wrapper never triggers an OTA on its own.
- **`time.sleep(0.001)` clock granularity**: macOS has a ~1 ms scheduler
  tick out of the box, so the transport's polling sleeps are tight. You
  may see slightly higher auto-push rate (~100 Hz vs Windows' ~91 Hz).
- **Port latency timer**: not a macOS concept; the CH340 driver does its
  own buffering. No tweaks needed.

## 6. Troubleshooting

- **"Device not configured" when opening port**: another process holds it.
  Run `lsof /dev/cu.usbserial-*` to find it, kill that process.
- **`paxini-rerun` exits with no viewer**: on older rerun-sdk versions,
  the connect-then-spawn fallback could hang. Use the latest
  `pip install --upgrade rerun-sdk`. If still flaky, run
  `rerun &` in another terminal first, then `paxini-rerun --connect ...`.
- **Permission denied on /dev/cu.\***: rare, usually after a system update.
  Add your user to the `wheel` or `_uucp` group, or sudo once to test.
