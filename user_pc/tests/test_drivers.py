import numpy as np
import pytest

from leap_teleop.hand.dry_run import LogDriver
from leap_teleop.hand.leap_driver import LeapHandDriver


class FakeController:
    def __init__(self, fail_on=None, failed_ids=()):
        self.calls = []
        self.fail_on = fail_on
        self.failed_ids = failed_ids

    def connect(self):
        self._step("connect")

    def configure(self):
        self._step("configure")

    def enable_torque(self):
        self._step("enable_torque")

    def command_degrees(self, angles):
        self.calls.append(("command", np.asarray(angles).copy()))

    def close(self):
        self.calls.append(("close",))
        return self.failed_ids

    def _step(self, name):
        self.calls.append((name,))
        if self.fail_on == name:
            raise OSError(name)


def test_start_connects_configures_then_enables_torque_in_order():
    controller = FakeController()
    LeapHandDriver(controller).start()
    assert [call[0] for call in controller.calls] == ["connect", "configure", "enable_torque"]


def test_start_failure_closes_controller_and_reraises():
    controller = FakeController(fail_on="configure")
    with pytest.raises(OSError):
        LeapHandDriver(controller).start()
    assert controller.calls[-1] == ("close",)


def test_command_forwards_angles():
    controller = FakeController()
    angles = np.arange(16, dtype=float)
    LeapHandDriver(controller).command(angles)
    name, forwarded = controller.calls[-1]
    assert name == "command"
    np.testing.assert_array_equal(forwarded, angles)


def test_close_reports_motors_that_did_not_acknowledge_torque_off():
    driver = LeapHandDriver(FakeController(failed_ids=(3, 7)))
    with pytest.raises(RuntimeError, match=r"\(3, 7\)"):
        driver.close()


def test_close_is_quiet_when_all_motors_acknowledge():
    LeapHandDriver(FakeController()).close()


def test_log_driver_logs_first_and_every_nth_command():
    lines = []
    driver = LogDriver(every=3, out=lines.append)
    driver.start()
    for _ in range(7):
        driver.command(np.zeros(16))
    driver.close()
    command_lines = [line for line in lines if "cmd" in line]
    assert len(command_lines) == 3  # commands 1, 4 and 7
    assert any("start" in line for line in lines)
    assert any("close" in line for line in lines)
