"""Episode writer: one folder per episode, one file per stream.

While recording, every stream's rows are written every few seconds as a small chunk file
(`parts/<stream>.part000000.npz`), so a crash or a power cut loses only the last few seconds.
On a normal stop the chunks are joined into `<stream>.npz` and removed. Camera frames are
JPEG-compressed and appended to `<stream>.mjpeg` by a separate thread per camera; their
per-frame index goes through the same chunks.

`add()` is called from the device threads and never blocks: it only appends to a list (or to a
camera's queue; if that is full the frame is dropped and counted). Disk writes happen on the
writer's own threads.
"""

from __future__ import annotations

import os
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from tactile_rec.types import KIND_VIDEO, NO_TIME, Sample, StreamSpec

IMAGE_FIELD = "image"
VIDEO_QUEUE_FRAMES = 120
PARTS_DIR = "parts"
TIME_KEYS = ("t_recv_ns", "t_src_ns", "seq", "src_seq")
VIDEO_KEYS = ("offset", "size")
_STOP = object()


def stream_stats(t_recv_ns: np.ndarray, src_seq: np.ndarray) -> dict[str, Any]:
    count = int(t_recv_ns.size)
    stats: dict[str, Any] = {"count": count, "hz": 0.0, "max_gap_ms": 0.0, "missed": 0}
    if count >= 2:
        span_s = (int(t_recv_ns[-1]) - int(t_recv_ns[0])) / 1e9
        if span_s > 0:
            stats["hz"] = round((count - 1) / span_s, 2)
        stats["max_gap_ms"] = round(float(np.diff(t_recv_ns).max()) / 1e6, 2)
    known = src_seq[src_seq != NO_TIME]
    if known.size >= 2:
        steps = np.diff(known)
        stats["missed"] = int(np.clip(steps - 1, 0, None).sum())
    return stats


def save_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    """Write the file under a temporary name and rename it, so it is complete or absent."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as file:
        np.savez(file, **arrays)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, path)


def _stored_fields(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The fields of a stream that live in its .npz (a camera's image lives in the .mjpeg)."""
    video = spec["kind"] == KIND_VIDEO
    return {k: f for k, f in spec["fields"].items() if not (video and k == IMAGE_FIELD)}


def assemble(directory: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Join a stream's chunk files into `<stream>.npz`, remove them, and return its statistics.

    `spec` is StreamSpec.to_json(). Also used to recover an episode whose recorder died: a
    stream that was already joined (no chunks left) is only read back.
    """
    name = spec["name"]
    final = directory / f"{name}.npz"
    parts = sorted((directory / PARTS_DIR).glob(f"{name}.part*.npz"))
    if not parts and final.is_file():
        with np.load(final) as data:
            return stream_stats(data["t_recv_ns"], data["src_seq"])
    chunks = []
    for part in parts:
        with np.load(part) as data:
            chunks.append({key: data[key] for key in data.files})
    index_keys = TIME_KEYS + (VIDEO_KEYS if spec["kind"] == KIND_VIDEO else ())
    arrays: dict[str, np.ndarray] = {}
    for key in index_keys:
        arrays[key] = (
            np.concatenate([c[key] for c in chunks]) if chunks else np.zeros(0, dtype=np.int64)
        )
    for key, field in _stored_fields(spec).items():
        arrays[key] = (
            np.concatenate([c[key] for c in chunks]) if chunks
            else np.zeros((0, *field["shape"]), dtype=field["dtype"])
        )
    save_npz(final, arrays)
    for part in parts:
        part.unlink()
    return stream_stats(arrays["t_recv_ns"], arrays["src_seq"])


class _Sink:
    """Rows of one stream: collected in memory, written as a chunk on every flush()."""

    def __init__(self, spec: StreamSpec, directory: Path) -> None:
        self.spec = spec
        self.directory = directory
        self.error = ""
        self._fields = tuple(_stored_fields(spec.to_json()))
        self._index_keys = TIME_KEYS + (VIDEO_KEYS if spec.kind == KIND_VIDEO else ())
        self._lock = threading.Lock()
        self._rows = self._empty_rows()
        self._parts = 0

    def _empty_rows(self) -> dict[str, list]:
        return {key: [] for key in (*self._index_keys, *self._fields)}

    def _append(self, sample: Sample, **index: int) -> None:
        with self._lock:
            rows = self._rows
            # The field values first: a sample that lacks one must not leave a row half-added.
            values = [sample.data[name] for name in self._fields]
            for name, value in zip(self._fields, values, strict=True):
                rows[name].append(value)
            rows["t_recv_ns"].append(sample.t_recv_ns)
            rows["t_src_ns"].append(sample.t_src_ns)
            rows["seq"].append(sample.seq)
            rows["src_seq"].append(sample.src_seq)
            for key, number in index.items():
                rows[key].append(number)

    def _before_chunk(self) -> None:
        """Called after the rows were taken and before their chunk is written."""

    def flush(self) -> None:
        with self._lock:
            rows, self._rows = self._rows, self._empty_rows()
        if not rows["t_recv_ns"]:
            return
        try:
            self._before_chunk()
            arrays = {key: np.asarray(rows[key], dtype=np.int64) for key in self._index_keys}
            for name in self._fields:
                dtype = self.spec.fields[name].dtype
                arrays[name] = np.stack(rows[name]).astype(dtype, copy=False)
            parts_dir = self.directory / PARTS_DIR
            parts_dir.mkdir(exist_ok=True)
            save_npz(parts_dir / f"{self.spec.name}.part{self._parts:06d}.npz", arrays)
            self._parts += 1
        except Exception as error:  # noqa: BLE001 - disk full, drive gone, rows of unequal shape
            self.error = f"{type(error).__name__}: {error}"

    def _join(self) -> dict[str, Any]:
        """Final flush, then one .npz. On failure the chunks stay where they are."""
        self.flush()
        try:
            return assemble(self.directory, self.spec.to_json())
        except Exception as error:  # noqa: BLE001 - reported as write_error, nothing is deleted
            self.error = f"{type(error).__name__}: {error}"
            return stream_stats(np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))


class _NumericSink(_Sink):
    def add(self, sample: Sample) -> None:
        self._append(sample)

    def close(self) -> dict[str, Any]:
        stats = self._join()
        if self.error:
            stats["write_error"] = self.error
        return stats

    def abort(self) -> None:
        pass


class _VideoSink(_Sink):
    def __init__(self, spec: StreamSpec, directory: Path, jpeg_quality: int) -> None:
        super().__init__(spec, directory)
        self.video_path = directory / f"{spec.name}.mjpeg"
        self.dropped = 0
        self.failed = 0
        self._params = [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)]
        self._queue: queue.Queue = queue.Queue(maxsize=VIDEO_QUEUE_FRAMES)
        self._file = self.video_path.open("wb")
        self._position = 0
        self._thread = threading.Thread(
            target=self._run, name=f"video-{spec.name}", daemon=True
        )
        self._thread.start()

    def add(self, sample: Sample) -> None:
        try:
            self._queue.put_nowait(sample)
        except queue.Full:
            self.dropped += 1

    def _run(self) -> None:
        while True:
            sample = self._queue.get()
            if sample is _STOP:
                return
            # A failed encode or write (disk full, drive unplugged) must not end this thread:
            # close() waits for it, and a dead thread with a full queue would block stop().
            try:
                ok, encoded = cv2.imencode(".jpg", sample.data[IMAGE_FIELD], self._params)
                if not ok:
                    self.failed += 1
                    continue
                data = encoded.tobytes()
                self._file.write(data)
            except Exception as error:  # noqa: BLE001 - reported through the stream statistics
                self.failed += 1
                self.error = str(error)
                continue
            # The frame is written before its index row exists, so an index row never points
            # at bytes that are not in the file.
            self._append(sample, offset=self._position, size=len(data))
            self._position += len(data)

    def _before_chunk(self) -> None:
        # The index chunk about to be written must not describe frames that are still in
        # Python's buffer.
        self._file.flush()
        os.fsync(self._file.fileno())

    def _finish_thread(self) -> None:
        self._queue.put(_STOP)
        self._thread.join()

    def _close_file(self) -> None:
        try:
            self._file.close()
        except (OSError, ValueError) as error:  # the final flush can fail on a full disk
            self.failed += 1
            self.error = str(error)

    def close(self) -> dict[str, Any]:
        self._finish_thread()
        stats = self._join()
        self._close_file()
        stats["dropped_write"] = self.dropped
        stats["failed_write"] = self.failed
        if self.error:
            stats["write_error"] = self.error
        return stats

    def abort(self) -> None:
        # Empty the queue first so the thread reaches the stop marker quickly.
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        self._finish_thread()
        self._close_file()


class EpisodeWriter:
    def __init__(
        self,
        directory: Path,
        specs: dict[str, StreamSpec],
        jpeg_quality: int = 95,
        flush_s: float = 5.0,
        on_flush: Callable[[], None] | None = None,
    ):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=False)
        self._sinks: dict[str, _NumericSink | _VideoSink] = {}
        for name, spec in specs.items():
            if spec.kind == KIND_VIDEO:
                self._sinks[name] = _VideoSink(spec, directory, jpeg_quality)
            else:
                self._sinks[name] = _NumericSink(spec, directory)
        self._on_flush = on_flush
        self._flush_s = flush_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="episode-flush", daemon=True)
        self._thread.start()

    def add(self, name: str, sample: Sample) -> None:
        self._sinks[name].add(sample)

    def _run(self) -> None:
        while not self._stop.wait(self._flush_s):
            self.flush()

    def flush(self) -> None:
        """Write what has arrived since the last flush as one chunk per stream."""
        for sink in self._sinks.values():
            sink.flush()
        if self._on_flush is not None:
            try:
                self._on_flush()
            except Exception:  # noqa: BLE001 - progress notes are best effort
                pass

    def _stop_flushing(self) -> None:
        self._stop.set()
        self._thread.join()

    def close(self) -> dict[str, dict[str, Any]]:
        """Flush everything to disk and return per-stream statistics. Never raises for a
        stream that could not be written: its statistics carry `write_error` instead."""
        self._stop_flushing()
        stats = {name: sink.close() for name, sink in self._sinks.items()}
        try:
            (self.directory / PARTS_DIR).rmdir()
        except OSError:  # absent, or chunks were kept because joining failed
            pass
        return stats

    def abort(self) -> None:
        """Stop the threads and close the files. Deletes nothing."""
        self._stop_flushing()
        for sink in self._sinks.values():
            sink.abort()
