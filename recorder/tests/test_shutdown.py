"""The real program, ended from outside while it records. Runs `tactile_rec.cli` on the fake
rig in a subprocess, so these take a few seconds each."""

from __future__ import annotations

import json
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

RECORDER = Path(__file__).parents[1]
EXIT_WITHIN_S = 10.0


def launch(root, *args):
    return subprocess.Popen(
        [sys.executable, "-m", "tactile_rec.cli", "record", "--config", "config/rig.fake.yaml",
         "--root", str(root), *args],
        cwd=RECORDER, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def finish(process, number):
    """Send the signal; return (seconds until exit, everything the program printed)."""
    began = time.monotonic()
    process.send_signal(number)
    try:
        output, _ = process.communicate(timeout=EXIT_WITHIN_S)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate()
        pytest.fail(f"still running {EXIT_WITHIN_S} s after the signal:\n{output}")
    return time.monotonic() - began, output


def kept_episode(root):
    [folder] = root.rglob("ep_0001.tmp")
    return json.loads((folder / "episode.json").read_text())


def wait_until(predicate, timeout_s=15.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except OSError:
            pass
        time.sleep(0.1)
    raise AssertionError("timed out")


@pytest.mark.parametrize("name", ["SIGINT", "SIGTERM", "SIGHUP"])
def test_ending_the_program_while_recording_keeps_the_episode(tmp_path, name):
    process = launch(tmp_path, "--ui", "none", "--auto", "60")
    wait_until(lambda: any(tmp_path.rglob("recording.json")))
    time.sleep(1.0)
    _, output = finish(process, getattr(signal, name))
    assert process.returncode == 0, output
    assert "unsaved episode kept in" in output
    meta = kept_episode(tmp_path)
    assert meta["result"] is None and meta["duration_s"] >= 1.0
    assert not meta["flags"]["recovered"]  # stopped properly, not cut off


def test_the_web_ui_exits_although_a_camera_preview_is_open(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    process = launch(tmp_path, "--port", str(port))
    wait_until(lambda: urllib.request.urlopen(base + "/api/state", timeout=1).status == 200)
    time.sleep(2.0)  # every stream healthy
    request = urllib.request.Request(
        base + "/api/record/start", data=b"{}", method="POST",
        headers={"Content-Type": "application/json"},
    )
    assert json.loads(urllib.request.urlopen(request, timeout=5).read()) == {"episode": 1}
    preview = urllib.request.urlopen(base + "/api/stream/cam_wrist", timeout=5)
    assert preview.read(2000)  # frames are flowing: this connection never ends by itself
    time.sleep(1.0)
    seconds, output = finish(process, signal.SIGTERM)
    preview.close()
    assert process.returncode == 0, output
    assert seconds < 6.0  # ui.shutdown_timeout_s (2) plus stopping the episode and the streams
    assert kept_episode(tmp_path)["duration_s"] >= 1.0
