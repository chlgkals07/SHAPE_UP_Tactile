"""HandDriver adapter for the vendored LEAP Hand v1 controller."""

from __future__ import annotations

import numpy as np

from leap_teleop.hand.leap_v1 import LeapHandHardwareController


class LeapHandDriver:
    def __init__(self, controller: LeapHandHardwareController) -> None:
        self._controller = controller

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
        except (OSError, RuntimeError):
            return None

    def close(self) -> None:
        failed_ids = self._controller.close()
        if failed_ids:
            raise RuntimeError(
                f"Torque-off was not acknowledged by motor IDs {tuple(failed_ids)}; "
                "cut the 5V supply."
            )
