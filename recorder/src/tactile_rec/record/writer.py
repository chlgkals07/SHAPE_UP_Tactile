"""Episode writer: one folder per episode, one file per stream.

Numeric streams are small, so they are kept in memory and written once at the end
(`<stream>.npz`). Camera frames are JPEG-compressed and appended to `<stream>.mjpeg` by a
separate thread per camera, with a per-frame index in `<stream>.npz`. `add()` is called from
the device threads and never blocks: if a camera's queue is full the frame is dropped and
counted, and its timestamp was already taken when it was captured.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from tactile_rec.types import KIND_VIDEO, NO_TIME, Sample, StreamSpec

IMAGE_FIELD = "image"
VIDEO_QUEUE_FRAMES = 120
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


class _Columns:
    """Timestamps and sequence numbers shared by both stream kinds."""

    def __init__(self) -> None:
        self.t_recv: list[int] = []
        self.t_src: list[int] = []
        self.seq: list[int] = []
        self.src_seq: list[int] = []

    def add(self, sample: Sample) -> None:
        self.t_recv.append(sample.t_recv_ns)
        self.t_src.append(sample.t_src_ns)
        self.seq.append(sample.seq)
        self.src_seq.append(sample.src_seq)

    def arrays(self) -> dict[str, np.ndarray]:
        return {
            "t_recv_ns": np.asarray(self.t_recv, dtype=np.int64),
            "t_src_ns": np.asarray(self.t_src, dtype=np.int64),
            "seq": np.asarray(self.seq, dtype=np.int64),
            "src_seq": np.asarray(self.src_seq, dtype=np.int64),
        }


class _NumericSink:
    def __init__(self, spec: StreamSpec, directory: Path) -> None:
        self.spec = spec
        self.path = directory / f"{spec.name}.npz"
        self.columns = _Columns()
        self.fields: dict[str, list[np.ndarray]] = {name: [] for name in spec.fields}

    def add(self, sample: Sample) -> None:
        self.columns.add(sample)
        for name, values in self.fields.items():
            values.append(sample.data[name])

    def close(self) -> dict[str, Any]:
        arrays = self.columns.arrays()
        for name, values in self.fields.items():
            field = self.spec.fields[name]
            if values:
                arrays[name] = np.stack(values).astype(field.dtype, copy=False)
            else:
                arrays[name] = np.zeros((0, *field.shape), dtype=field.dtype)
        np.savez(self.path, **arrays)
        return stream_stats(arrays["t_recv_ns"], arrays["src_seq"])

    def abort(self) -> None:
        pass


class _VideoSink:
    def __init__(self, spec: StreamSpec, directory: Path, jpeg_quality: int) -> None:
        self.spec = spec
        self.video_path = directory / f"{spec.name}.mjpeg"
        self.index_path = directory / f"{spec.name}.npz"
        self.columns = _Columns()
        self.extra: dict[str, list[np.ndarray]] = {
            name: [] for name in spec.fields if name != IMAGE_FIELD
        }
        self.offsets: list[int] = []
        self.sizes: list[int] = []
        self.dropped = 0
        self.failed = 0
        self.error = ""
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
            self.columns.add(sample)
            for name, values in self.extra.items():
                values.append(sample.data[name])
            self.offsets.append(self._position)
            self.sizes.append(len(data))
            self._position += len(data)

    def _finish_thread(self) -> None:
        self._queue.put(_STOP)
        self._thread.join()
        try:
            self._file.close()
        except OSError as error:  # the final flush can fail on a full disk
            self.failed += 1
            self.error = str(error)

    def close(self) -> dict[str, Any]:
        self._finish_thread()
        arrays = self.columns.arrays()
        arrays["offset"] = np.asarray(self.offsets, dtype=np.int64)
        arrays["size"] = np.asarray(self.sizes, dtype=np.int64)
        for name, values in self.extra.items():
            field = self.spec.fields[name]
            arrays[name] = (
                np.stack(values).astype(field.dtype, copy=False)
                if values
                else np.zeros((0, *field.shape), dtype=field.dtype)
            )
        np.savez(self.index_path, **arrays)
        stats = stream_stats(arrays["t_recv_ns"], arrays["src_seq"])
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


class EpisodeWriter:
    def __init__(self, directory: Path, specs: dict[str, StreamSpec], jpeg_quality: int = 95):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=False)
        self._sinks: dict[str, _NumericSink | _VideoSink] = {}
        for name, spec in specs.items():
            if spec.kind == KIND_VIDEO:
                self._sinks[name] = _VideoSink(spec, directory, jpeg_quality)
            else:
                self._sinks[name] = _NumericSink(spec, directory)

    def add(self, name: str, sample: Sample) -> None:
        self._sinks[name].add(sample)

    def close(self) -> dict[str, dict[str, Any]]:
        """Flush everything to disk and return per-stream statistics."""
        return {name: sink.close() for name, sink in self._sinks.items()}

    def abort(self) -> None:
        for sink in self._sinks.values():
            sink.abort()
