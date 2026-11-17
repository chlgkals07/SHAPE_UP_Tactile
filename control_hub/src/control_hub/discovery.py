"""The "what is plugged in" page: list USB devices, and say when a device seems to sit on a
different port than the config expects. It only shows; it never changes the config."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from control_hub.checks import CheckResult
from control_hub.config import HubConfig
from control_hub.sysfs import DEV, SYS, usb_devices


def scan(cfg: HubConfig, checks: dict[str, CheckResult], sys_root: Path = SYS,
         dev_root: Path = DEV) -> dict:
    found = usb_devices(sys_root, dev_root)
    devices = [{**asdict(d), "ttys": list(d.ttys), "by_id": list(d.by_id),
                "videos": list(d.videos), "label": cfg.known_usb.get(d.usb_id, "")}
               for d in found]
    misplaced = []
    for device in cfg.devices.values():
        if not device.usb_id:
            continue
        ttys = [t for d in found if d.usb_id == device.usb_id for t in d.ttys]
        for cid in device.checks:
            check = cfg.checks[cid]
            result = checks.get(cid)
            if check.kind not in ("serial", "file") or not ttys or result is None or result.ok:
                continue
            where = str(dev_root / ttys[0])
            misplaced.append({"device": device.id, "check": cid, "expected": check.target,
                              "found": where,
                              "text": f"{device.title} 이 {where} 에 있는 것 같습니다"})
    return {"devices": devices, "misplaced": misplaced}
