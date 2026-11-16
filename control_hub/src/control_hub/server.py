"""Web server. A thin layer: every action is a Supervisor method.

The browser can only name things from the config (a process id, a flag id) and type one line
into a process that asks for input. It can never send a command to run.

There is no login. Bind to 127.0.0.1 unless the lab network is trusted.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from control_hub.checks import CheckRunner
from control_hub.command import build_command
from control_hub.config import LOCAL, ConfigError, HubConfig, Process, load_config
from control_hub.incidents import Incidents
from control_hub.leapcheck import LEAP_JOINTS
from control_hub.session import SessionLog
from control_hub.supervisor import HubError, Supervisor
from control_hub.tmux import Tmux, TmuxError
from control_hub.watcher import Watcher

STATIC = Path(__file__).parent / "static"


class StartBody(BaseModel):
    flags: list[str] | None = None
    confirmed: bool = False


class StopBody(BaseModel):
    confirmed: bool = False


class InputBody(BaseModel):
    text: str = ""


def _where(cfg: HubConfig, proc: Process) -> str:
    if proc.host == LOCAL:
        return "이 PC"
    host = cfg.hosts[proc.host]
    if host.container:
        return f"{host.ssh} 의 컨테이너 {host.container}"
    return host.ssh


def _title(cfg: HubConfig, ref: str) -> str:
    if ref in cfg.processes:
        return cfg.processes[ref].title
    return cfg.checks[ref].title if ref in cfg.checks else ref


def describe(cfg: HubConfig, tmux: Tmux) -> dict[str, Any]:
    processes = {}
    for proc in cfg.processes.values():
        ready = ""
        if proc.ready is not None:
            ready = (f"로그에 /{proc.ready.log.pattern}/ 가 나오면" if proc.ready.log is not None
                     else f"점검 '{_title(cfg, proc.ready.check or '')}' 이 통과하면")
        processes[proc.id] = {
            "id": proc.id, "title": proc.title, "group": proc.group, "kind": proc.kind,
            "where": _where(cfg, proc), "remote": proc.host != LOCAL, "help": proc.help,
            "env_lines": list(cfg.envs.get(proc.env, ())) if proc.env else [],
            "cmd": proc.cmd,
            "ready_check": proc.ready.check if proc.ready is not None else None,
            "full_command": build_command(cfg, proc, [f.id for f in proc.flags if f.default]),
            "flags": [{"id": f.id, "label": f.label, "arg": f.arg, "default": f.default}
                      for f in proc.flags],
            "requires": [{"id": r, "title": _title(cfg, r)} for r in proc.requires],
            "conflicts": [{"id": r, "title": _title(cfg, r)} for r in proc.conflicts],
            "confirm_start": [{"text": c.text, "unless_flag": c.unless_flag}
                              for c in proc.confirm_start],
            "confirm_stop": [c.text for c in proc.confirm_stop],
            "input": proc.input, "ready": ready, "stop_grace_s": proc.stop_grace_s,
        }
    return {
        "config_path": str(cfg.path),
        "attach": tmux.attach_hint(),
        "processes": processes,
        "groups": list(dict.fromkeys(p.group for p in cfg.processes.values())),
        "checks": {c.id: {"id": c.id, "title": c.title, "kind": c.kind, "target": c.target,
                          "help": c.help, "link": c.link} for c in cfg.checks.values()},
        "profiles": [
            {"id": p.id, "title": p.title, "help": p.help,
             "steps": [{"note": s.note} if s.note is not None else {"process": s.process}
                       for s in p.steps]}
            for p in cfg.profiles
        ],
        "devices": {
            d.id: {"id": d.id, "title": d.title, "kind": d.kind, "help": d.help,
                   "recorder_stream": list(d.recorder_stream), "checks": list(d.checks),
                   "processes": list(d.processes), "tools": list(d.tools),
                   "joints": list(LEAP_JOINTS) if d.kind == "leap" else []}
            for d in cfg.devices.values()
        },
    }


def create_app(config_path: Path | str, tmux: Tmux | None = None,
               background: bool = True) -> FastAPI:
    """``background=False`` (tests) starts neither the checks nor the watcher thread."""
    config_path = Path(config_path)
    cfg = load_config(config_path)
    tmux = tmux or Tmux(cfg.tmux_socket, cfg.tmux_session)
    runner = CheckRunner(cfg)
    supervisor = Supervisor(cfg, tmux, runner.results)
    session = SessionLog(cfg.session_dir, cfg.keep_sessions)
    incidents = Incidents(session, supervisor.log_path)
    watcher = Watcher(cfg, supervisor, runner, session, incidents)
    hub: dict[str, Any] = {"cfg": cfg, "config_error": None, "loaded_at": time.time()}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if background:
            runner.start()
            watcher.start()
        try:
            yield
        finally:
            watcher.stop()
            runner.stop()  # the processes themselves belong to tmux and keep running

    app = FastAPI(title="Control Hub", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.supervisor = supervisor
    app.state.runner = runner
    app.state.watcher = watcher
    app.state.incidents = incidents

    @app.middleware("http")
    async def same_origin_only(request: Request, call_next):
        """Refuse a POST that another web page made the browser send.

        A browser attaches an Origin header to cross-site POSTs. If it names a different host
        than the one we were reached at, some other page is trying to press our buttons.
        """
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "다른 사이트에서 온 요청은 받지 않습니다"}, 403)
        return await call_next(request)

    @app.exception_handler(HubError)
    async def hub_error(_request: Request, exc: HubError):
        return JSONResponse({"detail": str(exc)}, 409)

    @app.exception_handler(TmuxError)
    async def tmux_error(_request: Request, exc: TmuxError):
        return JSONResponse({"detail": str(exc)}, 503)

    def call(action, pid: str, *args, **kwargs) -> dict[str, Any]:
        try:
            action(pid, *args, **kwargs)
        except KeyError:
            raise HTTPException(404, f"'{pid}' 는 설정에 없습니다") from None
        return {"ok": True}

    @app.get("/api/describe")
    def api_describe() -> dict[str, Any]:
        return describe(hub["cfg"], tmux)

    @app.get("/api/state")
    def api_state() -> dict[str, Any]:
        return {
            "time": time.time(),
            "loaded_at": hub["loaded_at"],
            "config_error": hub["config_error"],
            "processes": supervisor.status(),
            "checks": {cid: result.to_json() for cid, result in runner.results().items()},
            **watcher.snapshot(),  # devices, scan, session: at most one watcher step old
        }

    @app.post("/api/process/{pid}/start")
    def api_start(pid: str, body: StartBody) -> dict[str, Any]:
        return call(supervisor.start, pid, body.flags, body.confirmed)

    @app.post("/api/process/{pid}/stop")
    def api_stop(pid: str, body: StopBody) -> dict[str, Any]:
        return call(supervisor.stop, pid, body.confirmed)

    @app.post("/api/process/{pid}/kill")
    def api_kill(pid: str) -> dict[str, Any]:
        return call(supervisor.kill, pid)

    @app.post("/api/process/{pid}/clear")
    def api_clear(pid: str) -> dict[str, Any]:
        return call(supervisor.clear, pid)

    @app.post("/api/process/{pid}/input")
    def api_input(pid: str, body: InputBody) -> dict[str, Any]:
        return call(supervisor.send_input, pid, body.text)

    @app.get("/api/process/{pid}/log")
    def api_log(pid: str, offset: int = 0, run: str | None = None) -> dict[str, Any]:
        try:
            return supervisor.read_log(pid, offset, run)
        except KeyError:
            raise HTTPException(404, f"'{pid}' 는 설정에 없습니다") from None

    @app.get("/api/process/{pid}/runs")
    def api_runs(pid: str) -> dict[str, Any]:
        try:
            return {"runs": supervisor.runs(pid)}
        except KeyError:
            raise HTTPException(404, f"'{pid}' 는 설정에 없습니다") from None

    @app.post("/api/reload")
    def api_reload() -> dict[str, Any]:
        """Read the config again. A broken file changes nothing; running processes are kept."""
        try:
            new = load_config(config_path)
        except ConfigError as exc:
            hub["config_error"] = str(exc)
            raise HTTPException(400, str(exc)) from None
        hub.update(cfg=new, config_error=None, loaded_at=time.time())
        supervisor.reload(new)
        runner.reload(new)
        watcher.reload(new)
        return {"ok": True}

    def confined(read, *args):
        """Session and incident ids come from the URL: anything not shaped like one is 404."""
        try:
            return read(*args)
        except KeyError:
            raise HTTPException(404, "그런 세션이나 사고가 없습니다") from None

    @app.get("/api/sessions")
    def api_sessions() -> dict[str, Any]:
        return {"current": session.current, "sessions": session.sessions()}

    @app.post("/api/sessions/new")
    def api_new_session() -> dict[str, Any]:
        return {"current": session.new_session()}

    @app.get("/api/sessions/{sid}/events")
    def api_events(sid: str, dev: str | None = None, level: str | None = None,
                   limit: int = 500) -> dict[str, Any]:
        events = [e for e in confined(session.read_events, sid)
                  if (dev is None or e["dev"] == dev) and (level is None or e["level"] == level)]
        return {"events": events[-limit:] if limit > 0 else events}

    @app.get("/api/sessions/{sid}/incidents")
    def api_incidents(sid: str) -> dict[str, Any]:
        return {"incidents": confined(incidents.list, sid)}

    @app.get("/api/sessions/{sid}/incidents/{iid}")
    def api_incident(sid: str, iid: str) -> dict[str, Any]:
        return confined(incidents.read, sid, iid)

    @app.get("/api/sessions/{sid}/export")
    def api_export(sid: str, incident: str | None = None) -> Response:
        data = confined(incidents.zip, sid, incident)
        name = f"{sid}_{incident}.zip" if incident else f"{sid}.zip"
        disposition = f"attachment; filename*=UTF-8''{quote(name)}"
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": disposition})

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
