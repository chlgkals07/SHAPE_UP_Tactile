from __future__ import annotations

from control_hub.leapcheck import LEAP_JOINTS, parse_leap_check, problem_text

IDS = list(range(16))
OK = f"""$ leap_check
Connected with torque OFF: /dev/ttyUSB0
Motor IDs/model numbers: {dict.fromkeys(IDS, 1060)}
Positions: {[-85.0 if i in (1, 5, 9) else 1.5 for i in IDS]} deg
Temperatures: {[30.0 + i for i in IDS]} C
Input voltages: {[5.1] * 16} V
Hardware errors: {[0] * 16}
Torque was never enabled. Add --torque-test only after inspection.
Torque OFF; serial port closed.
"""

MISSING = """$ leap_check
Traceback (most recent call last):
  File "check_hardware.py", line 88, in main
ConnectionError: Missing or unresponsive DYNAMIXEL IDs: [3, 7]
"""


def test_parse_ok_output():
    table = parse_leap_check(OK)
    assert table["ok"] and table["missing"] == []
    motors = table["motors"]
    assert len(motors) == 16 and all(m["responded"] for m in motors)
    assert motors[15] == {"id": 15, "joint": LEAP_JOINTS[15], "responded": True,
                          "pos": 1.5, "temp": 45.0, "volt": 5.1, "hw_err": 0}
    assert motors[1]["pos"] == -85.0


def test_parse_missing():
    table = parse_leap_check(MISSING)
    assert not table["ok"] and table["missing"] == [3, 7]
    assert table["motors"][3]["responded"] is False and table["motors"][7]["responded"] is False
    assert table["motors"][0]["responded"] is None and table["motors"][0]["temp"] is None


def test_hw_error_nonzero_marks_not_ok():
    table = parse_leap_check(OK.replace(f"Hardware errors: {[0] * 16}",
                                        f"Hardware errors: {[0] * 15 + [32]}"))
    assert not table["ok"] and table["motors"][15]["hw_err"] == 32


def test_parse_unknown_returns_none():
    assert parse_leap_check("$ leap_check\nbash: leap_check: command not found\n") is None


def test_command_header_echoing_the_same_text_is_ignored():
    header = "$ bash -c 'echo \"Positions: [9.9] deg\"; echo \"Temperatures: [1.0] C\"'\n"
    table = parse_leap_check(header + OK.split("\n", 1)[1])
    assert table["motors"][15]["temp"] == 45.0 and table["motors"][1]["pos"] == -85.0


def test_problem_text_names_each_bad_motor():
    table = {"motors": [{"id": 3, "responded": False, "hw_err": None},
                        {"id": 7, "responded": True, "hw_err": 32},
                        {"id": 8, "responded": True, "hw_err": 0}]}
    assert problem_text(table) == "모터 확인: ID 3 응답 없음, ID 7 오류 비트 32"
    assert problem_text({"motors": [{"id": 8, "responded": True, "hw_err": 0}]}) is None
