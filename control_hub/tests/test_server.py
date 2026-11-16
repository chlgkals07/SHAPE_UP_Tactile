from __future__ import annotations

from conftest import wait_for
from fastapi.testclient import TestClient

from control_hub.cli import main
from control_hub.server import create_app
from control_hub.session import Event


def client_for(config_path, tmux) -> TestClient:
    return TestClient(create_app(config_path, tmux, background=False))


def state(client: TestClient, pid: str) -> str:
    return client.get("/api/state").json()["processes"][pid]["state"]


def test_describe_shape(config_path, tmux):
    data = client_for(config_path, tmux).get("/api/describe").json()
    server = data["processes"]["server"]
    assert server["where"] == "이 PC" and server["env_lines"] == ["export GREETING=hello"]
    assert server["conflicts"] == [{"id": "rival", "title": "경쟁자"}]
    assert data["processes"]["client"]["confirm_start"][1] == {"text": "실물 확인",
                                                              "unless_flag": "dry"}
    assert data["profiles"][0]["steps"][:2] == [{"note": "전원을 켠다"}, {"process": "server"}]
    assert data["devices"]["hand"]["kind"] == "leap"
    assert data["devices"]["hand"]["tools"] == ["once"]
    assert len(data["devices"]["hand"]["joints"]) == 16
    assert data["attach"].startswith("tmux -L ")
    assert "ready" in data["processes"]["server"]["ready"]


def test_start_stop_log_over_http(config_path, tmux):
    client = client_for(config_path, tmux)
    assert client.post("/api/process/server/start", json={}).status_code == 200
    wait_for(lambda: state(client, "server") == "ready", what="ready")
    log = client.get("/api/process/server/log").json()
    assert "hello" in log["text"] and log["offset"] > 0
    assert client.get("/api/process/server/runs").json()["runs"] == [log["run"]]

    refused = client.post("/api/process/client/start", json={})
    assert refused.status_code == 409 and "확인이 필요" in refused.json()["detail"]
    assert client.post("/api/process/client/start", json={"confirmed": True}).status_code == 200
    assert client.post("/api/process/server/stop", json={}).status_code == 409  # has a dependent
    assert client.post("/api/process/client/kill", json={}).status_code == 200
    assert client.post("/api/process/server/stop", json={}).status_code == 200
    wait_for(lambda: state(client, "server") == "off", what="off")


def test_unknown_ids_and_foreign_origin(config_path, tmux):
    client = client_for(config_path, tmux)
    assert client.post("/api/process/nope/start", json={}).status_code == 404
    assert client.get("/api/process/nope/log").json()["text"] == ""  # valid id shape, no logs
    assert client.get("/api/process/..%2Fx/log").status_code == 404
    assert client.post("/api/process/once/input", json={"text": "x"}).status_code == 409
    evil = client.post("/api/process/server/start", json={}, headers={"Origin": "http://evil"})
    assert evil.status_code == 403
    assert state(client, "server") == "off"
    same = client.post("/api/process/once/start", json={},
                       headers={"Origin": "http://testserver"})
    assert same.status_code == 200


def test_reload_keeps_old_config_when_broken(config_path, tmux):
    client = client_for(config_path, tmux)
    good = config_path.read_text()
    config_path.write_text(good + "\nnonsense: [")
    bad = client.post("/api/reload", json={})
    assert bad.status_code == 400
    snapshot = client.get("/api/state").json()
    assert "YAML" in snapshot["config_error"] and "server" in snapshot["processes"]
    assert "server" in client.get("/api/describe").json()["processes"]

    config_path.write_text(good.replace("title: 서버", "title: 새 이름"))
    assert client.post("/api/reload", json={}).status_code == 200
    assert client.get("/api/state").json()["config_error"] is None
    assert client.get("/api/describe").json()["processes"]["server"]["title"] == "새 이름"


def test_index_and_cli_validate(config_path, tmux, tmp_path, capsys):
    client = client_for(config_path, tmux)
    assert "Control Hub" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert main(["validate", "--config", str(config_path)]) == 0
    broken = tmp_path / "broken.yaml"
    broken.write_text("processes: {a: {cmd: x, requires: [nope]}}")
    assert main(["validate", "--config", str(broken)]) == 2
    assert "processes.a.requires" in capsys.readouterr().err


def test_state_has_devices_and_scan(config_path, tmux):
    with client_for(config_path, tmux) as client:
        client.app.state.watcher.step()
        data = client.get("/api/state").json()
        assert data["devices"]["hand"]["level"] in ("ok", "bad", "warn", "idle")
        assert "devices" in data["scan"] and data["session"]


def test_sessions_api_flow(config_path, tmux):
    with client_for(config_path, tmux) as client:
        first = client.get("/api/sessions").json()["current"]
        new = client.post("/api/sessions/new").json()["current"]
        listing = client.get("/api/sessions").json()
        assert new != first and listing["current"] == new
        assert listing["sessions"][0]["id"] == new  # the empty first one is cleared away
        assert client.get(f"/api/sessions/{new}/events").json() == {"events": []}
        assert client.get(f"/api/sessions/{new}/incidents").json() == {"incidents": []}


def test_events_limit_keeps_newest(config_path, tmux):
    app = create_app(config_path, tmux, background=False)
    session = app.state.watcher.session
    for i in range(5):
        session.add(Event(float(i), "hand", "log", "bad", str(i)))
    with TestClient(app) as client:
        rows = client.get(f"/api/sessions/{session.current}/events?limit=2").json()["events"]
    assert [e["text"] for e in rows] == ["3", "4"]


def test_session_paths_are_confined(config_path, tmux):
    with client_for(config_path, tmux) as client:
        sid = client.get("/api/sessions").json()["current"]
        assert client.get("/api/sessions/..%2F..%2Fetc/events").status_code == 404
        assert client.get("/api/sessions/nope/incidents").status_code == 404
        assert client.get(f"/api/sessions/{sid}/incidents/..%2Fx").status_code == 404
        assert client.get(f"/api/sessions/{sid}/export?incident=..").status_code == 404


def test_export_zip_and_incident(config_path, tmux):
    import io
    import zipfile

    from control_hub.session import Event

    with client_for(config_path, tmux) as client:
        app = client.app
        sid = client.get("/api/sessions").json()["current"]
        iid = app.state.incidents.on_event(Event(1.0, "hand", "log", "bad", "모터 7", {}),
                                           {}, {}, {})
        assert client.get(f"/api/sessions/{sid}/incidents").json()["incidents"][0]["id"] == iid
        detail = client.get(f"/api/sessions/{sid}/incidents/{iid}").json()
        assert detail["summary"].startswith("# 모터 7")
        response = client.get(f"/api/sessions/{sid}/export?incident={iid}")
        assert response.headers["content-type"] == "application/zip"
        assert f"{iid}/summary.md" in zipfile.ZipFile(io.BytesIO(response.content)).namelist()
