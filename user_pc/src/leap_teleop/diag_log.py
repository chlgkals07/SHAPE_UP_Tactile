"""Per-tick CSV log for debugging (e.g. a finger that stops mid-way).

Same interface as ``RosPublisher`` (``publish`` / ``close``) so the control loop treats it
as a record-only sink. Columns, all degrees / mA:

    t, mode,
    glove_<HUMAN_ANGLE_NAMES>   operator glove angles (blank when the tick had no new sample)
    cmd_<id>                    retargeted target after the stale guard (before LEAP clip / slew)
    sent_<id>                   what was actually written to the motor (after clip + slew limit)
    pos_<id>, cur_<id>          present position and current read back from the motor
"""

from __future__ import annotations

import csv
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from leap_teleop.types import HAND_DOF, HUMAN_ANGLE_NAMES, Reading


def header() -> list[str]:
    ids = range(HAND_DOF)
    return (
        ["t", "mode"]
        + [f"glove_{n}" for n in HUMAN_ANGLE_NAMES]
        + [f"cmd_{i}" for i in ids]
        + [f"sent_{i}" for i in ids]
        + [f"pos_{i}" for i in ids]
        + [f"cur_{i}" for i in ids]
    )


def _fmt(values, n: int) -> list[str]:
    if values is None:
        return [""] * n
    return [f"{float(v):.2f}" for v in np.asarray(values, dtype=float)]


class CsvLogger:
    def __init__(
        self,
        path: str | Path,
        driver=None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(header())
        self._driver = driver
        self._clock = clock
        self._t0 = clock()
        self._last_human_time = None

    def publish(self, command_degrees, feedback, mode: str, reading: Reading | None) -> None:
        human = reading.human if reading is not None else None
        glove = None
        if human is not None and reading.timestamp != self._last_human_time:
            self._last_human_time = reading.timestamp
            glove = human.angles
        sent_fn = getattr(self._driver, "last_sent_degrees", None)
        sent = sent_fn() if sent_fn is not None else None
        row = (
            [f"{self._clock() - self._t0:.4f}", mode]
            + _fmt(glove, len(HUMAN_ANGLE_NAMES))
            + _fmt(command_degrees, HAND_DOF)
            + _fmt(sent, HAND_DOF)
            + _fmt(feedback.positions_degrees if feedback is not None else None, HAND_DOF)
            + _fmt(feedback.currents_milliamps if feedback is not None else None, HAND_DOF)
        )
        self._writer.writerow(row)

    def close(self) -> None:
        self._file.close()


class Tee:
    """Fan one publish() out to several record-only sinks."""

    def __init__(self, *sinks) -> None:
        self._sinks = [s for s in sinks if s is not None]

    def publish(self, *args) -> None:
        for sink in self._sinks:
            sink.publish(*args)

    def close(self) -> None:
        for sink in self._sinks:
            sink.close()
