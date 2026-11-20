from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ActionChunk:
    chunk_id: int
    obs_id: int
    t_obs_ns: int
    t_reply_ns: int
    actions: np.ndarray


def check_reply(reply: Any, pred_horizon: int, action_dim: int) -> list[str]:
    if not isinstance(reply, dict) or "actions" not in reply:
        return ["reply has no actions"]
    actions = reply["actions"]
    if not isinstance(actions, np.ndarray):
        return [f"actions is a {type(actions).__name__}, not an array"]
    if actions.shape != (pred_horizon, action_dim):
        return [f"actions shape {actions.shape}, expected {(pred_horizon, action_dim)}"]
    if actions.dtype.kind != "f":
        return [f"actions dtype {actions.dtype}, expected float"]
    if not np.isfinite(actions).all():
        return [f"actions has {int((~np.isfinite(actions)).sum())} non-finite values"]
    return []
