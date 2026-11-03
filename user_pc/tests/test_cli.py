import io
from pathlib import Path

import numpy as np
import pytest

from leap_teleop import cli
from leap_teleop.config import load_postures
from leap_teleop.sources.base import Source

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
BASE = [
    "--postures", str(CONFIG_DIR / "postures.yaml"),
    "--leader-gripper", str(CONFIG_DIR / "leader_gripper.yaml"),
]


class StoppedSource(Source):
    @property
    def stop_requested(self):
        return True

    def poll(self, now):
        return None


def test_parser_defaults():
    args = cli.build_parser().parse_args([])
    assert args.source == "keyboard"
    assert args.port == "/dev/ttyUSB0"
    assert args.rate == 50.0
    assert args.current_limit == 300
    assert args.dry_run is False


@pytest.mark.parametrize("rate", ["5", "500"])
def test_rate_outside_watchdog_safe_range_is_rejected(rate, capsys):
    code = cli.main(BASE + ["--dry-run", "--rate", rate])
    assert code == 2
    assert "rate" in capsys.readouterr().err


def test_hardware_mode_refuses_to_run_without_motor_calibration(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "build_source", lambda args: pytest.fail("touched the terminal"))
    missing = tmp_path / "nope.yaml"
    code = cli.main(BASE + ["--motor-calibration-file", str(missing)])
    assert code == 2
    err = capsys.readouterr().err
    assert "calibrate_motors" in err


def test_keyboard_source_without_a_terminal_is_a_clean_error(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO())
    code = cli.main(BASE + ["--dry-run", "--source", "keyboard"])
    assert code == 2
    assert "TTY" in capsys.readouterr().err


def test_dry_run_starts_and_closes_the_log_driver(monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_source", lambda args: StoppedSource())
    code = cli.main(BASE + ["--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "[dry-run] start" in out
    assert "[dry-run] close" in out


def test_hardware_mode_refuses_the_nominal_example_calibration(capsys, monkeypatch):
    monkeypatch.setattr(cli, "build_source", lambda args: pytest.fail("touched the terminal"))
    example = CONFIG_DIR / "hardware_motors.example.yaml"
    code = cli.main(BASE + ["--motor-calibration-file", str(example)])
    assert code == 2
    assert "calibrate_motors" in capsys.readouterr().err


def test_safe_pose_defaults_to_open():
    assert cli.build_parser().parse_args([]).safe_pose == "open"


def test_safe_pose_fist_closes_the_hand_while_waiting(monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_source", lambda args: StoppedSource())
    commands = []
    monkeypatch.setattr(cli, "run_teleop", lambda source, retarget, guard, driver, **kw: commands.append(guard.resolve(0.0, None, None)))
    code = cli.main(BASE + ["--dry-run", "--safe-pose", "fist"])
    assert code == 0
    _, fist_pose = load_postures(CONFIG_DIR / "postures.yaml")
    np.testing.assert_array_equal(commands[0], fist_pose)


MANUS = [
    "--source", "manus",
    "--manus-config", str(CONFIG_DIR / "manus_leap.yaml"),
    "--manus-calibration", str(CONFIG_DIR / "manus_calibration.example.yaml"),
]


def test_manus_parser_defaults():
    args = cli.build_parser().parse_args(["--source", "manus"])
    assert args.thumb == "ik"
    assert args.glove_side == "Right"


def test_manus_dry_run_uses_the_manus_retargeter(monkeypatch):
    from leap_teleop.retarget.manus_leap import ManusLeapRetargeter

    monkeypatch.setattr(cli, "build_source", lambda args: StoppedSource())
    used = []
    monkeypatch.setattr(cli, "run_teleop", lambda source, retarget, guard, driver, **kw: used.append(retarget))
    assert cli.main(BASE + MANUS + ["--dry-run", "--thumb", "affine"]) == 0
    assert isinstance(used[0], ManusLeapRetargeter)


def test_hardware_mode_refuses_the_example_glove_calibration(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "build_source", lambda args: pytest.fail("touched ROS"))
    monkeypatch.setattr(cli, "build_driver", lambda args: pytest.fail("touched the hand"))
    motors = tmp_path / "hardware_motors.yaml"  # a "measured" file, so the motor check passes
    motors.write_text((CONFIG_DIR / "hardware_motors.example.yaml").read_text())
    code = cli.main(BASE + MANUS + ["--motor-calibration-file", str(motors)])
    assert code == 2
    assert "calibrate_manus" in capsys.readouterr().err


def test_manus_requires_a_glove_calibration(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "build_source", lambda args: pytest.fail("touched ROS"))
    args = BASE + MANUS[:-1] + [str(tmp_path / "missing.yaml"), "--dry-run"]
    assert cli.main(args) == 2
    assert "calibrate_manus" in capsys.readouterr().err


def test_missing_ros_package_fails_cleanly_before_the_hand_is_opened(monkeypatch, capsys):
    def no_manus_msgs(args):
        raise ModuleNotFoundError("No module named 'manus_ros2_msgs'")

    monkeypatch.setattr(cli, "build_source", no_manus_msgs)
    monkeypatch.setattr(cli, "build_driver", lambda args: pytest.fail("opened the hand first"))
    assert cli.main(BASE + MANUS + ["--dry-run"]) == 2
    assert "manus_ros2_msgs" in capsys.readouterr().err
