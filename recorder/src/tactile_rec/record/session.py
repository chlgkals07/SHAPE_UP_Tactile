"""Recording control: idle -> recording -> review -> idle.

This object is the whole recording logic. The terminal UI and the web UI only call its methods
and show `status()`, so both behave the same.

On disk:
  <data_root>/<task>/<YYYY-MM-DD_HHMM>_<operator>/session.json
                                                 /ep_0001/...
An episode is written to `ep_0001.tmp/` and renamed to `ep_0001/` when it is saved, so a folder
without `.tmp` is always complete. Only an explicit discard deletes the temporary folder: an
episode that was not saved (the program was closed, a write failed, the PC lost power) stays
there and can be kept later (see record/recover.py).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tactile_rec import __version__
from tactile_rec.config import ConfigError, SessionConfig, check_label
from tactile_rec.hub import Hub
from tactile_rec.record.writer import EpisodeWriter
from tactile_rec.streams.specs import mode_code
from tactile_rec.types import STATUS_OK, STATUS_SLOW

IDLE, RECORDING, REVIEW = "idle", "recording", "review"
FORMAT_VERSION = 1
EPISODE_PREFIX = "ep_"
TMP_SUFFIX = ".tmp"
EPISODE_FILE = "episode.json"
PROGRESS_FILE = "recording.json"  # what is known while recording; replaced by episode.json
EVENTS_FILE = "events.jsonl"
LIVE_MODE = mode_code("live")


class RecorderError(RuntimeError):
    """A command that cannot run now. `problems` lists why, in words for the operator."""

    def __init__(self, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.problems = problems or [message]


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent,
            capture_output=True, text=True, timeout=2, check=False,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def write_json(path: Path, data: Any) -> None:
    """Written under a temporary name and renamed, so the file is never half-written."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def list_episodes(session_dir: Path) -> list[Path]:
    """Saved episode folders of a session, in order."""
    if not session_dir.is_dir():
        return []
    return sorted(
        p for p in session_dir.iterdir()
        if p.is_dir() and p.name.startswith(EPISODE_PREFIX) and not p.name.endswith(TMP_SUFFIX)
    )


class Recorder:
    def __init__(self, hub: Hub, session: SessionConfig | None = None):
        self.hub = hub
        self.config = hub.config
        self.clock = hub.clock
        self.session = session or self.config.session
        self.time_limit_s = float(self.config.record.time_limit_s)
        self.state = IDLE
        self._lock = threading.RLock()
        self._listeners: list[Callable[[str, dict[str, Any]], None]] = []
        self._session_dir: Path | None = None
        self._writer: EpisodeWriter | None = None
        self._unsubscribe: list[Callable[[], None]] = []
        self._tmp_dir: Path | None = None
        self._episode = 0
        self._start: dict[str, int] = {}
        self._end_ns = 0
        self._forced = False
        self._disk_guard = False  # stop when the disk runs low (off if it already was at start)
        self._disk_low = False
        self._dropouts: dict[str, int] = {}  # stream -> number of dropouts in this episode
        self._down: set[str] = set()
        self._summary: dict[str, Any] = {}
        self._counts = {"success": 0, "failure": 0}
        self._last_saved: Path | None = None

    # ---- observers --------------------------------------------------------------------------

    def add_listener(self, fn: Callable[[str, dict[str, Any]], None]) -> None:
        """fn(kind, detail) on: start, stop, saved, discarded, failed, dropout, recovered,
        disk_low, mark."""
        self._listeners.append(fn)

    def _notify(self, kind: str, **detail: Any) -> None:
        for fn in self._listeners:
            try:
                fn(kind, detail)
            except Exception:  # noqa: BLE001 - a UI problem must not break recording
                pass

    # ---- session ----------------------------------------------------------------------------

    def set_session(self, task: str, text: str, operator: str) -> None:
        """Change task / operator. Only when idle; starts a new session folder."""
        with self._lock:
            if self.state != IDLE:
                raise RecorderError("the session can only be changed while idle")
            for value, what in ((task, "task"), (operator, "operator")):
                try:
                    check_label(value, what)
                except ConfigError as error:
                    raise RecorderError(str(error)) from error
            self.session = SessionConfig(task=task, text=text, operator=operator)
            self._session_dir = None
            self._counts = {"success": 0, "failure": 0}

    def set_time_limit(self, seconds: float) -> None:
        if seconds < 0:
            raise RecorderError("time limit must be 0 (off) or positive")
        self.time_limit_s = float(seconds)

    @property
    def task_dir(self) -> Path:
        return self.config.data_root / self.session.task

    def _ensure_session_dir(self) -> Path:
        if self._session_dir is None:
            stamp = time.strftime("%Y-%m-%d_%H%M", time.localtime(self.clock.wall_ns() / 1e9))
            directory = self.task_dir / f"{stamp}_{self.session.operator}"
            directory.mkdir(parents=True, exist_ok=True)
            write_json(directory / "session.json", {
                "format": FORMAT_VERSION,
                "recorder_version": __version__,
                "git_commit": _git_commit(),
                "created": self.clock.anchor(),
                "task": self.session.task,
                "text": self.session.text,
                "operator": self.session.operator,
                "rig": self.config.rig_name,
                "mount": self.config.mount,
                "config": self.config.to_json(),
            })
            self._session_dir = directory
        return self._session_dir

    def _next_episode(self, session_dir: Path) -> int:
        numbers = [0]
        for path in session_dir.iterdir():
            name = path.name.removesuffix(TMP_SUFFIX)
            if name.startswith(EPISODE_PREFIX) and name[len(EPISODE_PREFIX):].isdigit():
                numbers.append(int(name[len(EPISODE_PREFIX):]))
        return max(numbers) + 1

    # ---- checks -----------------------------------------------------------------------------

    def preflight(self) -> list[str]:
        """Reasons not to start recording, in words for the operator. Empty means ready."""
        problems = []
        for name, health in self.hub.health().items():
            stream = self.hub.streams[name]
            if stream.spec.required and health.status != STATUS_OK:
                detail = f" ({health.message})" if health.message else ""
                problems.append(
                    f"{name}: {health.status}, {health.hz:.0f} Hz of "
                    f"{stream.spec.nominal_hz:.0f} expected{detail}"
                )
        hand = self.hub.streams.get(self.config.dataset.hand)
        sample = hand.latest() if hand is not None else None
        if sample is not None and "mode" in sample.data and int(sample.data["mode"]) != LIVE_MODE:
            problems.append("teleop is not live (hand is holding or released)")
        free_gb = self._free_gb()
        if free_gb is not None and free_gb < self.config.record.min_free_gb:
            problems.append(
                f"disk: {free_gb:.1f} GB free, need {self.config.record.min_free_gb:.0f} GB"
            )
        return problems

    def _free_gb(self) -> float | None:
        path = self.config.data_root
        while not path.exists() and path != path.parent:
            path = path.parent
        try:
            return shutil.disk_usage(path).free / 1e9
        except OSError:
            return None

    # ---- commands ---------------------------------------------------------------------------

    def start(self, force: bool = False) -> int:
        """Begin an episode. Refuses if preflight() finds problems, unless force."""
        with self._lock:
            if self.state != IDLE:
                raise RecorderError(f"cannot start while {self.state}")
            problems = self.preflight()
            if problems and not force:
                raise RecorderError("not ready to record", problems)
            session_dir = self._ensure_session_dir()
            self._episode = self._next_episode(session_dir)
            self._tmp_dir = session_dir / f"{EPISODE_PREFIX}{self._episode:04d}{TMP_SUFFIX}"
            specs = {name: stream.spec for name, stream in self.hub.streams.items()}
            self._start = self.clock.anchor()
            self._forced = bool(problems)
            self._dropouts, self._down = {}, set()
            free_gb = self._free_gb()
            self._disk_low = False
            self._disk_guard = free_gb is None or free_gb >= self.config.record.min_free_gb
            self._writer = writer = EpisodeWriter(
                self._tmp_dir, specs, self.config.record.jpeg_quality,
                self.config.record.flush_s, self._write_progress,
            )
            since_ns = self._start["mono_ns"] - int(self.config.record.preroll_s * 1e9)
            # Each stream hands over its buffered pre-roll and then every new sample, in order.
            self._unsubscribe = [
                stream.subscribe(lambda sample, n=name: writer.add(n, sample), since_ns)
                for name, stream in self.hub.streams.items()
            ]
            self.state = RECORDING
            self.hub.add_event("record_start", episode=self._episode)
            self._write_progress()
        self._notify("start", episode=self._episode)
        return self._episode

    def stop(self) -> dict[str, Any]:
        """End the episode and write it to the temporary folder. Returns the review summary."""
        with self._lock:
            if self.state != RECORDING:
                raise RecorderError(f"cannot stop while {self.state}")
            self._end_ns = self.clock.now_ns()
            for unsubscribe in self._unsubscribe:
                unsubscribe()
            self._unsubscribe = []
            self.hub.add_event("record_stop", episode=self._episode)
            assert self._writer is not None and self._tmp_dir is not None
            try:
                self._summary = self._finish_episode()
            except Exception as error:  # noqa: BLE001 - episode.json itself cannot be written
                # The episode cannot be finished now. Return to idle so the operator can fix
                # the cause and record again; what reached the disk stays in the temporary
                # folder and can be kept later.
                try:
                    self._writer.abort()
                except Exception:  # noqa: BLE001 - best effort
                    pass
                self._writer = None
                kept, self._tmp_dir = self._tmp_dir, None
                self.state = IDLE
                self.hub.add_event("record_failed", episode=self._episode, error=str(error))
                failure = RecorderError(
                    f"the episode could not be finished ({error}); what was written is kept "
                    f"in {kept}"
                )
            else:
                failure = None
                self._writer = None
        if failure is not None:
            self._notify("failed", episode=self._episode)
            raise failure
        with self._lock:
            self.state = REVIEW
            summary = self._summary
        self._notify("stop", episode=self._episode)
        return summary

    def _header(self) -> dict[str, Any]:
        """Everything about the episode that is known before it ends."""
        return {
            "format": FORMAT_VERSION,
            "episode": self._episode,
            "task": self.session.task,
            "text": self.session.text,
            "operator": self.session.operator,
            "rig": self.config.rig_name,
            "mount": self.config.mount,
            "start": self._start,
            "preroll_s": self.config.record.preroll_s,
            "result": None,
            "flags": {
                "forced_start": self._forced,
                "dropouts": dict(self._dropouts),
                "disk_low": self._disk_low,
                "write_errors": {},
                "recovered": False,
            },
            "streams": {n: s.spec.to_json() for n, s in self.hub.streams.items()},
        }

    def _write_events(self, directory: Path) -> None:
        events = self.hub.events_since(
            self._start["mono_ns"] - int(self.config.record.preroll_s * 1e9)
        )
        tmp = directory / (EVENTS_FILE + ".tmp")
        with tmp.open("w", encoding="utf-8") as file:
            for event in events:
                file.write(json.dumps(event, ensure_ascii=False) + "\n")
        os.replace(tmp, directory / EVENTS_FILE)

    def _write_progress(self) -> None:
        """Called with every chunk the writer puts on disk: the header and the events so far,
        so that an episode whose recorder died can still be described. Takes no recorder
        lock (it runs on the writer's thread while stop() may be waiting for that thread)."""
        directory = self._tmp_dir
        if directory is None:
            return
        self._write_events(directory)
        write_json(directory / PROGRESS_FILE, self._header())

    def _finish_episode(self) -> dict[str, Any]:
        """Flush the writer and write events.jsonl and episode.json into the temporary folder.
        A stream that could not be written is flagged in the summary, not thrown away."""
        assert self._writer is not None and self._tmp_dir is not None
        stats = self._writer.close()
        self._write_events(self._tmp_dir)
        summary = self._header()
        summary["end_ns"] = self._end_ns
        summary["duration_s"] = round((self._end_ns - self._start["mono_ns"]) / 1e9, 3)
        summary["flags"]["write_errors"] = {
            name: value["write_error"] for name, value in stats.items() if value.get("write_error")
        }
        for name, spec in summary["streams"].items():
            spec["stats"] = stats[name]
        write_json(self._tmp_dir / EPISODE_FILE, summary)
        (self._tmp_dir / PROGRESS_FILE).unlink(missing_ok=True)
        return summary

    def save(self, success: bool) -> Path:
        """Keep the episode, labelled success or failure."""
        with self._lock:
            if self.state != REVIEW:
                raise RecorderError(f"cannot save while {self.state}")
            assert self._tmp_dir is not None
            result = "success" if success else "failure"
            self._summary["result"] = result
            write_json(self._tmp_dir / EPISODE_FILE, self._summary)
            final = self._tmp_dir.with_name(self._tmp_dir.name.removesuffix(TMP_SUFFIX))
            self._tmp_dir.rename(final)
            self._tmp_dir = None
            self._counts[result] += 1
            self._last_saved = final
            self.state = IDLE
        self._notify("saved", episode=self._episode, result=result)
        return final

    def discard(self) -> None:
        """Throw the episode away. Works while recording (abort) or in review."""
        with self._lock:
            if self.state == RECORDING:
                for unsubscribe in self._unsubscribe:
                    unsubscribe()
                self._unsubscribe = []
                assert self._writer is not None
                self._writer.abort()
                self._writer = None
            elif self.state != REVIEW:
                raise RecorderError(f"nothing to discard while {self.state}")
            if self._tmp_dir is not None:
                shutil.rmtree(self._tmp_dir, ignore_errors=True)
            self._tmp_dir = None
            self.state = IDLE
            self.hub.add_event("record_discard", episode=self._episode)
        self._notify("discarded", episode=self._episode)

    def close(self) -> Path | None:
        """The program is ending. An episode in progress is stopped and, like one waiting in
        review, left in its temporary folder (returned) to be kept or deleted later."""
        with self._lock:
            if self.state == RECORDING:
                try:
                    self.stop()
                except RecorderError:
                    return None  # stop() already said where the data is
            return self._tmp_dir if self.state == REVIEW else None

    @property
    def active_tmp_dir(self) -> Path | None:
        """The temporary folder the recorder itself is using now (recording or review)."""
        return self._tmp_dir

    def mark(self, label: str = "") -> None:
        """Drop a marker into the event log (e.g. first contact)."""
        with self._lock:
            if self.state != RECORDING:
                raise RecorderError("markers can only be set while recording")
            self.hub.add_event("mark", label=label, episode=self._episode)
        self._notify("mark", label=label)

    def zero_tactile(self) -> list[str]:
        with self._lock:
            if self.state != IDLE:
                raise RecorderError("tactile can only be zeroed while idle")
            return self.hub.zero_tactile()

    def tick(self) -> None:
        """Call about 10 times a second: enforces the time limit, watches for dropouts and
        stops the episode before the disk is full."""
        stop_now = False
        notices: list[tuple[str, str]] = []
        with self._lock:
            if self.state != RECORDING:
                return
            for name, health in self.hub.health().items():
                if not self.hub.streams[name].spec.required:
                    continue
                if health.status not in (STATUS_OK, STATUS_SLOW):
                    if name not in self._down:
                        self._down.add(name)
                        self._dropouts[name] = self._dropouts.get(name, 0) + 1
                        self.hub.add_event("dropout", stream=name, status=health.status)
                        notices.append(("dropout", name))
                elif name in self._down:
                    self._down.discard(name)
                    self.hub.add_event("recovered", stream=name)
                    notices.append(("recovered", name))
            elapsed_s = (self.clock.now_ns() - self._start["mono_ns"]) / 1e9
            stop_now = 0 < self.time_limit_s <= elapsed_s
            free_gb = self._free_gb()
            if (self._disk_guard and free_gb is not None
                    and free_gb < self.config.record.min_free_gb):
                self._disk_low = stop_now = True
                self.hub.add_event("disk_low", free_gb=round(free_gb, 2))
                notices.append(("disk_low", ""))
        for kind, name in notices:
            self._notify(kind, stream=name)
        if stop_now:
            try:
                self.stop()
            except RecorderError:
                # The operator stopped (or discarded) in the same instant, or the write failed
                # and stop() already returned the recorder to idle. Either way nothing to do.
                pass

    # ---- status -----------------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            elapsed_s = 0.0
            if self.state == RECORDING:
                elapsed_s = (self.clock.now_ns() - self._start["mono_ns"]) / 1e9
            elif self.state == REVIEW:
                elapsed_s = self._summary.get("duration_s", 0.0)
            return {
                "state": self.state,
                "episode": self._episode,
                "elapsed_s": round(elapsed_s, 1),
                "time_limit_s": self.time_limit_s,
                "task": self.session.task,
                "text": self.session.text,
                "operator": self.session.operator,
                "session": self._session_dir.name if self._session_dir else None,
                "task_dir": str(self.task_dir),
                "counts": dict(self._counts),
                "dropouts": dict(self._dropouts) if self.state != IDLE else {},
                "down": sorted(self._down) if self.state == RECORDING else [],
                "summary": self._summary if self.state == REVIEW else None,
                "last_saved": str(self._last_saved) if self._last_saved else None,
            }
