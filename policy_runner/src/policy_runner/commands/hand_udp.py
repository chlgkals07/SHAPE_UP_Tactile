from __future__ import annotations

import itertools
import json
import socket

import numpy as np
from tactile_rec.streams.specs import HAND_JOINTS


class HandUdpCommand:
    def __init__(self, host: str, port: int, arm_dof: int):
        self.target = (host, port)
        self.hand = slice(arm_dof, arm_dof + len(HAND_JOINTS))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._seq = itertools.count(1)

    def send(self, row: np.ndarray, t_ns: int) -> None:
        hand_deg = np.rad2deg(np.asarray(row, dtype=np.float64)[self.hand])
        packet = {"v": 1, "seq": next(self._seq), "t_ns": int(t_ns),
                  "hand_deg": [round(float(v), 4) for v in hand_deg]}
        self.sock.sendto(json.dumps(packet).encode(), self.target)

    def close(self) -> None:
        self.sock.close()
