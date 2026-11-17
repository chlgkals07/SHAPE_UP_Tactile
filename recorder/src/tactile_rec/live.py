"""Latest values of the rig in model-ready form. Read-only consumers use this: the UI preview
now, a policy later. It never touches the recording path.

`observe()` builds one observation with the same functions the converter uses
(`tactile_rec.features`), so what a policy sees at run time matches the training data.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from tactile_rec import features
from tactile_rec import tactile as _tactile
from tactile_rec.hub import Hub
from tactile_rec.tactile import TactileLayout, decode_payload


def tactile_now(hub: Hub) -> dict[str, dict[str, np.ndarray]]:
    """{place: {"resultant": (3,) counts, "distributed": (points, 3) counts}} from every board
    that has produced a sample."""
    out: dict[str, dict[str, np.ndarray]] = {}
    for stream in hub.tactile_streams().values():
        sample = stream.latest()
        layout_json = stream.spec.meta.get("layout")
        if sample is None or layout_json is None:
            continue
        decoded = decode_payload(sample.data["payload"], TactileLayout.from_json(layout_json))
        for place, values in decoded.items():
            out[place] = {key: array[0] for key, array in values.items()}
    return out


_preview_cache: dict[tuple[int, str, int], tuple[int, bytes]] = {}


def preview_jpeg(hub: Hub, camera: str, width: int, quality: int = 70) -> tuple[int, bytes] | None:
    """(sample seq, JPEG bytes) of the camera's latest frame, upright and scaled to `width`.

    The result is cached per frame, so several open browser tabs cost one encode, not one each.
    """
    stream = hub.streams.get(camera)
    sample = stream.latest() if stream is not None else None
    if sample is None or "image" not in sample.data:
        return None
    key = (id(stream), camera, width)
    cached = _preview_cache.get(key)
    if cached is not None and cached[0] == sample.seq:
        return cached
    image = features.rotate_bgr(sample.data["image"], int(stream.spec.meta.get("rotation_deg", 0)))
    if width and image.shape[1] > width:
        height = max(1, round(image.shape[0] * width / image.shape[1]))
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return None
    _preview_cache[key] = (sample.seq, encoded.tobytes())
    return _preview_cache[key]


def observe(hub: Hub) -> dict[str, Any] | None:
    """One observation with the dataset's keys, or None until every needed stream has data.

    Images are upright RGB. Tactile is in newtons in `dataset.tactile_order`.
    (The high-rate tactile window is added with the policy runner; the recorder does not
    need it.)
    """
    cfg = hub.config.dataset
    arm = hub.streams[cfg.arm_state].latest()
    hand = hub.streams[cfg.hand].latest()
    if arm is None or hand is None or not np.isfinite(hand.data["pos"]).all():
        return None
    out: dict[str, Any] = {
        features.KEY_STATE: features.joint_vector(arm.data["pos"], hand.data["pos"], cfg.arm_dof),
        features.KEY_CURRENT: hand.data["cur"].astype(np.float32),
    }
    if cfg.tactile:
        now = tactile_now(hub)
        if any(place not in now for place in cfg.tactile_order):
            return None
        batched = {p: {k: v[None] for k, v in values.items()} for p, values in now.items()}
        resultant, distributed = features.tactile_vectors(batched, cfg.tactile_order)
        out[features.KEY_TACTILE], out[features.KEY_TACTILE_DIST] = resultant[0], distributed[0]
    for camera in cfg.cameras:
        stream = hub.streams[camera]
        sample = stream.latest()
        if sample is None:
            return None
        out[features.KEY_IMAGE + camera] = features.orient_image(
            sample.data["image"], int(stream.spec.meta.get("rotation_deg", 0))
        )
    return out


taxel_xy = _tactile.taxel_xy  # kept here for callers of the live module
