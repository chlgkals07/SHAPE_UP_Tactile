from __future__ import annotations

import os

import pytest
from fake_sysfs import make_usb

from control_hub import checks
from control_hub.checks import run_check
from control_hub.config import Check
from control_hub.sysfs import usb_devices


def test_ping_reports_ms(monkeypatch):
    # _sh keeps the last line, and that is ping's summary
    monkeypatch.setattr(checks, "_sh", lambda *a, **k: (
        0, "rtt min/avg/max/mdev = 0.412/0.412/0.412/0.000 ms"))
    result = run_check(Check("p", "p", "ping", "10.42.0.241"), {})
    assert result.ok and result.info["ms"] == pytest.approx(0.412)


def test_usb_devices_lists_tty_and_by_id(tmp_path):
    sys_root, dev_root = make_usb(
        tmp_path, "1-2", "0403:6014", serial="FT8ZABCD", tty="ttyUSB0", latency=1,
        by_id="usb-FTDI_Serial_FT8ZABCD-if00-port0", product="USB Serial")
    [dev] = usb_devices(sys_root, dev_root)
    assert dev.usb_id == "0403:6014" and dev.serial == "FT8ZABCD" and dev.speed_mbps == 480
    assert dev.ttys == ("ttyUSB0",) and dev.by_id == ("usb-FTDI_Serial_FT8ZABCD-if00-port0",)
    assert dev.bus_path == "1-2" and dev.product == "USB Serial"


def test_serial_found_with_latency_warning(tmp_path):
    sys_root, dev_root = make_usb(tmp_path, "1-2", "0403:6014", serial="FT8ZABCD",
                                  tty="ttyUSB0", latency=16, by_id="usb-FTDI-port0")
    check = Check("l", "l", "serial", str(dev_root / "ttyUSB0"))
    result = run_check(check, {}, sys_root=sys_root, dev_root=dev_root)
    assert result.ok and result.info["serial"] == "FT8ZABCD"
    assert result.info["tty"] == "ttyUSB0" and result.info["by_id"] == ["usb-FTDI-port0"]
    assert result.info["latency_timer"] == 16 and "latency timer 16" in result.warn


def test_serial_latency_one_has_no_warning(tmp_path):
    sys_root, dev_root = make_usb(tmp_path, "1-2", "0403:6014", tty="ttyUSB0", latency=1)
    result = run_check(Check("l", "l", "serial", str(dev_root / "ttyUSB*")), {},
                       sys_root=sys_root, dev_root=dev_root)
    assert result.ok and result.warn == ""


def test_serial_missing(tmp_path):
    result = run_check(Check("l", "l", "serial", str(tmp_path / "ttyUSB0")), {},
                       sys_root=tmp_path, dev_root=tmp_path)
    assert result.ok is False and result.detail == "없음"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_serial_no_permission(tmp_path):
    sys_root, dev_root = make_usb(tmp_path, "1-2", "0403:6014", tty="ttyUSB0")
    (dev_root / "ttyUSB0").chmod(0)
    result = run_check(Check("l", "l", "serial", str(dev_root / "ttyUSB0")), {},
                       sys_root=sys_root, dev_root=dev_root)
    assert result.ok is False and "권한 없음" in result.detail


def test_usb_speed_warning(tmp_path):
    sys_root, dev_root = make_usb(tmp_path, "2-1", "8086:0b5b", serial="335122272125",
                                  speed=480, product="Intel RealSense D405")
    check = Check("c", "c", "usb", "8086:0b5b", warn_below_mbps=5000)
    result = run_check(check, {}, sys_root=sys_root, dev_root=dev_root)
    assert result.ok and "480 Mbps" in result.warn and result.info["serial"] == "335122272125"


def test_usb_absent(tmp_path):
    result = run_check(Check("c", "c", "usb", "8086:0b5b"), {}, sys_root=tmp_path,
                       dev_root=tmp_path)
    assert result.ok is False and result.detail == "꽂혀 있지 않음"
