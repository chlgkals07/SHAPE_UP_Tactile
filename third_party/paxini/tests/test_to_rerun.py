"""Regressions for mixed sensor geometry and the browser viewer path."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("rerun")
from paxini_sdk.tools import to_rerun as viz


def mixed_board(monkeypatch):
    board = MagicMock()
    board.read_version.return_value = "ADAPTER_FW02.26"
    board.read_active_modules.return_value = [5, 6]
    board.read_distribution_point_count.side_effect = lambda module: {5: 25, 6: 52}[module]
    frame = SimpleNamespace(
        resultant_forces_newtons={"Index-Middle": (0, 0, 1), "Index-Tip": (0, 0, 2)},
        distributed_forces={"Index-Middle": [(0, 0, 1)] * 25,
                            "Index-Tip": [(0, 0, 2)] * 52},
    )
    board.stream_auto_push.return_value = iter([frame])
    board.__enter__.return_value = board
    monkeypatch.setattr(viz, "HighSpeedHandBoard", lambda *a, **kw: board)
    for name in ("log", "set_time", "send_blueprint"):
        monkeypatch.setattr(viz.rr, name, MagicMock())
    return board


def test_mixed_sensors_keep_all_points_and_correct_coordinates(monkeypatch):
    board = mixed_board(monkeypatch)
    distributed = MagicMock()
    monkeypatch.setattr(viz, "log_distributed", distributed)
    viz.run_live("unused", 921600, 1, False, None)

    calls = {call.args[0]: call.args[1:] for call in distributed.call_args_list}
    for name, code, count in (("Index-Middle", "PXSR-STDIP03B", 25),
                              ("Index-Tip", "PXSR-STDDP03G", 52)):
        positions, forces = calls[name]
        assert len(positions) == len(forces) == count
        assert positions == viz.load_sensor_points(viz.resolve_sensor_variant(
            sensor_part_override=code))
    anatomy = {call.args[0] for call in viz.rr.log.call_args_list
               if call.args[0].endswith("/anatomy")}
    assert anatomy == {"sensor/index_middle/anatomy", "sensor/index_tip/anatomy"}
    board.__exit__.assert_called_once()


def test_mixed_sensor_override_rejects_wrong_geometry(monkeypatch):
    board = mixed_board(monkeypatch)
    with pytest.raises(ValueError, match="Index-Tip: 52 points reported"):
        viz.run_live("unused", 921600, 1, False, "PXSR-STDIP03B")
    board.stream_auto_push.assert_not_called()
    board.__exit__.assert_called_once()


def test_web_mode_serves_without_spawning_and_stops_cleanly(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["paxini-rerun", "--port", "unused", "--web-viewer"])
    mocks = {}
    for name in ("init", "spawn", "serve_grpc", "serve_web_viewer", "disconnect"):
        mocks[name] = MagicMock()
        monkeypatch.setattr(viz.rr, name, mocks[name])
    mocks["serve_grpc"].return_value = "rerun+http://127.0.0.1:9876/proxy"
    monkeypatch.setattr(viz, "run_live", MagicMock(side_effect=KeyboardInterrupt))

    assert viz.main() == 0
    mocks["init"].assert_called_once_with("paxini_tactile", spawn=False)
    mocks["spawn"].assert_not_called()
    mocks["serve_web_viewer"].assert_called_once_with(web_port=9090, open_browser=False)
    mocks["disconnect"].assert_called_once()
    assert "http://localhost:9090/?url=rerun%2Bhttp" in capsys.readouterr().out


def test_web_replay_keeps_server_alive_until_interrupted(monkeypatch, tmp_path):
    recording = tmp_path / "example.csv"
    recording.touch()
    monkeypatch.setattr("sys.argv", ["paxini-rerun", "--csv", str(recording), "--web-viewer"])
    for name in ("init", "serve_grpc", "serve_web_viewer", "disconnect"):
        monkeypatch.setattr(viz.rr, name, MagicMock())
    viz.rr.serve_grpc.return_value = "rerun+http://127.0.0.1:9876/proxy"
    replay = MagicMock()
    monkeypatch.setattr(viz, "run_csv_replay", replay)
    wait = MagicMock(side_effect=KeyboardInterrupt)
    monkeypatch.setattr(viz.time, "sleep", wait)
    assert viz.main() == 0
    replay.assert_called_once_with(recording, "PXSR-STDDP03G")
    wait.assert_called_once()
    viz.rr.disconnect.assert_called_once()
