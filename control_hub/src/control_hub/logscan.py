"""Read a process log as it grows: clean terminal noise, spot "ready", collect problems."""

from __future__ import annotations

import codecs
import re
from collections import deque
from pathlib import Path

from control_hub.config import Hint

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


class LogScanner:
    """Follows one log file. ``poll()`` is cheap and may be called every second."""

    def __init__(self, path: Path, ready: re.Pattern[str] | None, hints: list[Hint]) -> None:
        self.path = path
        self.ready = ready
        self.hints = hints
        self.ready_seen = False
        self.issues: deque[dict] = deque(maxlen=MAX_ISSUES)
        self.last_line = ""
        self._offset = 0
        self._partial = ""
        # The first line of every log is the command itself ("$ ssh ..."). Its words must not
        # count as output: a command that mentions "leader" is not a ready leader.
        self._header_seen = False

    def poll(self) -> None:
        while True:
            offset, text = read_chunk(self.path, self._offset)
            if offset == self._offset:
                break
            self._offset = offset
            lines = (self._partial + text).split("\n")
            self._partial = lines.pop()
            for line in lines:
                self._line(line.rstrip())
        if (self._header_seen and self.ready is not None and not self.ready_seen
                and self.ready.search(self._partial)):
            self.ready_seen = True  # a prompt without a newline can be the "ready" sign

    def _line(self, line: str) -> None:
        if not self._header_seen:
            self._header_seen = True
            return
        if not line.strip():
            return
        self.last_line = line
        if self.ready is not None and not self.ready_seen and self.ready.search(line):
            self.ready_seen = True
        hint_text = None
        for hint in self.hints:
            if hint.pattern.search(line):
                if hint.ignore:
                    return
                hint_text = hint.text
                break
        if hint_text is None and not GENERIC_ERROR.search(line):
            return
        if self.issues and self.issues[-1]["line"] == line:
            self.issues[-1]["count"] += 1
            return
        self.issues.append({"line": line[:400], "hint": hint_text, "count": 1})
