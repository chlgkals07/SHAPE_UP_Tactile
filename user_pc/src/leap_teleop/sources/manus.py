"""Human-hand input from the Manus SDK ROS 2 node.

The message layout below (manus_ros2_msgs/ManusGlove: side, ergonomics[type, value],
raw_nodes[chain_type, joint_type, pose]) is assumed from the MANUS ROS 2 sample and is not
yet checked against the installed SDK (spec section 2). Only Ros2ManusSource touches it;
human_from_glove is plain Python and carries the tested logic.

rclpy is imported inside Ros2ManusSource.__init__ so the package works without ROS.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping, Sequence

import numpy as np

from leap_teleop.sources.base import Source
from leap_teleop.types import HUMAN_ANGLE_NAMES, KEYPOINT_NAMES, HumanHand, Reading

# Later SDKs renamed some ergonomics types (3.1.1: ThumbMCPSpread -> ThumbSpread).
# Add the rest here once seen on the real SDK.
ERGONOMICS_ALIASES = {"ThumbMCPSpread": ("ThumbSpread",)}

# Keypoint -> (Manus chain type, joint type). A "Proximal" node sits at the MCP joint.
KEYPOINT_NODES = {
    "wrist": ("Hand", "Metacarpal"),
    "thumb_cmc": ("Thumb", "Metacarpal"),
    "thumb_ip": ("Thumb", "Distal"),
    "thumb_tip": ("Thumb", "Tip"),
    "index_mcp": ("Index", "Proximal"),
    "index_tip": ("Index", "Tip"),
    "middle_mcp": ("Middle", "Proximal"),
    "pinky_mcp": ("Pinky", "Proximal"),
}


def human_from_glove(
    ergonomics: Mapping[str, float],
    nodes: Mapping[tuple[str, str], Sequence[float]] | None = None,
) -> HumanHand | None:
    """Build a HumanHand, or None if an angle is missing or anything is not finite.

    Ergonomics keys may carry a side prefix ("RightFingerIndexMCPStretch"); they are matched
    by suffix, also under ERGONOMICS_ALIASES. Missing keypoints only drop the keypoints (the
    thumb then runs affine).
    """
    angles = []
    for name in HUMAN_ANGLE_NAMES:
        names = (name, *ERGONOMICS_ALIASES.get(name, ()))
        matches = [v for k, v in ergonomics.items() if any(k.endswith(n) for n in names)]
        if len(matches) != 1 or not np.isfinite(matches[0]):
            return None
        angles.append(float(matches[0]))
    keypoints = None
    if nodes is not None and all(KEYPOINT_NODES[n] in nodes for n in KEYPOINT_NAMES):
        points = np.array([nodes[KEYPOINT_NODES[n]] for n in KEYPOINT_NAMES], dtype=np.float64)
        keypoints = points if np.all(np.isfinite(points)) else None
    return HumanHand(np.array(angles), keypoints)


class Ros2ManusSource(Source):
    def __init__(
        self, topic: str, side: str = "Right", clock: Callable[[], float] = time.monotonic
    ) -> None:
        import rclpy
        from manus_ros2_msgs.msg import ManusGlove
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data

        self._side = side
        self._clock = clock
        self._rclpy = rclpy
        self._owns_context = not rclpy.ok()
        if self._owns_context:
            rclpy.init()
        self._node = rclpy.create_node("leap_teleop_manus_source")
        self._lock = threading.Lock()
        self._latest: Reading | None = None
        self._node.create_subscription(
            ManusGlove, topic, self._on_message, qos_profile_sensor_data
        )
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._thread.start()

    def _on_message(self, msg) -> None:
        if str(msg.side) != self._side:
            return
        ergonomics = {str(e.type): float(e.value) for e in msg.ergonomics}
        nodes = {
            (str(n.chain_type), str(n.joint_type)): (
                n.pose.position.x, n.pose.position.y, n.pose.position.z
            )
            for n in msg.raw_nodes
        }
        human = human_from_glove(ergonomics, nodes)
        if human is None:
            return
        reading = Reading(timestamp=self._clock(), human=human)
        with self._lock:
            self._latest = reading

    def poll(self, now: float) -> Reading | None:
        with self._lock:
            return self._latest

    @property
    def stop_requested(self) -> bool:
        # Same as Ros2LeaderSource: rclpy's SIGINT handler may shut the context down first.
        return not self._rclpy.ok()

    def close(self) -> None:
        steps = [self._executor.shutdown, self._node.destroy_node]
        if self._owns_context:
            steps.append(self._rclpy.shutdown)
        for step in steps:
            try:
                step()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
        self._thread.join(timeout=1.0)
