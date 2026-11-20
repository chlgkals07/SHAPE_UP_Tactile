from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from policy_runner.runner import Runner

STATIC = Path(__file__).parent / "static"


def make_app(runner: Runner) -> FastAPI:
    app = FastAPI(title="policy-runner")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/app.js")
    def script() -> FileResponse:
        return FileResponse(STATIC / "app.js")

    @app.get("/api/state")
    def state() -> dict:
        return runner.status()

    @app.post("/api/arm")
    def arm() -> dict:
        runner.arm()
        return runner.status()

    @app.post("/api/disarm")
    def disarm() -> dict:
        runner.disarm()
        return runner.status()

    @app.post("/api/reset")
    def reset() -> dict:
        runner.reset()
        return runner.status()

    return app


def serve(runner: Runner) -> None:
    import uvicorn

    host, port = runner.cfg.ui
    print(f"[policy-runner] open http://{host}:{port}")
    uvicorn.run(make_app(runner), host=host, port=port, log_level="warning")
