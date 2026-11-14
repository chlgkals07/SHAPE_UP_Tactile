from __future__ import annotations

from fake_sysfs import make_usb

from control_hub.checks import CheckResult
from control_hub.discovery import scan


def rig(tmp_path):
    make_usb(tmp_path, "1-2", "0403:6014", serial="FT8ZABCD", tty="ttyUSB1", latency=1)
    return make_usb(tmp_path, "2-1", "8086:0b5b", serial="3351", speed=5000,
                    product="Intel RealSense D405", video="video0")


def test_scan_lists_and_labels(tmp_path, cfg):
    sys_root, dev_root = rig(tmp_path)
    cfg = cfg.__class__(**{**cfg.__dict__, "known_usb": {"8086:0b5b": "RealSense D405"}})
    found = scan(cfg, {}, sys_root, dev_root)
    by_id = {d["usb_id"]: d for d in found["devices"]}
    assert by_id["8086:0b5b"]["label"] == "RealSense D405"
    assert by_id["8086:0b5b"]["videos"] == ["video0"] and by_id["8086:0b5b"]["speed_mbps"] == 5000
    assert by_id["0403:6014"]["label"] == "" and by_id["0403:6014"]["ttys"] == ["ttyUSB1"]


def test_misplaced_leap(tmp_path, cfg):
    sys_root, dev_root = rig(tmp_path)
    found = scan(cfg, {"port": CheckResult(False, "없음")}, sys_root, dev_root)
    [hint] = found["misplaced"]
    assert hint["device"] == "hand" and hint["check"] == "port"
    assert hint["found"] == str(dev_root / "ttyUSB1")
    assert hint["text"] == f"손 이 {dev_root / 'ttyUSB1'} 에 있는 것 같습니다"


def test_no_misplaced_when_check_ok(tmp_path, cfg):
    sys_root, dev_root = rig(tmp_path)
    found = scan(cfg, {"port": CheckResult(True, "ok")}, sys_root, dev_root)
    assert found["misplaced"] == []
