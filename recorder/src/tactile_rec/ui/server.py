"""Web UI server. A thin layer: every action is a Recorder method, every number comes from
the Hub. No recording logic lives here.

There is no login. Bind to 127.0.0.1 unless the lab network is trusted.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tactile_rec import live
from tactile_rec.hub import Hub
from tactile_rec.record.session import Recorder, RecorderError, list_episodes
from tactile_rec.types import KIND_VIDEO

STATIC = Path(__file__).parent / "static"
STATE_HZ = 5.0
TICK_HZ = 10.0
FOLDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")


class StartBody(BaseModel):
    force: bool = False


class SaveBody(BaseModel):
    success: bool


class MarkBody(BaseModel):
    label: str = ""


class SessionBody(BaseModel):
    task: str
    text: str = ""
    operator: str
    time_limit_s: float = 0.0


class LabelBody(BaseModel):
    session: str
    episode: str
    result: str


def _list(values: np.ndarray, digits: int = 2) -> list[float | None]:
    return [None if not np.isfinite(v) else round(float(v), digits) for v in values]


def build_state(hub: Hub, recorder: Recorder) -> dict[str, Any]:
    status = recorder.status()
    streams = {}
    for name, health in hub.health().items():
        spec = hub.streams[name].spec
        streams[name] = {
            **health.to_json(), "nominal_hz": spec.nominal_hz, "required": spec.required,
            "kind": spec.kind,
        }
    free = recorder._free_gb()
    return {
        "type": "state",
        "recorder": status,
        "streams": streams,
        "problems": recorder.preflight() if status["state"] == "idle" else [],
        "disk_free_gb": None if free is None else round(free, 1),
    }


def build_live(hub: Hub) -> dict[str, Any]:
    """Latest values for the preview panels (tactile maps, hand bars, arm joints)."""
    cfg = hub.config.dataset
    out: dict[str, Any] = {"type": "live", "tactile": {}, "hand": None, "arm": None}
    for place, values in live.tactile_now(hub).items():
        out["tactile"][place] = {
            "r": [round(float(v) * 0.1, 1) for v in values["resultant"]],  # newtons
            "fz": values["distributed"][:, 2].astype(int).tolist(),  # counts, 0.1 N each
        }
    hand = hub.streams.get(cfg.hand)
    sample = hand.latest() if hand is not None else None
    if sample is not None:
        out["hand"] = {
            "cmd": _list(sample.data["cmd"], 1), "pos": _list(sample.data["pos"], 1),
            "cur": _list(sample.data["cur"], 0), "mode": int(sample.data["mode"]),
        }
    arm_state, arm_action = hub.streams.get(cfg.arm_state), hub.streams.get(cfg.arm_action)
    state = arm_state.latest() if arm_state is not None else None
    action = arm_action.latest() if arm_action is not None else None
    if state is not None:
        out["arm"] = {
            "state": _list(state.data["pos"], 3),
            "action": _list(action.data["pos"], 3) if action is not None else None,
        }
    return out


def describe(hub: Hub) -> dict[str, Any]:
    """Static description for the UI: streams, cameras, tactile layout and taxel positions."""
    cameras, tactile = [], {}
    for name, stream in hub.streams.items():
        if stream.spec.kind == KIND_VIDEO:
            cameras.append({"name": name, "rotation_deg": stream.spec.meta.get("rotation_deg", 0)})
    for stream in hub.tactile_streams().values():
        for module in (stream.spec.meta.get("layout") or {}).get("modules", []):
            tactile[module["place"]] = {
                "board": stream.name, "module": module["name"], "points": module["points"],
                "model": module.get("model", ""), "xy": live.taxel_xy(module["points"]),
            }
    return {
        "config": hub.config.to_json(),
        "specs": {name: stream.spec.to_json() for name, stream in hub.streams.items()},
        "cameras": cameras,
        "tactile": tactile,
        "tactile_order": list(hub.config.dataset.tactile_order),
    }


def episode_rows(task_dir: Path) -> list[dict[str, Any]]:
    rows = []
    if not task_dir.is_dir():
        return rows
    for session_dir in sorted((p for p in task_dir.iterdir() if p.is_dir()), reverse=True):
        for path in reversed(list_episodes(session_dir)):
            try:
                meta = json.loads((path / "episode.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            flags = meta.get("flags", {})
            rows.append({
                "session": session_dir.name, "episode": path.name, "result": meta.get("result"),
                "duration_s": meta.get("duration_s"), "text": meta.get("text", ""),
                "dropouts": flags.get("dropouts", {}), "forced": bool(flags.get("forced_start")),
                "max_gap_ms": max(
                    (s.get("stats", {}).get("max_gap_ms", 0) for s in meta["streams"].values()),
                    default=0,
                ),
            })
    return rows


def create_app(hub: Hub, recorder: Recorder) -> FastAPI:
    app = FastAPI(title="Tactile Recorder", docs_url=None, redoc_url=None)
    clients: set[WebSocket] = set()
    notices: asyncio.Queue = asyncio.Queue()
    loop_holder: dict[str, asyncio.AbstractEventLoop] = {}

    def on_recorder_event(kind: str, detail: dict[str, Any]) -> None:
        # Called from whichever thread ran the recorder command; hop onto the event loop.
        loop = loop_holder.get("loop")
        if loop is not None:
            loop.call_soon_threadsafe(notices.put_nowait, {"type": "notice", "kind": kind, **detail})

    recorder.add_listener(on_recorder_event)

    async def broadcast(message: dict[str, Any]) -> None:
        text = json.dumps(message)
        for client in list(clients):
            try:
                await client.send_text(text)
            except Exception:  # noqa: BLE001 - a closed browser tab
                clients.discard(client)

    async def pump() -> None:
        """Tick the recorder and push state, live values and notices to every browser."""
        tick, state_every = 0, max(1, round(TICK_HZ / STATE_HZ))
        live_every = max(1, round(TICK_HZ / min(TICK_HZ, hub.config.ui.preview_hz)))
        while True:
            await asyncio.sleep(1.0 / TICK_HZ)
            tick += 1
            await asyncio.to_thread(recorder.tick)
            while not notices.empty():
                await broadcast(notices.get_nowait())
            if not clients:
                continue
            if tick % state_every == 0:
                await broadcast(build_state(hub, recorder))
            if tick % live_every == 0:
                await broadcast(build_live(hub))

    @app.on_event("startup")
    async def startup() -> None:
        loop_holder["loop"] = asyncio.get_running_loop()
        app.state.pump = asyncio.create_task(pump())

    @app.on_event("shutdown")
    async def shutdown() -> None:
        app.state.pump.cancel()

    def run(command, *args):
        try:
            return command(*args)
        except RecorderError as error:
            raise HTTPException(409, {"message": str(error), "problems": error.problems}) from error

    # ---- pages ------------------------------------------------------------------------------

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    # ---- live data --------------------------------------------------------------------------

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        return build_state(hub, recorder)

    @app.get("/api/describe")
    def description() -> dict[str, Any]:
        return describe(hub)

    @app.websocket("/ws")
    async def socket(websocket: WebSocket) -> None:
        await websocket.accept()
        clients.add(websocket)
        try:
            await websocket.send_text(json.dumps(build_state(hub, recorder)))
            while True:
                await websocket.receive_text()  # the browser only listens; this detects close
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(websocket)

    @app.get("/api/stream/{camera}")
    async def stream(camera: str) -> StreamingResponse:
        if camera not in hub.streams or hub.streams[camera].spec.kind != KIND_VIDEO:
            raise HTTPException(404, f"no camera named {camera}")
        period = 1.0 / hub.config.ui.preview_hz
        width = hub.config.ui.preview_width

        async def frames():
            last = -1
            while True:
                frame = await asyncio.to_thread(live.preview_jpeg, hub, camera, width)
                if frame is not None and frame[0] != last:
                    last = frame[0]
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame[1] + b"\r\n")
                await asyncio.sleep(period)

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    # ---- recording commands -----------------------------------------------------------------

    @app.post("/api/record/start")
    def start(body: StartBody) -> dict[str, Any]:
        return {"episode": run(recorder.start, body.force)}

    @app.post("/api/record/stop")
    def stop() -> dict[str, Any]:
        return {"summary": run(recorder.stop)}

    @app.post("/api/record/save")
    def save(body: SaveBody) -> dict[str, Any]:
        return {"path": str(run(recorder.save, body.success))}

    @app.post("/api/record/discard")
    def discard() -> dict[str, Any]:
        run(recorder.discard)
        return {}

    @app.post("/api/record/mark")
    def mark(body: MarkBody) -> dict[str, Any]:
        run(recorder.mark, body.label)
        return {}

    @app.post("/api/tactile/zero")
    def zero() -> dict[str, Any]:
        return {"streams": run(recorder.zero_tactile)}

    @app.post("/api/session")
    def session(body: SessionBody) -> dict[str, Any]:
        run(recorder.set_session, body.task, body.text, body.operator)
        run(recorder.set_time_limit, body.time_limit_s)
        return recorder.status()

    # ---- saved episodes ---------------------------------------------------------------------

    def episode_path(session: str, episode: str) -> Path:
        if not FOLDER.match(session) or not FOLDER.match(episode):
            raise HTTPException(400, "bad session or episode name")
        path = recorder.task_dir / session / episode
        if not (path / "episode.json").is_file():
            raise HTTPException(404, "no such episode")
        return path

    @app.get("/api/episodes")
    def episodes() -> dict[str, Any]:
        return {"task_dir": str(recorder.task_dir), "episodes": episode_rows(recorder.task_dir)}

    @app.post("/api/episodes/label")
    def label(body: LabelBody) -> dict[str, Any]:
        if body.result not in ("success", "failure"):
            raise HTTPException(400, "result must be success or failure")
        path = episode_path(body.session, body.episode) / "episode.json"
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta["result"] = body.result
        path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {}

    @app.delete("/api/episodes/{session}/{episode}")
    def delete(session: str, episode: str) -> dict[str, Any]:
        shutil.rmtree(episode_path(session, episode))
        return {}

    return app


def serve(hub: Hub, recorder: Recorder) -> None:
    import uvicorn

    ui = hub.config.ui
    print(f"[tactile-rec] open http://{'localhost' if ui.host == '0.0.0.0' else ui.host}:{ui.port}")
    uvicorn.run(create_app(hub, recorder), host=ui.host, port=ui.port, log_level="warning")
