"""Turn the text that ``leap_check`` prints into the 16-motor table of the LEAP page.

``leap_check`` itself is not changed: if its output changes shape this returns None and the
page shows the raw output instead.
"""

from __future__ import annotations

import ast
import re

# Same order as user_pc leap_teleop.hand.joints.ANGLE_NAMES (copied: the hub imports nothing
# from user_pc).
LEAP_JOINTS = (
    "index_mcp_side", "index_mcp_flex", "index_pip_flex", "index_dip_flex",
    "middle_mcp_side", "middle_mcp_flex", "middle_pip_flex", "middle_dip_flex",
    "ring_mcp_side", "ring_mcp_flex", "ring_pip_flex", "ring_dip_flex",
    "thumb_cmc_side", "thumb_cmc_flex", "thumb_mcp_flex", "thumb_ip_flex",
)  # fmt: skip

_LINES = {
    "ids": re.compile(r"Motor IDs/model numbers: (\{[^}]*\})"),
    "pos": re.compile(r"Positions: (\[[^\]]*\])"),
    "temp": re.compile(r"Temperatures: (\[[^\]]*\])"),
    "volt": re.compile(r"Input voltages: (\[[^\]]*\])"),
    "hw_err": re.compile(r"Hardware errors: (\[[^\]]*\])"),
    "missing": re.compile(r"Missing or unresponsive DYNAMIXEL IDs: (\[[^\]]*\])"),
}


def parse_leap_check(text: str) -> dict | None:
    found = {}
    for line in text.splitlines():
        if line.startswith("$ "):  # the command header may echo the very same words
            continue
        for key, pattern in _LINES.items():
            match = pattern.search(line)
            if match is None:
                continue
            try:
                found[key] = ast.literal_eval(match.group(1))
            except (ValueError, SyntaxError):
                continue
    if not found:
        return None
    ids = list(found["ids"]) if "ids" in found else list(range(len(LEAP_JOINTS)))
    missing = [int(i) for i in found.get("missing", [])]
    motors = []
    for index, motor_id in enumerate(ids):
        row = {"id": motor_id,
               "joint": LEAP_JOINTS[index] if index < len(LEAP_JOINTS) else "",
               "responded": False if motor_id in missing else (True if "ids" in found else None)}
        for key in ("pos", "temp", "volt", "hw_err"):
            values = found.get(key)
            row[key] = values[index] if values is not None and index < len(values) else None
        motors.append(row)
    ok = not missing and "ids" in found and not any(found.get("hw_err", []))
    return {"ok": ok, "missing": missing, "motors": motors}


def problem_text(table: dict) -> str | None:
    """One line naming each motor that did not answer or has a hardware error bit set."""
    bad = [f"ID {m['id']} 응답 없음" if m["responded"] is False
           else f"ID {m['id']} 오류 비트 {m['hw_err']}"
           for m in table["motors"] if m["responded"] is False or m["hw_err"]]
    return "모터 확인: " + ", ".join(bad) if bad else None
