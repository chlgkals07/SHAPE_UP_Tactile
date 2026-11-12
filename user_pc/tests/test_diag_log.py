import numpy as np

from leap_teleop.diag_log import CsvLogger, Tee, header
from leap_teleop.hand.leap_v1 import LeapHandFeedback
from leap_teleop.tools import analyze_log
from leap_teleop.types import HUMAN_ANGLE_NAMES, HumanHand, Reading


class _Driver:
    def __init__(self):
        self.sent = np.zeros(16)

    def last_sent_degrees(self):
        return self.sent


def test_csv_logger_writes_rows_and_analyzer_finds_stall(tmp_path, capsys):
    path = tmp_path / "run.csv"
    driver = _Driver()
    clock = iter(np.arange(0, 10, 0.02))
    log = CsvLogger(path, driver, clock=lambda: next(clock))
    for k in range(40):
        cmd = np.zeros(16)
        cmd[2] = 60.0
        driver.sent = cmd.copy()
        pos = np.zeros(16)
        pos[2] = 30.0 if k >= 10 else 60.0  # stuck at 30 deg from tick 10
        cur = np.zeros(16)
        cur[2] = 300.0 if k >= 10 else 50.0
        fb = LeapHandFeedback(pos, np.zeros(16), cur)
        human = HumanHand(np.full(len(HUMAN_ANGLE_NAMES), float(k)))
        log.publish(cmd, fb, "live", Reading(timestamp=float(k), human=human))
    log.close()

    lines = path.read_text().splitlines()
    assert lines[0].split(",") == header()
    assert len(lines) == 41

    analyze_log.main([str(path), "--joints", "2"])
    out = capsys.readouterr().out
    assert "stall: 1 episodes" in out
    assert "lag" not in out.split("ID 2")[1].split("stall")[0]


def test_tee_fans_out():
    calls = []

    class Sink:
        def publish(self, *a):
            calls.append(a)

        def close(self):
            calls.append("closed")

    tee = Tee(Sink(), None, Sink())
    tee.publish(1, 2, 3, 4)
    tee.close()
    assert calls == [(1, 2, 3, 4), (1, 2, 3, 4), "closed", "closed"]
