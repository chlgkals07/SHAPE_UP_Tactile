"""Render the LEAP Hand v1 (right) with every motor ID drawn at its joint.

Uses the repo URDF (user_pc/assets/leap_hand_right.urdf) for kinematics and the
matching visual meshes from dexsuite/dex-urdf@f5e7132 (not vendored; pass --meshes).

    python3 scripts/render_leap_ids.py --meshes <dir containing meshes/visual> --out docs/...

ID -> name comes from leap_teleop.hand.joints.ANGLE_NAMES (URDF joint "k" = motor ID k).
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from leap_teleop.hand.joints import ANGLE_NAMES  # noqa: E402
from leap_teleop.kinematics import LEAP_URDF, _rpy_matrix, load_chain  # noqa: E402

FINGER_COLORS = {
    "index": "#2a78d6",
    "middle": "#1f9e6e",
    "ring": "#d07a12",
    "thumb": "#c2410c",
}
KOREAN = {"index": "검지", "middle": "중지", "ring": "약지", "thumb": "엄지"}
# What each joint does on the real hand (zero = open hand, + = the direction listed).
JOINT_KOREAN = {
    "mcp_side": "옆으로 벌림 (손가락 좌우)",
    "mcp_flex": "뿌리 마디 굽힘 (손바닥 쪽)",
    "pip_flex": "가운데 마디 굽힘",
    "dip_flex": "끝 마디 굽힘",
    "cmc_side": "엄지를 손바닥 앞으로 돌림",
    "cmc_flex": "엄지 비틀기 / 벌림",
    "mcp_flex@thumb": "엄지 가운데 마디 굽힘",
    "ip_flex": "엄지 끝 마디 굽힘",
}


def load_obj(path: Path, keep_every: int) -> tuple[np.ndarray, np.ndarray]:
    verts, faces = [], []
    for line in path.read_text().splitlines():
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("f "):
            idx = [int(tok.split("/")[0]) - 1 for tok in line.split()[1:]]
            for i in range(1, len(idx) - 1):
                faces.append((idx[0], idx[i], idx[i + 1]))
    return np.asarray(verts), np.asarray(faces[::keep_every])


def visuals(urdf: Path):
    root = ET.parse(urdf).getroot()
    for link in root.findall("link"):
        for vis in link.findall("visual"):
            mesh = vis.find("geometry/mesh")
            if mesh is None:
                continue
            origin = vis.find("origin")
            xyz = np.array((origin.get("xyz", "0 0 0") if origin is not None else "0 0 0").split(), float)
            rpy = np.array((origin.get("rpy", "0 0 0") if origin is not None else "0 0 0").split(), float)
            yield link.get("name"), mesh.get("filename"), _rpy_matrix(*rpy), xyz


def joint_children(urdf: Path) -> dict[str, str]:
    root = ET.parse(urdf).getroot()
    return {j.get("name"): j.find("child").get("link") for j in root.findall("joint")}


def render(mesh_root: Path, out: Path, q_deg: np.ndarray, keep_every: int, title: str) -> None:
    chain = load_chain(LEAP_URDF)
    q = {str(i): float(np.deg2rad(q_deg[i])) for i in range(16)}
    tris, cols = [], []
    cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for link, filename, r_vis, t_vis in visuals(LEAP_URDF):
        if filename not in cache:
            cache[filename] = load_obj(mesh_root / filename, keep_every)
        v, f = cache[filename]
        r_link, t_link = chain.link_pose(link, q)
        world = (r_link @ (r_vis @ v.T + t_vis[:, None])).T + t_link
        tris.append(world[f])
        cols.append(np.full(len(f), 0.0 if "palm" in link else 1.0))
    tris = np.concatenate(tris)

    children = joint_children(LEAP_URDF)
    joint_pos = {}
    for i in range(16):
        r, t = chain.link_pose(children[str(i)], q)
        joint_pos[i] = t

    # (title, toward-camera, screen-right, screen-up) in the URDF frame:
    # +x = palm side (fingers curl toward +x), +y = thumb side, +z = along the fingers.
    views = [
        ("손바닥 쪽", (1, 0, 0), (0, 1, 0), (0, 0, 1)),
        ("손등 쪽", (-1, 0, 0), (0, -1, 0), (0, 0, 1)),
    ]
    plt.rcParams["font.family"] = ["NanumGothic", "Noto Sans CJK JP", "DejaVu Sans"]
    fig = plt.figure(figsize=(19, 9.5), dpi=150)
    grid = fig.add_gridspec(1, 3, width_ratios=[1.15, 1.15, 0.9], wspace=0.02)
    axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])]
    table_ax = fig.add_subplot(grid[0, 2])
    shade_base = np.where(np.concatenate(cols)[:, None] == 0.0, [[0.80, 0.80, 0.83]], [[0.55, 0.56, 0.60]])
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    for ax, (name, cam, right, up) in zip(axes, views):
        cam, right, up = (np.asarray(v, float) for v in (cam, right, up))
        depth = (tris @ cam).mean(1)
        order = np.argsort(depth)
        xy = np.stack([tris @ right, tris @ up], axis=-1)[order] * 1000.0
        shade = 0.30 + 0.70 * np.abs(n @ cam)
        face = np.clip(shade_base * shade[:, None], 0, 1)[order]
        ax.add_collection(PolyCollection(xy, facecolors=face, edgecolors=face, linewidths=0.2))
        pts = xy.reshape(-1, 2)
        lo, hi = pts.min(0), pts.max(0)
        pad = 25
        ax.set_xlim(lo[0] - pad, hi[0] + pad)
        ax.set_ylim(lo[1] - pad, hi[1] + pad)
        ax.set_aspect("equal")
        ax.set_axis_off()
        ax.set_title(name, fontsize=16)
        for i, p in joint_pos.items():
            finger = ANGLE_NAMES[i].split("_")[0]
            x, y = p @ right * 1000.0, p @ up * 1000.0
            ax.text(x, y, f"{i}", fontsize=11, weight="bold", color="white", ha="center", va="center",
                    zorder=11, bbox=dict(boxstyle="circle,pad=0.3", fc=FINGER_COLORS[finger], ec="white", lw=1.2))

    table_ax.set_axis_off()
    table_ax.set_xlim(0, 1)
    table_ax.set_ylim(0, 1)
    y = 0.97
    for finger in FINGER_COLORS:
        table_ax.text(0.0, y, f"{KOREAN[finger]} ({finger})", fontsize=15, weight="bold",
                      color=FINGER_COLORS[finger], va="center")
        y -= 0.044
        for i in range(16):
            name = ANGLE_NAMES[i]
            if not name.startswith(finger):
                continue
            joint = name.split("_", 1)[1]
            desc = JOINT_KOREAN.get(f"{joint}@thumb" if finger == "thumb" else joint, JOINT_KOREAN.get(joint, ""))
            table_ax.text(0.03, y, f"{i}", fontsize=12, weight="bold", color="white", ha="center", va="center",
                          bbox=dict(boxstyle="circle,pad=0.3", fc=FINGER_COLORS[finger], ec="white"))
            table_ax.text(0.08, y, f"{name}", fontsize=12, family="DejaVu Sans Mono", va="center")
            table_ax.text(0.47, y, desc, fontsize=12, va="center", color="#333")
            y -= 0.041
        y -= 0.012
    table_ax.text(0.0, y - 0.01, "※ 검지·중지·약지: 벌림(0·4·8)이 뿌리 굽힘(1·5·9)보다\n   손끝 쪽에 있다 (LEAP 구조). 0° = 편 손.",
                  fontsize=11, color="#555", va="top")
    fig.suptitle(title, fontsize=17)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.92, bottom=0.03)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor="white")
    print(f"wrote {out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--meshes", type=Path, required=True, help="directory that contains meshes/visual/*.obj")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--pose", default="", help="comma list id=deg, e.g. 1=40,2=40 (default: open hand)")
    p.add_argument("--keep-every", type=int, default=3, help="draw every Nth triangle (speed)")
    p.add_argument("--title", default="LEAP Hand v1 (오른손) 모터 ID")
    a = p.parse_args()
    q = np.zeros(16)
    for item in filter(None, a.pose.split(",")):
        k, v = item.split("=")
        q[int(k)] = float(v)
    render(a.meshes, a.out, q, a.keep_every, a.title)


if __name__ == "__main__":
    main()
