from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from control_hub.config import ConfigError, load_config

EXAMPLES = Path(__file__).parent.parent / "config"


def write(tmp_path: Path, checks: dict) -> Path:
    path = tmp_path / "hub.yaml"
    path.write_text(yaml.safe_dump({"processes": {"a": {"cmd": "x"}}, "checks": checks}),
                    encoding="utf-8")
    return path


def test_link_check_without_page_is_the_recorder_page(tmp_path):
    cfg = load_config(write(tmp_path, {"ui": {"http": "http://127.0.0.1:8800/", "link": "열기"}}))
    assert cfg.checks["ui"].page == "rec"


def test_policy_page_check(tmp_path):
    cfg = load_config(write(tmp_path, {
        "rec": {"http": "http://127.0.0.1:8800/", "link": "녹화기 열기"},
        "pol": {"http": "http://127.0.0.1:8810/", "link": "정책 열기", "page": "policy"},
    }))
    assert cfg.checks["rec"].page == "rec"
    assert cfg.checks["pol"].page == "policy"


def test_unknown_page_is_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"x": {"http": "http://127.0.0.1:1/", "link": "x",
                                           "page": "nope"}}))


@pytest.mark.parametrize("name", ["hub.example.yaml", "hub.fake.yaml"])
def test_examples_have_one_page_per_link_check(name):
    cfg = load_config(EXAMPLES / name)
    pages = sorted(c.page for c in cfg.checks.values() if c.link)
    assert pages == ["policy", "rec"]
