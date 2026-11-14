"""Read a process log as it grows: clean terminal noise, spot "ready", collect problems."""

from __future__ import annotations

import codecs
import re
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from control_hub.config import EventRule, Hint

_ANSI = re.compile(
    r"\x1b\[[0-9;?<=>]*[ -/]*[@-~]"        # CSI: colours, cursor moves
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC: window titles
    r"|\x1b[@-Z\\^_=>()][0-9A-B]?"         # other two-byte escapes
)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
GENERIC_ERROR = re.compile(
    r"(?i)\b(error|fatal|traceback|exception|failed|failure|no such file|not found|refused"
    r"|denied|timed out|unreachable|cannot|abort(ed)?|segmentation fault|killed)\b"
)
MAX_ISSUES = 20
MAX_CHUNK = 256 * 1024
EVENT_GAP_S = 1.0  # the same event text is reported at most once a second
MOTOR_NUMBER = re.compile(r"\d+")


def clean(text: str) -> str:
    """Terminal bytes -> plain lines."""
    text = _ANSI.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL.sub("", text)


def read_chunk(path: Path, offset: int) -> tuple[int, str]:
    """Text from byte ``offset`` on, and the offset to ask for next. Never splits a character."""
    try:
        size = path.stat().st_size
    except OSError:
        return 0, ""
    if offset > size or offset < 0:
        offset = 0
    if size - offset > MAX_CHUNK:
        offset = size - MAX_CHUNK
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(MAX_CHUNK)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    text = decoder.decode(data)
    pending = decoder.getstate()[0]
    return offset + len(data) - len(pending), clean(text)


@dataclass(frozen=True)
class LogEvent:
    t: float
    level: str
    text: str
    line: str
    motors: tuple[int, ...]
    offset: int  # where the chunk holding this line starts: open the log here to see it
    hint: str | None
    generic: bool  # caught by the generic error words or a hint, not by a device rule
    count: int = 1  # lines this event stands for (repeats held back by the rate limit)


class LogScanner:
    """Follows one log file. ``poll()`` is cheap and may be called every second."""

    def __init__(self, path: Path, ready: re.Pattern[str] | None, hints: list[Hint],
                 events: Sequence[EventRule] = (), now: Callable[[], float] = time.time) -> None:
        self.path = path
        self.ready = ready
        self.hints = hints
        self.rules = events
        self.ready_seen = False
        self.issues: deque[dict] = deque(maxlen=MAX_ISSUES)
        self.last_line = ""
        self._now = now
        self._offset = 0
        self._chunk_start = 0
        self._partial = ""
        self._quiet = False  # reading old lines: update ready, report nothing
        self._events: list[LogEvent] = []
        self._last_sent: dict[str, float] = {}
        self._held: dict[str, int] = {}
        # The first line of every log is the command itself ("$ ssh ..."). Its words must not
        # count as output: a command that mentions "leader" is not a ready leader.
        self._header_seen = False

    def poll(self) -> None:
        while True:
            start = self._offset
            offset, text = read_chunk(self.path, self._offset)
            if offset == self._offset:
                break
            self._chunk_start = start
            self._offset = offset
            lines = (self._partial + text).split("\n")
            self._partial = lines.pop()
            for line in lines:
                self._line(line.rstrip())
        if (self._header_seen and self.ready is not None and not self.ready_seen
                and self.ready.search(self._partial)):
            self.ready_seen = True  # a prompt without a newline can be the "ready" sign

    def skip_existing(self) -> None:
        """Read what is already in the file without reporting it (hub restart, reload)."""
        self._quiet = True
        try:
            self.poll()
        finally:
            self._quiet = False

    def drain(self) -> list[LogEvent]:
        events, self._events = self._events, []
        return events

    def _line(self, line: str) -> None:
        if not self._header_seen:
            self._header_seen = True
            return
        if not line.strip():
            return
        self.last_line = line
        if self.ready is not None and not self.ready_seen and self.ready.search(line):
            self.ready_seen = True
        if self._quiet:
            return
        hint_text = None
        for hint in self.hints:
            if hint.pattern.search(line):
                if hint.ignore:
                    return
                hint_text = hint.text
                break
        rule_hit = self._rule_event(line, hint_text)
        if hint_text is None and not GENERIC_ERROR.search(line):
            return
        if not rule_hit:
            self._emit("bad" if hint_text else "warn", line[:200], line, (), hint_text, True)
        if self.issues and self.issues[-1]["line"] == line:
            self.issues[-1]["count"] += 1
            return
        self.issues.append({"line": line[:400], "hint": hint_text, "count": 1})

    def _rule_event(self, line: str, hint_text: str | None) -> bool:
        for rule in self.rules:
            match = rule.pattern.search(line)
            if match is None:
                continue
            groups = {k: (v or "").strip() for k, v in match.groupdict().items()}
            motors = tuple(int(n) for n in MOTOR_NUMBER.findall(groups.get("motors", "")))
            try:
                text = rule.text.format(**groups)
            except (KeyError, IndexError, ValueError):
                text = rule.text
            self._emit(rule.level, text, line, motors, hint_text, False)
            return True
        return False

    def _emit(self, level: str, text: str, line: str, motors: tuple[int, ...],
              hint: str | None, generic: bool) -> None:
        now = self._now()
        if now - self._last_sent.get(text, -EVENT_GAP_S) < EVENT_GAP_S:
            self._held[text] = self._held.get(text, 0) + 1
            return
        if len(self._last_sent) > 1000:  # many different lines: forget the old ones
            self._last_sent = {k: t for k, t in self._last_sent.items() if now - t < EVENT_GAP_S}
        self._last_sent[text] = now
        count = 1 + self._held.pop(text, 0)
        self._events.append(LogEvent(now, level, text, line[:400], motors, self._chunk_start,
                                     hint, generic, count))
