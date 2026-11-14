from __future__ import annotations

import re

from control_hub.config import EventRule, Hint
from control_hub.logscan import LogScanner

RULE = EventRule(re.compile(r"IDs: \[?(?P<motors>[\d, ]+)"), "bad", "모터 응답 없음: {motors}")


def write(tmp_path, text):
    path = tmp_path / "run.log"
    path.write_text(text, encoding="utf-8")
    return path


def append(path, text):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def test_rule_extracts_motors(tmp_path):
    log = write(tmp_path, "$ cmd\nok\nMissing or unresponsive DYNAMIXEL IDs: [3, 7]\n")
    scanner = LogScanner(log, None, [], [RULE])
    scanner.poll()
    [event] = scanner.drain()
    assert event.motors == (3, 7) and event.text == "모터 응답 없음: 3, 7"
    assert event.level == "bad" and event.count == 1
    assert scanner.drain() == []


def test_header_line_is_not_event(tmp_path):
    scanner = LogScanner(write(tmp_path, "$ run --ids IDs: [1]\n"), None, [], [RULE])
    scanner.poll()
    assert scanner.drain() == []


def test_generic_error_becomes_warn_event(tmp_path):
    scanner = LogScanner(write(tmp_path, "$ cmd\nsomething failed\n"), None, [], [RULE])
    scanner.poll()
    [event] = scanner.drain()
    assert event.level == "warn" and event.text == "something failed"


def test_hint_line_becomes_bad_event_with_hint(tmp_path):
    hint = Hint(re.compile("busy"), "다른 프로그램이 잡고 있다")
    scanner = LogScanner(write(tmp_path, "$ cmd\nport busy\n"), None, [hint], [])
    scanner.poll()
    [event] = scanner.drain()
    assert event.level == "bad" and event.hint == "다른 프로그램이 잡고 있다"


def test_ignored_hint_is_not_event(tmp_path):
    hint = Hint(re.compile("BULK_READ_FAIL"), "", ignore=True)
    scanner = LogScanner(write(tmp_path, "$ cmd\nBULK_READ_FAIL error\n"), None, [hint], [RULE])
    scanner.poll()
    assert scanner.drain() == []


def test_event_rate_limit(tmp_path):
    clock = [100.0]
    line = "Missing or unresponsive DYNAMIXEL IDs: [7]\n"
    log = write(tmp_path, "$ cmd\n" + line * 500)
    scanner = LogScanner(log, None, [], [RULE], now=lambda: clock[0])
    scanner.poll()
    assert [e.count for e in scanner.drain()] == [1]
    clock[0] = 101.1
    append(log, line)
    scanner.poll()
    assert [e.count for e in scanner.drain()] == [500]  # 499 held back + this one



def test_skip_existing_keeps_ready_but_no_events(tmp_path):
    log = write(tmp_path, "$ cmd\n[srv] ready\nIDs: [1]\nit failed\n")
    scanner = LogScanner(log, re.compile(r"\[srv\] ready"), [], [RULE])
    scanner.skip_existing()
    assert scanner.ready_seen and scanner.drain() == []
    assert [i["line"] for i in scanner.issues] == ["it failed"]  # the detail panel keeps them
    append(log, "IDs: [4]\n")
    scanner.poll()
    assert [e.motors for e in scanner.drain()] == [(4,)]


def test_timestamped_flood_is_one_event(tmp_path):
    lines = "".join(f"[ERROR] [1731650000.{i:06d}] [arm]: read failed\n" for i in range(300))
    scanner = LogScanner(write(tmp_path, "$ cmd\n" + lines), None, [], [RULE], now=lambda: 5.0)
    scanner.poll()
    [event] = scanner.drain()
    assert event.text.startswith("[ERROR] [1731650000.000000]")


def test_different_motors_are_not_merged_by_the_rate_limit(tmp_path):
    log = write(tmp_path, "$ cmd\nIDs: [3]\nIDs: [7]\n")
    scanner = LogScanner(log, None, [], [RULE], now=lambda: 5.0)
    scanner.poll()
    assert [e.motors for e in scanner.drain()] == [(3,), (7,)]
