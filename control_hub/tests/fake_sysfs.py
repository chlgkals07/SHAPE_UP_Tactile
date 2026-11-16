"""Build a tiny /sys + /dev tree shaped like the real one, for checks and discovery tests."""

from __future__ import annotations

import os
from pathlib import Path


def make_usb(root: Path, bus_path: str, usb_id: str, *, serial: str = "", speed: int = 480,
             product: str = "", manufacturer: str = "", tty: str | None = None,
             latency: int | None = None, by_id: str | None = None,
             video: str | None = None) -> tuple[Path, Path]:
    """Add one USB device (optionally with a tty or a video node). Returns (sys, dev) roots."""
    sys_root, dev_root = root / "sys", root / "dev"
    vendor, prod = usb_id.split(":")
    device = sys_root / "devices" / "pci0000:00" / "usb1" / bus_path
    device.mkdir(parents=True)
    for name, value in (("idVendor", vendor), ("idProduct", prod), ("serial", serial),
                        ("speed", str(speed)), ("product", product),
                        ("manufacturer", manufacturer)):
        if value:
            (device / name).write_text(value + "\n")
    links = sys_root / "bus" / "usb" / "devices"
    links.mkdir(parents=True, exist_ok=True)
    os.symlink(device, links / bus_path)
    interface = device / f"{bus_path}:1.0"
    interface.mkdir()
    if tty is not None:
        port = interface / tty  # usb-serial (FTDI) puts a port dir under the interface
        port.mkdir()
        tty_class = sys_root / "class" / "tty" / tty
        tty_class.mkdir(parents=True)
        os.symlink(port, tty_class / "device")
        if latency is not None:
            (port / "latency_timer").write_text(f"{latency}\n")
            serial_bus = sys_root / "bus" / "usb-serial" / "devices"
            serial_bus.mkdir(parents=True, exist_ok=True)
            os.symlink(port, serial_bus / tty)
        dev_root.mkdir(exist_ok=True)
        (dev_root / tty).write_text("")
        if by_id is not None:
            by_id_dir = dev_root / "serial" / "by-id"
            by_id_dir.mkdir(parents=True, exist_ok=True)
            os.symlink(f"../../{tty}", by_id_dir / by_id)
    if video is not None:
        video_class = sys_root / "class" / "video4linux" / video
        video_class.mkdir(parents=True)
        os.symlink(interface, video_class / "device")
    return sys_root, dev_root
