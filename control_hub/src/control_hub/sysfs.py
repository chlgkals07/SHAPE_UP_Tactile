"""What is plugged in, read from /sys and /dev without opening any device.

The hub never opens a serial port or a camera: the program that uses the device owns it.
Everything here is a directory listing or a small text file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SYS = Path("/sys")
DEV = Path("/dev")


@dataclass(frozen=True)
class UsbInfo:
    usb_id: str  # "0403:6014"
    manufacturer: str
    product: str
    serial: str
    speed_mbps: int | None
    bus_path: str  # "1-2.3": which port of which hub
    ttys: tuple[str, ...]
    by_id: tuple[str, ...]
    videos: tuple[str, ...]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _owner(node: Path) -> Path | None:
    """The USB device directory a tty or video node hangs under (the one with idVendor)."""
    try:
        path = node.resolve()
    except OSError:
        return None
    for parent in (path, *path.parents):
        if (parent / "idVendor").is_file():
            return parent
    return None


def _nodes(class_dir: Path) -> dict[Path, list[str]]:
    """{usb device dir: [node names]} for every node of a /sys/class directory."""
    out: dict[Path, list[str]] = {}
    if not class_dir.is_dir():
        return out
    for entry in sorted(class_dir.iterdir()):
        owner = _owner(entry / "device")
        if owner is not None:
            out.setdefault(owner, []).append(entry.name)
    return out


def _by_id(dev_root: Path) -> dict[str, list[str]]:
    """{tty name: [by-id link names]}"""
    out: dict[str, list[str]] = {}
    folder = dev_root / "serial" / "by-id"
    if not folder.is_dir():
        return out
    for link in sorted(folder.iterdir()):
        try:
            target = os.readlink(link)
        except OSError:
            continue
        out.setdefault(Path(target).name, []).append(link.name)
    return out


def usb_devices(sys_root: Path = SYS, dev_root: Path = DEV) -> list[UsbInfo]:
    folder = sys_root / "bus" / "usb" / "devices"
    if not folder.is_dir():
        return []
    ttys = _nodes(sys_root / "class" / "tty")
    videos = _nodes(sys_root / "class" / "video4linux")
    links = _by_id(dev_root)
    out = []
    for entry in sorted(folder.iterdir()):
        device = entry.resolve()
        vendor = _read(device / "idVendor")
        if not vendor or entry.name.startswith("usb"):  # root hubs are not devices
            continue
        speed = _read(device / "speed")
        tty_names = tuple(ttys.get(device, ()))
        out.append(UsbInfo(
            usb_id=f"{vendor}:{_read(device / 'idProduct')}",
            manufacturer=_read(device / "manufacturer"),
            product=_read(device / "product"),
            serial=_read(device / "serial"),
            speed_mbps=int(float(speed)) if speed else None,
            bus_path=entry.name,
            ttys=tty_names,
            by_id=tuple(name for tty in tty_names for name in links.get(tty, ())),
            videos=tuple(videos.get(device, ())),
        ))
    return out


def tty_info(tty: str, sys_root: Path = SYS, dev_root: Path = DEV) -> dict:
    """USB details, FTDI latency timer and by-id names of one tty ("ttyUSB0")."""
    usb = next((d for d in usb_devices(sys_root, dev_root) if tty in d.ttys), None)
    latency = _read(sys_root / "bus" / "usb-serial" / "devices" / tty / "latency_timer")
    return {
        "usb": usb,
        "latency_timer": int(latency) if latency.isdigit() else None,
        "by_id": _by_id(dev_root).get(tty, []),
    }
