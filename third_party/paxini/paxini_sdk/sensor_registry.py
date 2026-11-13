"""Lookup for bundled sensor coordinate assets.

The Paxini protocol exposes a per-module distributed-force point count via
register 0x0030 + 2*module_idx, but does NOT report which sensor model is
plugged into a slot. Fortunately the 12 stock GEN3 sensor variants all
report distinct point counts (verified against the vendor xlsx files in
the 2025-12-02 product zip), so we can map point_count → vendor_part_code
unambiguously.

If/when the vendor releases a new sensor that collides on point count,
the lookup falls back to a (point_count, geometry) hint.

Asset files live in paxini_sdk/data/<vendor_part>_points.json (lowercase
with underscores). The registry index is paxini_sdk/data/registry.json.

Public API:

    list_sensors()                  -> list of all bundled variants
    find_by_part_code(code)         -> registry entry or None
    find_by_point_count(n,...)      -> registry entry or None
    load_points(part_code_or_entry) -> list of (x_mm, y_mm, z_mm) tuples
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

_DATA_DIR = Path(__file__).parent / "data"
_REGISTRY_PATH = _DATA_DIR / "registry.json"


@dataclass(frozen=True)
class SensorVariant:
    vendor_part_code: str       # e.g. "PXSR-STDDP03G"
    sensor_model: str            # e.g. "PX6AX-GEN3-DP-S2015-Elite"
    sensor_class: str            # "DP" / "IP" / "CP" / "MC"
    geometry: str                # "fingertip" / "finger_pad" / "integrated_tip_pad" / "palm"
    grade: str                   # "Elite" / "Core" / "Omega"
    nominal_size_mm: Optional[int]
    n_points: int
    json_file: str               # filename inside data/, relative


def _load_registry() -> List[SensorVariant]:
    if not _REGISTRY_PATH.exists():
        return []
    blob = json.loads(_REGISTRY_PATH.read_text())
    return [SensorVariant(**s) for s in blob.get("sensors", [])]


_REGISTRY: List[SensorVariant] = _load_registry()


def list_sensors() -> List[SensorVariant]:
    """Return every bundled sensor variant."""
    return list(_REGISTRY)


def find_by_part_code(vendor_part_code: str) -> Optional[SensorVariant]:
    """Look up a sensor by its PXSR-STD... part code (case-insensitive)."""
    needle = vendor_part_code.strip().upper()
    for s in _REGISTRY:
        if s.vendor_part_code.upper() == needle:
            return s
    return None


def find_by_point_count(
    n_points: int,
    geometry_hint: Optional[str] = None,
) -> Optional[SensorVariant]:
    """Resolve a sensor variant from the board-reported point count.

    If multiple variants share the same count (no such collision exists in
    the 2025-12-02 product line, but defensive), prefer the one whose
    geometry matches ``geometry_hint``. Returns None if no match.
    """
    matches = [s for s in _REGISTRY if s.n_points == n_points]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    if geometry_hint:
        for s in matches:
            if s.geometry == geometry_hint:
                return s
    # Multiple matches and no usable hint: return the first to keep behaviour
    # deterministic; caller can iterate matches if they need to choose.
    return matches[0]


def load_points(sensor: Union[str, SensorVariant]) -> List[Tuple[float, float, float]]:
    """Return per-point (x_mm, y_mm, z_mm) tuples for ``sensor``.

    Accepts either a vendor part code string or a SensorVariant returned
    from one of the find_by_... helpers.
    """
    if isinstance(sensor, str):
        variant = find_by_part_code(sensor)
        if variant is None:
            raise KeyError(f"unknown sensor part code: {sensor!r}")
    else:
        variant = sensor
    asset_path = _DATA_DIR / variant.json_file
    if not asset_path.exists():
        raise FileNotFoundError(f"sensor coordinates not bundled: {asset_path}")
    blob = json.loads(asset_path.read_text())
    return [(p["x_mm"], p["y_mm"], p["z_mm"]) for p in blob["points"]]
