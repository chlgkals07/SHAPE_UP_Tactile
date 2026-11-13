"""LEAP hand and Manus glove, received from the `leap_teleop` process over local UDP.

`leap_teleop` keeps owning the hand (serial port, safety loop). Its record sink
(`leap_teleop/record_sink.py`) sends one JSON datagram per control tick. The sender stamps
`t_ns` with CLOCK_MONOTONIC, which is the same clock this process uses.

Packet (version 1):
  {"v": 1, "seq": int, "t_ns": int, "mode": "live" | "hold" | "release",
   "cmd": [16 deg], "sent": [16 deg] | null,
   "pos": [16 deg] | null, "vel": [16 deg/s] | null, "cur": [16 mA] | null,
   "glove": null | {"t_ns": int, "ergo": [20 deg],
                    "nodes": [[x, y, z, qx, qy, qz, qw], ...], "node_names": ["Chain/Joint", ...]}}
`glove` is present only on ticks that carry a new glove sample.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any

import numpy as np

from tactile_rec.clock import Clock
from tactile_rec.stream import Stream, ThreadedStream
from tactile_rec.streams import specs

PACKET_VERSION = 1
MAX_DATAGRAM = 65535


@dataclass(frozen=True)
class HandPacket:
    seq: int
    t_ns: int
    hand: dict[str, np.ndarray]
    glove: dict[str, np.ndarray] | None
    glove_t_ns: int
    node_names: list[str]


def _joint_array(values: Any, name: str) -> np.ndarray:
    if values is None:
        return np.full(specs.HAND_DOF, np.nan, dtype=np.float32)
    array = np.asarray(values, dtype=np.float32)
    if array.shape != (specs.HAND_DOF,):
        raise ValueError(f"{name} must have {specs.HAND_DOF} values, got shape {array.shape}")
    return array


def parse_packet(raw: bytes) -> HandPacket:
    """Decode one datagram. Raises ValueError on anything malformed."""
    try:
        packet = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"not JSON: {error}") from error
    if not isinstance(packet, dict) or packet.get("v") != PACKET_VERSION:
        version = packet.get("v") if isinstance(packet, dict) else None
        raise ValueError(f"unsupported packet version {version}")
    try:
        hand = {
            "cmd": _joint_array(packet["cmd"], "cmd"),
            "sent": _joint_array(packet.get("sent"), "sent"),
            "pos": _joint_array(packet.get("pos"), "pos"),
            "vel": _joint_array(packet.get("vel"), "vel"),
            "cur": _joint_array(packet.get("cur"), "cur"),
            "mode": np.int8(specs.mode_code(str(packet["mode"]))),
        }
        seq, t_ns = int(packet["seq"]), int(packet["t_ns"])
    except KeyError as error:
        raise ValueError(f"missing field {error}") from error
    if packet["cmd"] is None:
        raise ValueError("cmd is required")
    glove_raw = packet.get("glove")
    if glove_raw is None:
        return HandPacket(seq, t_ns, hand, None, 0, [])
    ergo = np.asarray(glove_raw["ergo"], dtype=np.float32)
    if ergo.shape != (specs.GLOVE_ANGLES,):
        raise ValueError(f"glove ergo must have {specs.GLOVE_ANGLES} values")
    nodes_in = np.asarray(glove_raw.get("nodes") or [], dtype=np.float32).reshape(-1, 7)
    count = min(len(nodes_in), specs.GLOVE_MAX_NODES)
    nodes = np.full((specs.GLOVE_MAX_NODES, 7), np.nan, dtype=np.float32)
    nodes[:count] = nodes_in[:count]
    glove = {"ergo": ergo, "nodes": nodes, "n_nodes": np.int16(count)}
    names = [str(n) for n in (glove_raw.get("node_names") or [])][:count]
    return HandPacket(seq, t_ns, hand, glove, int(glove_raw["t_ns"]), names)


class HandUdpStream(ThreadedStream):
    """The `hand` stream. It also feeds the passive `glove` stream (self.glove)."""

    def __init__(self, name: str, cfg: dict[str, Any], clock: Clock | None = None):
        super().__init__(specs.hand_spec(name, float(cfg["hz"]), bool(cfg["required"])), clock)
        self.host, self.port = str(cfg["host"]), int(cfg["port"])
        self.glove: Stream | None = None
        if cfg["glove"]:
            self.glove = Stream(specs.glove_spec("glove", float(cfg["hz"])), self.clock)
        self.bad_packets = 0
        self._socket: socket.socket | None = None

    def _open(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.settimeout(0.2)
        self._socket = sock

    def _close(self) -> None:
        if self._socket is not None:
            self._socket.close()
        self._socket = None

    def _read_once(self) -> None:
        assert self._socket is not None
        try:
            raw, _ = self._socket.recvfrom(MAX_DATAGRAM)
        except TimeoutError:
            return
        t_recv_ns = self.clock.now_ns()
        try:
            packet = parse_packet(raw)
        except ValueError:
            self.bad_packets += 1
            return
        self.push(packet.hand, t_src_ns=packet.t_ns, src_seq=packet.seq, t_recv_ns=t_recv_ns)
        if packet.glove is not None and self.glove is not None:
            if packet.node_names and packet.node_names != self.glove.spec.meta["node_names"]:
                self.glove.spec.meta["node_names"] = packet.node_names
            self.glove.push(packet.glove, t_src_ns=packet.glove_t_ns, t_recv_ns=t_recv_ns)
