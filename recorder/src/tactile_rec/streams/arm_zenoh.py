"""OMY arm topics from the Robot PC, read without ROS through `zenoh-ros2-sdk`.

The Robot PC runs ROS 2 Jazzy on rmw_zenoh. This adapter connects to the Robot PC's zenohd
as a plain zenoh client and builds the Jazzy-style key itself, so the recorder venv needs no
ROS install. It was first needed because the old Humble User PC's rmw_zenoh could not receive
those topics (no type hash in the data key); the Jazzy User PC could, but the venv stays ROS-free.

Field 2026-11-17: receives /joint_states (~400 Hz) and /leader/joint_trajectory (~300 Hz)
once the session runs in client mode (see `use_client_mode`).
The message-to-array functions below are pure and tested.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Sequence
from typing import Any

import numpy as np

from tactile_rec.clock import Clock
from tactile_rec.stream import ThreadedStream
from tactile_rec.streams import specs
from tactile_rec.types import NO_TIME

MSG_TYPES = {
    "joint_state": "sensor_msgs/msg/JointState",
    "joint_trajectory": "trajectory_msgs/msg/JointTrajectory",
}

# The SDK's default session is a zenoh *peer*. Peers learn each other through the router and
# then connect directly, but the Robot PC nodes run in a Docker container whose addresses the
# User PC cannot reach, so a peer receives nothing (field 2026-11-17: 0 samples even on 30/**).
# A *client* sends everything through the router we name. The SDK reads this variable when it
# opens its shared session, so it must be set before the first subscriber is created.
ZENOH_OVERRIDE_ENV = "ZENOH_CONFIG_OVERRIDE"
CLIENT_MODE = 'mode="client"'

# Both arm streams open on their own threads. On a first run the SDK clones the message
# definitions from git; two opens at once raced and one failed with "not found in registry"
# (field 2026-11-17). Opening one at a time avoids that.
_OPEN_LOCK = threading.Lock()


def use_client_mode(environ: dict[str, str] | os._Environ = os.environ) -> None:
    """Add mode="client" to the SDK's zenoh override unless the user already chose a mode."""
    current = environ.get(ZENOH_OVERRIDE_ENV, "").strip()
    if "mode=" in current.replace(" ", ""):
        return
    environ[ZENOH_OVERRIDE_ENV] = f"{CLIENT_MODE};{current}" if current else CLIENT_MODE


def stamp_ns(stamp: Any) -> int:
    """builtin_interfaces/Time -> epoch ns; NO_TIME when the publisher left it at zero."""
    sec, nanosec = int(getattr(stamp, "sec", 0)), int(getattr(stamp, "nanosec", 0))
    if sec == 0 and nanosec == 0:
        return NO_TIME
    return sec * 1_000_000_000 + nanosec


def _select(names: Sequence[str], values: Sequence[float], joints: Sequence[str]) -> np.ndarray:
    """Values reordered to `joints`. NaN where the message carries no value for a joint."""
    lookup = {str(n): i for i, n in enumerate(names)}
    out = np.full(len(joints), np.nan, dtype=np.float64)
    for k, joint in enumerate(joints):
        index = lookup.get(joint)
        if index is not None and index < len(values):
            out[k] = float(values[index])
    return out


def joint_state_data(msg: Any, joints: Sequence[str]) -> dict[str, np.ndarray]:
    """sensor_msgs/JointState -> pos / vel / eff in the configured joint order.

    Raises ValueError if a configured joint has no position: recording a silent NaN as a
    joint angle would be worse than dropping the message.
    """
    names = list(msg.name)
    pos = _select(names, list(msg.position), joints)
    if np.isnan(pos).any():
        missing = [j for j, v in zip(joints, pos, strict=True) if np.isnan(v)]
        raise ValueError(f"joint_states has no position for {missing}; it has {names}")
    return {
        "pos": pos,
        "vel": _select(names, list(msg.velocity), joints),
        "eff": _select(names, list(msg.effort), joints),
    }


def joint_trajectory_data(msg: Any, joints: Sequence[str]) -> dict[str, np.ndarray]:
    """trajectory_msgs/JointTrajectory -> the first point's positions in the joint order."""
    if not msg.points:
        raise ValueError("joint_trajectory has no points")
    names = list(msg.joint_names)
    pos = _select(names, list(msg.points[0].positions), joints)
    if np.isnan(pos).any():
        missing = [j for j, v in zip(joints, pos, strict=True) if np.isnan(v)]
        raise ValueError(f"joint_trajectory has no position for {missing}; it has {names}")
    return {"pos": pos}


class ArmZenohStream(ThreadedStream):
    def __init__(self, name: str, cfg: dict[str, Any], clock: Clock | None = None):
        self.message = cfg["message"]
        self.joints = [str(j) for j in cfg["joints"]]
        super().__init__(
            specs.arm_spec(
                name, self.message, self.joints, float(cfg["hz"]), bool(cfg["required"])
            ),
            clock,
        )
        self.topic = str(cfg["topic"])
        router = str(cfg["router"])
        self.router_ip, _, port = router.partition(":")
        self.router_port = int(port or 7447)
        self.domain_id = int(cfg["domain_id"])
        self.bad_messages = 0
        self._subscriber: Any = None

    def counters(self) -> dict[str, int]:
        return {**super().counters(), "bad_messages": self.bad_messages}

    def _open(self) -> None:
        use_client_mode()
        from zenoh_ros2_sdk import ROS2Subscriber  # optional dependency

        with _OPEN_LOCK:
            self._subscriber = ROS2Subscriber(
                topic=self.topic,
                msg_type=MSG_TYPES[self.message],
                callback=self._on_message,
                domain_id=self.domain_id,
                router_ip=self.router_ip,
                router_port=self.router_port,
            )

    def _close(self) -> None:
        if self._subscriber is not None:
            self._subscriber.close()
        self._subscriber = None

    def _read_once(self) -> None:
        # Messages arrive on the SDK's own thread; this thread only waits for stop().
        self._stop_event.wait(0.2)

    def _on_message(self, msg: Any) -> None:
        t_recv_ns = self.clock.now_ns()
        try:
            if self.message == "joint_state":
                data = joint_state_data(msg, self.joints)
            else:
                data = joint_trajectory_data(msg, self.joints)
        except ValueError as error:
            self.bad_messages += 1
            self.set_error(str(error))
            return
        header = getattr(msg, "header", None)
        t_src_ns = stamp_ns(header.stamp) if header is not None else NO_TIME
        self.push(data, t_src_ns=t_src_ns, t_recv_ns=t_recv_ns)
