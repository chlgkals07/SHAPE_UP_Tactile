from __future__ import annotations

import pytest

from policy_runner import config as runner_config
from policy_runner.manifest import Manifest

from conftest import manifest_dict, passive_hub, rig_dict, runner_dict


def problems_of(path, **kwargs) -> list[str]:
    with pytest.raises(runner_config.ConfigError) as caught:
        runner_config.load(path, **kwargs)
    return caught.value.problems


def test_loads_a_valid_config(files):
    cfg = runner_config.load(files())
    assert cfg.exec_horizon == 10
    assert cfg.dt_ns == round(1e9 / 30)
    assert cfg.required_streams == ("arm_state", "hand", "cam_wrist", "cam_ext")
    assert cfg.prompt == "Pick up the cup"


def test_rejects_respread_for_a_required_stream(files, tmp_path):
    rig = rig_dict(tmp_path, time={"hand": "respread"})
    problems = problems_of(files(rig=rig))
    assert any("hand" in p and "respread" in p for p in problems)


def test_rejects_src_time_on_a_remote_clock(files, tmp_path):
    rig = rig_dict(tmp_path, time={"hand": "src", "arm_state": "src"})
    problems = problems_of(files(rig=rig))
    assert any("arm_state" in p and "src" in p for p in problems)


@pytest.mark.parametrize("k", [0, 51])
def test_rejects_exec_horizon_outside_one_to_h(files, k):
    problems = problems_of(files(runner=runner_dict(execution={"exec_horizon": k})))
    assert any("exec_horizon" in p for p in problems)


def test_every_required_stream_needs_an_age_budget(files):
    runner = runner_dict(observation={"max_age_ms": {"arm_state": 50, "hand": 100}})
    problems = problems_of(files(runner=runner))
    assert any("cam_wrist" in p for p in problems)
    assert any("cam_ext" in p for p in problems)


def test_hand_mode_needs_explicit_permission(files):
    path = files(runner=runner_dict(execution={"mode": "hand"}))
    assert any("hand" in p for p in problems_of(path))
    assert runner_config.load(path, allow_hand=True).mode == "hand"


def test_manifest_mismatch_lists_every_field(tmp_path):
    hub = passive_hub(tmp_path)
    wrong = Manifest(**{**manifest_dict(), "fps": 15, "mount": "stock", "hand_action": "cmd",
                        "joint_names": ["a"] * 22, "cameras": ["cam_ext"]})
    text = " ".join(wrong.mismatches(hub))
    for word in ("fps", "mount", "hand_action", "joint_names", "cameras"):
        assert word in text


def test_matching_manifest_has_no_mismatch(tmp_path):
    assert Manifest(**manifest_dict()).mismatches(passive_hub(tmp_path)) == []


def test_config_mismatch_with_manifest_is_a_config_error(files, tmp_path):
    problems = problems_of(files(manifest=manifest_dict(fps=15)))
    assert any("fps" in p for p in problems)
