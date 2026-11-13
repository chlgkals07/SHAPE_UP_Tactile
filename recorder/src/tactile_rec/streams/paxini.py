"""Paxini GEN3 tactile sensors on one High-Speed Communication Board.

One stream per board. Each sample is the board's auto-push payload, untouched; decoding lives
in `tactile_rec.tactile`. The board gives no timestamp, so the receive time is taken the moment
a frame has been read from the serial port.

FIELD-UNVERIFIED with more than one sensor on a board: single-sensor streaming at ~91 Hz was
observed on 2026-11-12, simultaneous streaming of several sensors was not. Zeroing during a
stream is also untested. Check with `tactile-rec check tactile_a` (field checklist item 2).
"""

from __future__ import annotations

import threading
from typing import Any

import numpy as np

from tactile_rec.clock import Clock
from tactile_rec.stream import ThreadedStream
from tactile_rec.streams import specs
from tactile_rec.tactile import Module, TactileLayout
from tactile_rec.types import Field


def layout_from_board(
    module_names: list[str], point_counts: list[int], has_resultant: bool, has_distributed: bool,
    places: dict[str, str], models: list[str] | None = None,
) -> TactileLayout:
    """Board report -> layout. Every active module must have a place in the config, and every
    configured module must be active: a sensor on the wrong connector should stop the stream,
    not be recorded under the wrong finger."""
    unknown = [name for name in module_names if name not in places]
    absent = [name for name in places if name not in module_names]
    if unknown or absent:
        raise ValueError(
            f"board modules do not match config 'places': active but not configured {unknown}, "
            f"configured but not active {absent}"
        )
    models = models or [""] * len(module_names)
    modules = tuple(
        Module(name, int(points), places[name], model)
        for name, points, model in zip(module_names, point_counts, models)
    )
    return TactileLayout(modules, has_resultant, has_distributed)


class PaxiniStream(ThreadedStream):
    def __init__(self, name: str, cfg: dict[str, Any], clock: Clock | None = None):
        super().__init__(specs.tactile_spec(name, float(cfg["hz"]), bool(cfg["required"])), clock)
        self.port, self.baudrate = str(cfg["port"]), int(cfg["baudrate"])
        self.places = {str(k): str(v) for k, v in cfg["places"].items()}
        self.layout: TactileLayout | None = None
        self.bad_frames = 0
        self._board: Any = None
        self._zero_requested = threading.Event()
        self.last_zero_ns = 0
        self.last_zero_error = ""

    def zero(self) -> None:
        """Ask the reader thread to run the board's calibration (zero at the current load)."""
        self._zero_requested.set()

    def _open(self) -> None:
        from paxini_sdk import HighSpeedHandBoard, registers, sensor_registry

        board = HighSpeedHandBoard(self.port, baudrate=self.baudrate)
        board.open()
        try:
            firmware = board.read_version()
            config = board.read_auto_push_config()
            names = [registers.MODULE_NAMES[m] for m in config.active_modules]
            counts = [config.point_counts.get(m, 0) for m in config.active_modules]
            models = []
            for points in counts:
                variant = sensor_registry.find_by_point_count(points)
                models.append(variant.vendor_part_code if variant else "")
            layout = layout_from_board(
                names, counts, config.has_resultant, config.has_distributed, self.places, models
            )
            board.enable_auto_push()
        except BaseException:
            board.close()
            raise
        self._board = board
        self.layout = layout
        self.spec.fields["payload"] = Field((layout.payload_size,), "uint8", "board bytes")
        self.spec.meta.update({"layout": layout.to_json(), "firmware": firmware, "port": self.port})

    def _close(self) -> None:
        if self._board is not None:
            try:
                self._board.disable_auto_push()
            finally:
                self._board.close()
        self._board = None

    def _read_once(self) -> None:
        from paxini_sdk.exceptions import FrameError
        from paxini_sdk.exceptions import TimeoutError as PaxiniTimeoutError
        from paxini_sdk.protocol import parse_auto_push

        if self._zero_requested.is_set():
            self._zero_requested.clear()
            self._run_zero()
            return
        try:
            raw = self._board.transport.read_auto_push_frame(timeout=0.2)
        except PaxiniTimeoutError:
            return
        t_recv_ns = self.clock.now_ns()
        try:
            parsed = parse_auto_push(raw)
        except FrameError:
            self.bad_frames += 1
            return
        payload = np.frombuffer(parsed.valid_data, dtype=np.uint8)
        if payload.size != self.layout.payload_size:
            self.bad_frames += 1
            return
        self.push(
            {"payload": payload.copy(), "error_code": np.int16(parsed.error_code)},
            t_recv_ns=t_recv_ns,
        )

    def _run_zero(self) -> None:
        # The calibration command expects a plain response, so the push stream is paused
        # around it.
        self._board.disable_auto_push()
        try:
            self._board.calibrate()
            self.last_zero_error = ""
        except Exception as error:  # noqa: BLE001 - shown in the UI; streaming resumes
            self.last_zero_error = str(error)
        finally:
            self.last_zero_ns = self.clock.now_ns()
            self._board.enable_auto_push()
