"""Latest values of the rig in model-ready form. Read-only consumers use this: the UI preview
now, a policy later. It never touches the recording path.

`observe()` builds one observation with the same functions the converter uses
(`tactile_rec.features`), so what a policy sees at run time matches the training data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from tactile_rec import features
from tactile_rec.hub import Hub
from tactile_rec.tactile import TactileLayout, decode_payload

_ROTATE = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


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


def preview_jpeg(hub: Hub, camera: str, width: int, quality: int = 70) -> tuple[int, bytes] | None:
    """(sample seq, JPEG bytes) of the camera's latest frame, upright and scaled to `width`."""
    stream = hub.streams.get(camera)
    sample = stream.latest() if stream is not None else None
    if sample is None or "image" not in sample.data:
        return None
    image = sample.data["image"]
    rotation = int(stream.spec.meta.get("rotation_deg", 0))
    if rotation in _ROTATE:
        image = cv2.rotate(image, _ROTATE[rotation])
    if width and image.shape[1] > width:
        height = max(1, round(image.shape[0] * width / image.shape[1]))
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return (sample.seq, encoded.tobytes()) if ok else None


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


# ---- taxel positions for drawing -------------------------------------------------------------

_DATA_DIRS = (
    # the repo checkout: recorder/src/tactile_rec/live.py -> third_party/paxini/paxini_sdk/data
    Path(__file__).resolve().parents[3] / "third_party" / "paxini" / "paxini_sdk" / "data",
)


def _vendor_points(points: int) -> list[list[float]] | None:
    folders = list(_DATA_DIRS)
    try:
        import paxini_sdk

        folders.insert(0, Path(paxini_sdk.__file__).parent / "data")
    except ImportError:
        pass
    for folder in folders:
        registry = folder / "registry.json"
        if not registry.is_file():
            continue
        for sensor in json.loads(registry.read_text(encoding="utf-8"))["sensors"]:
            if sensor["n_points"] == points:
                data = json.loads((folder / sensor["json_file"]).read_text(encoding="utf-8"))
                return [[p["x_mm"], p["y_mm"]] for p in data["points"]]
    return None


def taxel_xy(points: int) -> list[list[float]]:
    """2D positions (mm) of a sensor's taxels, identified by its point count. Falls back to a
    plain grid when the vendor coordinate files are not available."""
    xy = _vendor_points(points)
    if xy is not None:
        return xy
    columns = max(1, int(np.ceil(np.sqrt(points * 0.6))))
    return [[float(i % columns), float(i // columns)] for i in range(points)]
