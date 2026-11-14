"""HandDriver adapter for the vendored LEAP Hand v1 controller."""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np

from leap_teleop.hand.leap_v1 import LeapHandHardwareController


FAILURE_LOG_INTERVAL_S = 1.0


class LeapHandDriver:
    def __init__(self, controller: LeapHandHardwareController,
                 log: Callable[[str], None] = print,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._controller = controller
        self._log = log
        self._clock = clock
        self._last_failure_log: float | None = None

    def start(self) -> None:
        try:
            self._controller.connect()
            self._controller.configure()
            self._controller.enable_torque()
        except BaseException:
            self._controller.close()
            raise

    def command(self, angles_degrees: np.ndarray) -> None:
        self._controller.command_degrees(angles_degrees)

    def last_sent_degrees(self):
        """Last command actually written (after LEAP bounds clip and slew limit)."""
        return self._controller.last_command_degrees

    def read_feedback(self):
        """Feedback for recording only; None when a read fails (control must not stop)."""
        try:
            return self._controller.read_feedback()
        except (OSError, RuntimeError) as error:
            now = self._clock()
            if (self._last_failure_log is None
                    or now - self._last_failure_log >= FAILURE_LOG_INTERVAL_S):
                self._last_failure_log = now
                self._log(f"[leap] feedback read failed: {error}")  # read by control_hub
            return None

    def close(self) -> None:
        failed_ids = self._controller.close()
        if failed_ids:
            raise RuntimeError(
                f"Torque-off was not acknowledged by motor IDs {tuple(failed_ids)}; "
                "cut the 5V supply."
            )
