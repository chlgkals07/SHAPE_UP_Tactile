"""Stream specs: the field names, shapes and units every adapter (real or fake) must produce."""

from __future__ import annotations

from tactile_rec.tactile import TactileLayout
from tactile_rec.types import (
    KIND_VIDEO,
    SRC_HOST_WALL,
    SRC_MONO,
    SRC_NONE,
    SRC_REMOTE_WALL,
    Field,
    StreamSpec,
)

HAND_DOF = 16
# Same order as leap_teleop.hand.joints.ANGLE_NAMES (a test keeps the two in step).
HAND_JOINTS = (
    "index_mcp_side", "index_mcp_flex", "index_pip_flex", "index_dip_flex",
    "middle_mcp_side", "middle_mcp_flex", "middle_pip_flex", "middle_dip_flex",
    "ring_mcp_side", "ring_mcp_flex", "ring_pip_flex", "ring_dip_flex",
    "thumb_cmc_side", "thumb_cmc_flex", "thumb_mcp_flex", "thumb_ip_flex",
)  # fmt: skip
GLOVE_ANGLES = 20
GLOVE_MAX_NODES = 32
HAND_MODES = ("live", "hold", "release")  # index = stored code; anything else is -1


def mode_code(mode: str) -> int:
    return HAND_MODES.index(mode) if mode in HAND_MODES else -1


def arm_spec(name: str, message: str, joints: list[str], hz: float, required: bool) -> StreamSpec:
    count = len(joints)
    fields = {"pos": Field((count,), "float64", "rad")}
    if message == "joint_state":
        fields["vel"] = Field((count,), "float64", "rad/s")
        fields["eff"] = Field((count,), "float64", "")
    return StreamSpec(
        name, fields=fields, nominal_hz=hz, required=required, src_clock=SRC_REMOTE_WALL,
        meta={"message": message, "joints": list(joints)},
    )


def hand_spec(name: str, hz: float, required: bool) -> StreamSpec:
    joint = (HAND_DOF,)
    return StreamSpec(
        name,
        fields={
            "cmd": Field(joint, "float32", "deg"),  # target after the stale guard
            "sent": Field(joint, "float32", "deg"),  # written to the motors (clip + slew)
            "pos": Field(joint, "float32", "deg"),
            "vel": Field(joint, "float32", "deg/s"),
            "cur": Field(joint, "float32", "mA"),
            "mode": Field((), "int8", "0 live, 1 hold, 2 release"),
        },
        nominal_hz=hz, required=required, src_clock=SRC_MONO,
        meta={"joints": list(HAND_JOINTS), "modes": list(HAND_MODES)},
    )


def glove_spec(name: str, hz: float) -> StreamSpec:
    return StreamSpec(
        name,
        fields={
            "ergo": Field((GLOVE_ANGLES,), "float32", "deg"),
            "nodes": Field((GLOVE_MAX_NODES, 7), "float32", "m, quaternion xyzw"),
            "n_nodes": Field((), "int16", ""),
        },
        nominal_hz=hz, required=False, src_clock=SRC_MONO,
        meta={"node_names": []},
    )


def tactile_spec(
    name: str, hz: float, required: bool, layout: TactileLayout | None = None
) -> StreamSpec:
    size = layout.payload_size if layout is not None else 0
    spec = StreamSpec(
        name,
        fields={
            "payload": Field((size,), "uint8", "board bytes"),
            "error_code": Field((), "int16", ""),
        },
        nominal_hz=hz, required=required, src_clock=SRC_NONE,
    )
    if layout is not None:
        spec.meta["layout"] = layout.to_json()
    return spec


def camera_spec(
    name: str, width: int, height: int, fps: float, rotation_deg: int, required: bool,
    host_clock: bool = True,
) -> StreamSpec:
    return StreamSpec(
        name, kind=KIND_VIDEO,
        fields={
            "image": Field((height, width, 3), "uint8", "BGR"),
            "ts_domain": Field((), "int8", "RealSense timestamp domain"),
        },
        nominal_hz=fps, required=required,
        src_clock=SRC_HOST_WALL if host_clock else SRC_NONE,
        meta={"rotation_deg": rotation_deg, "width": width, "height": height},
    )
