"""RealSense colour stream (D405 wrist camera, D435i external camera) read with pyrealsense2.

Frames are stored as they come from the sensor (BGR, unrotated). `rotation_deg` is only
metadata here; the converter and the preview apply it.

Each frame carries the camera's own timestamp and its domain. Only SYSTEM_TIME and GLOBAL_TIME
are on this PC's wall clock; HARDWARE_CLOCK is the camera's private counter. The domain is
recorded per frame so the converter can tell which it got.

FIELD-UNVERIFIED: written from the pyrealsense2 API, not yet run on the cameras. The ROS
`realsense2_camera` node must not be running at the same time. Check with
`tactile-rec check cam_wrist` (field checklist item 3).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from tactile_rec.clock import Clock
from tactile_rec.stream import ThreadedStream
from tactile_rec.streams import specs
from tactile_rec.types import NO_TIME

FRAME_TIMEOUT_MS = 1000
# pyrealsense2.timestamp_domain values
DOMAIN_HARDWARE, DOMAIN_SYSTEM, DOMAIN_GLOBAL = 0, 1, 2


def frame_src_ns(timestamp_ms: float, domain: int) -> int:
    """Camera timestamp -> epoch ns when it is on the host wall clock, else NO_TIME."""
    if domain in (DOMAIN_SYSTEM, DOMAIN_GLOBAL):
        # Round to microseconds first: an epoch time in ns does not fit a float exactly.
        return int(round(timestamp_ms * 1000.0)) * 1000
    return NO_TIME


class RealSenseStream(ThreadedStream):
    def __init__(self, name: str, cfg: dict[str, Any], clock: Clock | None = None):
        self.width, self.height, self.fps = int(cfg["width"]), int(cfg["height"]), int(cfg["fps"])
        super().__init__(
            specs.camera_spec(
                name, self.width, self.height, float(self.fps),
                int(cfg["rotation_deg"]), bool(cfg["required"]),
            ),
            clock,
        )
        self.serial = str(cfg["serial"])
        self.exposure_us = int(cfg["exposure_us"])
        self._pipeline: Any = None

    def _open(self) -> None:
        import pyrealsense2 as rs  # optional dependency

        pipeline, config = rs.pipeline(), rs.config()
        if self.serial:
            config.enable_device(self.serial)
        config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps)
        profile = pipeline.start(config)
        device = profile.get_device()
        self.spec.meta.update({
            "serial": device.get_info(rs.camera_info.serial_number),
            "model": device.get_info(rs.camera_info.name),
            "usb": device.get_info(rs.camera_info.usb_type_descriptor)
            if device.supports(rs.camera_info.usb_type_descriptor) else "",
            "exposure_us": self.exposure_us,
        })
        if self.exposure_us > 0:
            # Fixed exposure keeps frame timing and motion blur constant. The colour stream
            # belongs to a different sensor on the D405 (stereo module) and the D435i (RGB).
            for sensor in device.query_sensors():
                if sensor.supports(rs.option.enable_auto_exposure) and sensor.supports(
                    rs.option.exposure
                ):
                    sensor.set_option(rs.option.enable_auto_exposure, 0)
                    sensor.set_option(rs.option.exposure, float(self.exposure_us))
        self._pipeline = pipeline

    def _close(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()
        self._pipeline = None

    def _read_once(self) -> None:
        frames = self._pipeline.wait_for_frames(FRAME_TIMEOUT_MS)
        t_recv_ns = self.clock.now_ns()
        color = frames.get_color_frame()
        if not color:
            return
        domain = int(color.get_frame_timestamp_domain())
        self.push(
            {"image": np.asanyarray(color.get_data()).copy(), "ts_domain": np.int8(domain)},
            t_src_ns=frame_src_ns(color.get_timestamp(), domain),
            src_seq=int(color.get_frame_number()),
            t_recv_ns=t_recv_ns,
        )
