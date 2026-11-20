from __future__ import annotations

import numpy as np

from leap_teleop.types import Reading


def passthrough(reading: Reading) -> np.ndarray:
    if reading.hand is None:
        raise ValueError("passthrough needs a hand reading")
    return reading.hand.copy()
