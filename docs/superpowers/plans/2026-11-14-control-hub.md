# Control Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 가이드의 명령을 브라우저 한 화면에서 켜고, 끄고, 상태·끊긴 곳·오류·로그를 보는 `control_hub/` 패키지를 만든다.

**Architecture:** 프로세스는 전용 tmux 서버(`tmux -L shapeup`)의 창으로 돈다. hub(FastAPI)는 YAML 설정을 읽어 창을 만들고, Ctrl+C를 보내고, 로그 파일을 읽는 리모컨이다. 브라우저는 1초마다 `/api/state`를 읽고 id만 보낸다.

**Tech Stack:** Python 3.10+, PyYAML, FastAPI, uvicorn, tmux 3.x, 순수 JS/CSS. 시험은 pytest + httpx + 실제 tmux(임시 소켓).

**Spec:** `docs/superpowers/specs/2026-11-14-control-hub-design.md`

## Global Constraints

- `control_hub/`는 `recorder/`, `user_pc/`를 import하지 않는다.
- tmux를 부르는 코드는 `tmux.py`에만 있다. 셸 명령 문자열을 만드는 코드는 `command.py`에만 있다.
- API는 프로세스 id, flag id, 입력 한 줄만 받는다. 명령 문자열은 받지 않는다.
- 끄기는 Ctrl+C다. 강제 종료는 사람이 누를 때만 한다. 자동 재시작은 없다.
- 기본 바인드 `127.0.0.1:8700`. 다른 출처(Origin)의 POST는 거부한다.
- 화면 문구는 한국어, 최소 글자 13px, 색은 상태에만 쓴다 (녹화기 `style.css`와 같은 값).
- ruff `line-length = 100`, 규칙 `E, F, I, B, UP`.

## Review Focus

1. 창 이름이 다른 이름의 접두사일 때(`arm` / `arm_stock`) 엉뚱한 창을 끄지 않는다 → Task 3 시험.
2. 명령에 작은따옴표·큰따옴표·공백 경로가 있어도 ssh + docker 두 겹을 지나 그대로 전달된다 → Task 2 시험.
3. hub가 재시작해도 도는 프로세스를 다시 인식하고 로그 위치를 잃지 않는다 → Task 4 시험.
4. 설정 다시 읽기가 실패하면 이전 설정이 유지되고, 도는 프로세스가 설정에서 사라져도 상태에 남아 끌 수 있다 → Task 4, 6 시험.
5. 로그에 ANSI 색 코드와 `\r`이 섞여도 준비 판정과 오류 힌트가 맞는다 → Task 4 시험.

---

### Task 1: 패키지 뼈대와 설정 (`config.py`)

**Files:** Create `control_hub/pyproject.toml`, `control_hub/.gitignore`, `src/control_hub/__init__.py`, `src/control_hub/config.py`, `tests/test_config.py`

**Interfaces — Produces:**
- `class ConfigError(Exception)`
- 데이터 클래스 (frozen): `Host(name, ssh, container, ssh_options)`, `Flag(id, label, arg, default)`, `Confirm(text, unless_flag)`, `Hint(pattern, text)`, `Ready(log, check)`, `Process(id, title, group, kind, host, env, cmd, flags, requires, conflicts, ready, confirm_start, confirm_stop, input, stop_grace_s, help, hints)`, `Check(id, title, kind, target, help, link)`, `Step(note, process)`, `Profile(id, title, steps)`, `Chain(id, title, items)`, `HubConfig(path, repo, hosts, envs, processes, checks, profiles, chains, hints, ui_host, ui_port, tmux_socket, tmux_session, log_dir, check_interval_s)`
- `load_config(path: Path) -> HubConfig`
- `kind`는 `service` | `tool`. 점검 `kind`는 `ping, tcp, file, http, ssh, usb, process, no_process, command` 중 하나이고 YAML에서는 그 이름이 키다 (`{title: ..., tcp: "host:port"}`).
- `requires`는 프로세스 id 또는 점검 id. `conflicts`는 로드할 때 양방향으로 만든다.
- `{repo}`는 `repo:` 값(없으면 설정 파일에서 위로 올라가며 `.git`이 있는 폴더)으로 치환한다.

- [ ] 시험: 올바른 최소 설정 로드, 모르는 키, 없는 id를 가리키는 `requires`/`conflicts`/`steps`/`chains`/`ready.check`, 없는 `env`/`host`, 틀린 정규식, 점검 종류가 0개 또는 2개, id가 `[a-z0-9_]+`가 아님 → 각각 `ConfigError`에 위치(`processes.arm.requires`)가 들어 있다. 충돌 양방향. `{repo}` 치환.
- [ ] 구현, 시험 통과, 커밋.

### Task 2: 명령 조립 (`command.py`)

**Files:** Create `src/control_hub/command.py`, `tests/test_command.py`

**Interfaces — Produces:**
- `script_for(cfg: HubConfig, proc: Process, flags: frozenset[str]) -> str`: 환경 줄과 명령(+켜진 flag의 `arg`)을 ` && `로 이은 것.
- `build_command(cfg, proc, flags) -> str`: 창에서 실행할 한 줄. `local` → `bash -c <q(script)>`; ssh 호스트 → `ssh -tt <옵션> <ssh> <q(script)>`; 컨테이너 호스트 → `ssh -tt <옵션> <ssh> <q("docker exec -it <컨테이너> bash -c " + q(script))>`.
- 기본 ssh 옵션: `-o ConnectTimeout=5 -o ServerAliveInterval=5 -o ServerAliveCountMax=3`.

- [ ] 시험: 세 위치의 문자열. 따옴표가 든 명령을 `bash -c`로 실제 실행해(ssh 대신 `bash -c`로 한 겹씩 벗겨) 원문이 나오는지. flag 순서는 설정 순서.
- [ ] 구현, 통과, 커밋.

### Task 3: tmux 래퍼 (`tmux.py`)

**Files:** Create `src/control_hub/tmux.py`, `tests/conftest.py`, `tests/test_tmux.py`

**Interfaces — Produces:**
- `class TmuxError(Exception)`
- `@dataclass Window(name, id, dead: bool, exit_code: int | None, pid: int)`
- `class Tmux(socket: str, session: str)`: `available() -> bool`, `windows() -> dict[str, Window]`, `spawn(name, script_path: Path, log_path: Path) -> None`, `interrupt(name)`, `send_line(name, text)`, `kill(name)`, `kill_server()`, `attach_hint() -> str`
- `spawn`: 세션이 없으면 만든다(`remain-on-exit on`). 창은 `script_path.go` 파일이 생길 때까지 기다렸다가 `bash script_path`를 실행하고, `pipe-pane`을 건 뒤 `.go`를 만든다 (첫 줄부터 로그에 남게).
- 모든 조작은 `windows()`로 찾은 창 id(`@N`)를 대상으로 한다. 없는 이름은 `TmuxError`.
- `conftest.py`: 임시 소켓 이름의 `Tmux` fixture, 끝나면 `kill_server()`. tmux가 없으면 skip.

- [ ] 시험: spawn → 로그에 출력, 종료 코드 3으로 끝나면 `dead`/`exit_code == 3`, `interrupt`로 `sleep`이 끝남, `send_line`이 `read`에 도달, `arm_stock`만 있을 때 `interrupt("arm")`은 `TmuxError`, 같은 이름 두 번 spawn은 `TmuxError`.
- [ ] 구현, 통과, 커밋.

### Task 4: 감독 (`supervisor.py`)

**Files:** Create `src/control_hub/supervisor.py`, `src/control_hub/logscan.py`, `tests/test_supervisor.py`

**Interfaces — Consumes:** Task 1–3. `checks: Callable[[], dict[str, CheckResult]]` (Task 5; 시험에서는 dict를 돌려주는 함수).

**Interfaces — Produces:**
- `class HubError(Exception)` (사용자에게 보일 한국어 문장)
- `logscan.clean(text: str) -> str` (ANSI 제거, `\r\n`/`\r` 정리), `class LogScanner(path, ready: Pattern | None, hints: list[Hint])` with `poll() -> None`, `.ready_seen: bool`, `.issues: list[dict]` (최근 20개: `{line, hint}`), 일반 오류 줄은 `(?i)\b(error|fatal|traceback|exception|failed|no such file|not found|refused|denied)\b`.
- `class Supervisor(cfg, tmux, checks)`:
  - `reload(cfg) -> None`
  - `status() -> dict[str, dict]`: 키 `state`(`off|starting|ready|stopping|done|failed`), `exit_code`, `started_at`, `command`, `flags`, `log`, `blockers: list[str]`, `issues`, `stale_config: bool`, `stop_overdue: bool`, `dependents: list[str]`, `orphan: bool`
  - `start(id, flags: Iterable[str] | None, confirmed: bool)`, `stop(id, confirmed: bool)`, `kill(id)`, `clear(id)`, `send_input(id, text)`
  - `read_log(id, offset: int, run: str | None) -> tuple[int, str]`, `runs(id) -> list[str]`
- 상태 규칙: 창 없음 → `off`. 살아 있음 → 끄는 중이면 `stopping`, `ready` 조건 만족이면 `ready`, 아니면 `starting`. 죽음 → 끄기를 요청했던 것이면 창을 지우고 `off`; `tool`이고 코드 0이면 `done`; 그 밖은 `failed`.
- 실행 기록: `<log_dir>/<id>/<YYYYmmdd-HHMMSS>.log`, `.sh`(실행 스크립트), `<log_dir>/<id>/current.json`(`run, command, flags, started_at, stop_requested_at`). 재시작 시 이 파일로 복원한다.
- `start`가 거부하는 경우와 문구: 모르는 id, 이미 켜져 있음, 선행 조건 미충족("먼저 필요: zenoh 라우터 (꺼짐)"), 충돌("같이 켤 수 없음: 녹화기"), 확인 필요.
- `stop`은 `confirm_stop`이 있거나 기대는 프로세스가 돌고 있으면 `confirmed=True`여야 한다.

- [ ] 시험 (실제 tmux, `sleep`/`echo`/`read` 설정): 켜기 → `ready`(로그 정규식, ANSI가 섞인 줄), 점검 기반 ready, 선행·충돌·확인 거부, flag와 `unless_flag`, 끄기 → `off`, 실패 종료 → `failed` + `exit_code` + `issues`에 힌트, tool 성공 → `done` → `clear` → `off`, 입력 허용/거부, 새 `Supervisor`가 도는 프로세스를 복원, `reload` 후 명령이 달라지면 `stale_config`, 설정에서 빠진 도는 프로세스는 `orphan`으로 남고 끌 수 있음, `read_log` 오프셋.
- [ ] 구현, 통과, 커밋.

### Task 5: 점검 (`checks.py`)

**Files:** Create `src/control_hub/checks.py`, `tests/test_checks.py`

**Interfaces — Produces:**
- `@dataclass CheckResult(ok: bool | None, detail: str, checked_at: float)` (`None` = 아직 안 봄)
- `run_check(check: Check, hosts: dict[str, Host]) -> CheckResult`: 종류별 1~3초 시간 제한. 예외는 `ok=False`와 사유.
- `class CheckRunner(cfg)`: `start()`, `stop()`, `reload(cfg)`, `results() -> dict[str, CheckResult]`. 백그라운드 스레드가 `check_interval_s`마다 스레드 풀로 전부 돌린다.

- [ ] 시험: `file`(있음/없음/글롭), `tcp`(임시 리슨 소켓/닫힌 포트), `http`(임시 서버), `process`/`no_process`, `command`(0/1/시간 초과), `CheckRunner`가 결과를 채움.
- [ ] 구현, 통과, 커밋.

### Task 6: 서버와 CLI (`server.py`, `cli.py`)

**Files:** Create `src/control_hub/server.py`, `src/control_hub/cli.py`, `tests/test_server.py`

**Interfaces — Produces:**
- `create_app(config_path: Path, tmux: Tmux | None = None, start_checks: bool = True) -> FastAPI`
- `GET /api/describe` (프로세스·점검·실행표·사슬·tmux 접속 명령), `GET /api/state` (`processes`, `checks`, `config_error`), `POST /api/process/{id}/{start|stop|kill|clear|input}`, `GET /api/process/{id}/log?offset=&run=`, `GET /api/process/{id}/runs`, `POST /api/reload`, `GET /` 정적 파일.
- `HubError` → 409 `{detail}`, 모르는 id → 404, 다른 출처 POST → 403, 설정 오류로 reload 실패 → 400이고 이전 설정 유지.
- CLI: `control-hub serve --config [--host] [--port]`, `validate --config`, `status --config`.

- [ ] 시험 (httpx `TestClient`, 가짜 설정, 실제 tmux): describe 모양, start→state→stop, 확인 없이 start → 409, 모르는 id → 404, `Origin: http://evil` POST → 403, 깨진 YAML로 reload → 400 + 이전 프로세스 목록 유지, `validate`가 오류에서 0이 아닌 코드.
- [ ] 구현, 통과, 커밋.

### Task 7: 화면 (`static/`)

**Files:** Create `src/control_hub/static/index.html`, `app.js`, `style.css`

- 메뉴: **실행**(실행표 단계 + 오른쪽 상세), **전체**(그룹별 모든 프로세스와 도구), **연결**(사슬과 점검 전체, 실패한 점검의 조치 문구).
- 맨 위 띠: 사슬마다 처음 실패한 곳("팔: zenoh :7447 에서 끊김"). 전부 정상이면 숨긴다.
- 상세: 제목, 상태, 가이드 설명, 실제 명령, flag 체크, 막힌 이유, 켜기/끄기/강제 종료/닫기, 문제 목록(오류 줄 + 힌트), 로그(오류 줄 강조, 자동 스크롤, 지난 실행 고르기), 입력 줄, tmux 접속 명령.
- 확인 창: `<dialog>`에 항목 체크박스, 전부 체크해야 버튼 활성.
- [ ] `hub.fake.yaml`로 띄워 브라우저에서 켜기·끄기·실패·입력·확인 창·끊김 표시를 눌러 본다 (스크린샷 확인). 커밋.

### Task 8: 실제 설정과 문서

**Files:** Create `control_hub/config/hub.example.yaml`, `hub.fake.yaml`, `control_hub/README.md`, `docs/data_preparation/control_hub_usage.md`; Modify spec(추가된 사슬·힌트·폴링 반영)

- `hub.example.yaml`: 가이드의 명령을 그대로 옮긴다. 프로세스, 점검, 사슬(팔 / 손 / 녹화), 실행표(leader 트리거 / 손만 / 팔+손 / 수집), 가이드 "문제 해결" 표를 힌트로.
- [ ] 시험: 두 설정 파일이 `load_config`를 통과하고, example의 모든 프로세스가 `build_command`로 조립된다.
- [ ] 사용법 문서: 설치, 실물 없이 돌리기, 설정 고치는 법, 현장 확인 항목, 터미널로 돌아가기.
- [ ] 전체 시험 + ruff, 커밋, push.
