"""Space-bar toggle between an open and a closed hand."""

from __future__ import annotations

import os
import select
import sys
from collections.abc import Callable

from leap_teleop.sources.base import Source
from leap_teleop.types import Reading


class TerminalKeyReader:
    """Non-blocking single-key reads from an interactive terminal (cbreak mode)."""

    def __init__(self, stream=None) -> None:
        import termios
        import tty

        self._stream = stream if stream is not None else sys.stdin
        if not self._stream.isatty():
            raise RuntimeError(
                "The keyboard source needs an interactive terminal (stdin is not a TTY)"
            )
        self._termios = termios
        self._fd = self._stream.fileno()
        self._saved = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)

    def __call__(self) -> str | None:
        if select.select([self._fd], [], [], 0)[0]:
            return os.read(self._fd, 1).decode(errors="ignore")
        return None

    def close(self) -> None:
        self._termios.tcsetattr(self._fd, self._termios.TCSADRAIN, self._saved)


class KeyboardSource(Source):
    def __init__(self, read_key: Callable[[], str | None] | None = None) -> None:
        self._read_key = read_key if read_key is not None else TerminalKeyReader()
        self._grasp = 0.0
        self._stop = False

    def poll(self, now: float) -> Reading:
        while (key := self._read_key()) is not None:
            if key == " ":
                self._grasp = 1.0 - self._grasp
            elif key in ("q", "Q"):
                self._stop = True
        return Reading(timestamp=now, grasp=self._grasp)

    @property
    def stop_requested(self) -> bool:
        return self._stop

    def close(self) -> None:
        closer = getattr(self._read_key, "close", None)
        if closer is not None:
            closer()
