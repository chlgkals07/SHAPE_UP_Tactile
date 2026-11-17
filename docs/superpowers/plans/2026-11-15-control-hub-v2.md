# Control Hub v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** hub 를 장치 중심으로 바꾼다: 홈 화면, 장치 페이지 7개(LEAP 모터 표 포함), 오른쪽 상태 패널, 장치 탐색, 로그 오류 → 장치·모터 위치, 세션 기록, 오류마다 사고 폴더.

**Architecture:** 기존 tmux 리모컨 구조는 그대로. 새로 `Watcher` 스레드(1초)가 점검 결과·프로세스 상태·로그 사건의 **변화**를 모아 `SessionLog`(events.jsonl)에 쓰고, bad 사건은 `Incidents` 가 폴더로 남긴다. 장치 상태는 순수 함수(`devices.py`)가 계산한다. 텔레옵은 읽기 실패를 로그에 한 줄 남기는 것만 바꾼다.

**Tech Stack:** Python 3.10+, PyYAML, FastAPI, 순수 JS/CSS. 시험은 pytest + httpx + 실제 tmux(임시 소켓), 가짜 sysfs 디렉터리.

**Spec:** `docs/superpowers/specs/2026-11-15-control-hub-devices-design.md` (앞 설계 `2026-11-14-control-hub-design.md`)

## Global Constraints

- 앞 계획(`2026-11-14-control-hub.md`)의 제약을 모두 따른다: `control_hub/` 는 `recorder/`, `user_pc/` 를 import 하지 않는다, tmux 는 `tmux.py` 에서만, 명령 문자열은 `command.py` 에서만, API 는 id 만 받는다, 바인드 `127.0.0.1:8700`, 다른 Origin 의 POST 거부, 화면 문구 한국어·최소 13px·색은 상태에만, ruff `line-length = 100`, `E, F, I, B, UP`.
- hub 는 장치(시리얼, 카메라)를 **열지 않는다**. sysfs·`/dev/serial/by-id`·ping·lsusb 만 본다.
- 텔레옵 변경(Task 12)은 버스 읽기·재시도·루프를 바꾸지 않는다. 따로 커밋한다.
- 상태 폴더 기본값: 로그 `~/.local/state/control_hub/logs`(지금 그대로), 세션 `~/.local/state/control_hub/sessions`. `keep_sessions: 30`.
- 사건 1초 제한(같은 장치·같은 문구), 장치 상태는 최근 60초 사건, 사고 묶기 30초, 사고 로그 직전 200줄 + 직후 30초, 확인 도구 결과는 사고 뒤 5분 안의 것.
- 설정에 `chains` 가 있으면 오류: `chains 는 v2 에서 없어졌습니다. devices 로 옮깁니다`.
- 장치 id 7개: `robot`, `arm`, `leap`, `glove`, `tactile`, `cam_wrist`, `cam_ext`.
- 모든 sysfs·/dev 경로는 함수 인자(`sys_root`, `dev_root`)로 받아 시험에서 가짜 디렉터리를 쓴다.

## Review Focus

1. hub 가 브라우저 없이 돌 때도(화면을 아무도 안 열어도) 사건·사고가 기록된다. 상태 계산을 `/api/state` 에만 걸면 안 된다 → Task 8 `test_watcher_records_without_browser`.
2. 같은 오류가 초당 수백 줄 찍혀도 사건 파일·사고 폴더가 폭주하지 않는다 → Task 4 `test_event_rate_limit`, Task 7 `test_incident_groups_repeats`.
3. hub 재시작 직후, 이미 쌓여 있던 로그를 다시 읽으며 옛 오류를 새 사건·사고로 다시 만들지 않는다 → Task 8 `test_restart_does_not_replay_old_log`.
4. 세션·사고 폴더 이름과 API 경로에 `..`, `/` 가 들어와도 밖의 파일을 읽지 않는다 → Task 8 `test_session_paths_are_confined`.
5. 장치에 걸리지 않은 프로세스의 오류도 홈에 "기타"로 보인다 (오류가 안 보이는 일 없음) → Task 6 `test_unassigned_issue_goes_to_other`.

---

### Task 1: 설정 — `devices`, `known_usb`, 세션 설정, `chains` 제거

**Files:**
- Modify: `control_hub/src/control_hub/config.py` (dataclass 추가, `TOP_KEYS`, `load_config`)
- Modify: `control_hub/src/control_hub/server.py` (`describe` 의 `chains` 를 `devices` 로)
- Modify: `control_hub/src/control_hub/cli.py:39` (요약 문구: 사슬 → 장치)
- Modify: `control_hub/tests/conftest.py` (BASE 의 `chains` 를 `devices` 로)
- Test: `control_hub/tests/test_config_command.py`, `control_hub/tests/test_server.py`

**Interfaces:**
- Produces:
  ```python
  DEVICE_KINDS = ("generic", "leap")
  EVENT_LEVELS = ("info", "warn", "bad")

  @dataclass(frozen=True)
  class EventRule:
      pattern: re.Pattern[str]
      level: str          # EVENT_LEVELS
      text: str           # "{motors}" 같은 이름 그룹 자리

  @dataclass(frozen=True)
  class Device:
      id: str
      title: str
      kind: str = "generic"
      recorder_stream: tuple[str, ...] = ()
      checks: tuple[str, ...] = ()
      processes: tuple[str, ...] = ()
      tools: tuple[str, ...] = ()
      events: tuple[EventRule, ...] = ()
      usb_id: str = ""     # "vvvv:pppp", 탐색에서 "다른 위치" 표시용
      help: str = ""
  ```
  `HubConfig` 에서 `chains` 를 빼고 `devices: dict[str, Device]`, `known_usb: dict[str, str]` ("vvvv:pppp" → 이름표), `session_dir: Path`, `keep_sessions: int = 30` 을 더한다. `TOP_KEYS` 에 `devices`, `known_usb`, `session_dir`, `keep_sessions` 를 더하고 `chains` 는 뺀다.
  `describe()["devices"]` = `{id: {id, title, kind, recorder_stream, checks, processes, tools, help}}` (순서 유지).

- [ ] **Step 1: 실패하는 시험 쓰기** (`test_config_command.py`)

```python
def test_devices_parsed(cfg):
    dev = cfg.devices["hand"]
    assert dev.kind == "leap" and dev.processes == ("server",) and dev.tools == ("greet",)
    assert dev.recorder_stream == ("hand",)
    rule = dev.events[0]
    assert rule.level == "bad" and rule.pattern.search("IDs: [3, 7]")

@pytest.mark.parametrize("snippet, where", [
    ("devices: {d: {processes: [nope]}}", "devices.d.processes"),
    ("devices: {d: {checks: [nope]}}", "devices.d.checks"),
    ("devices: {d: {tools: [server]}}", "devices.d.tools"),        # tool 이 아닌 프로세스
    ("devices: {d: {kind: robotarm}}", "devices.d.kind"),
    ("devices: {d: {events: [{match: '(', text: x}]}}", "devices.d.events[0]"),
    ("devices: {d: {events: [{match: x, level: fatal, text: x}]}}", "devices.d.events[0].level"),
    ("chains: []", "chains 는 v2 에서 없어졌습니다"),
])
def test_device_errors(tmp_path, snippet, where): ...   # 기존 오류 시험과 같은 방식, 메시지에 where 포함

def test_recorder_stream_accepts_string_or_list(...): ...  # "hand" -> ("hand",), [a, b] -> ("a","b")
```
conftest BASE 의 `chains:` 줄을 다음으로 바꾼다:
```yaml
devices:
  hand:
    title: 손
    kind: leap
    recorder_stream: hand
    checks: [port]
    processes: [server]
    tools: [greet]
    usb_id: "0403:6014"
    events:
      - {match: "IDs: \\[?(?P<motors>[\\d, ]+)", level: bad, text: "모터 응답 없음: {motors}"}
```
기존 `cfg.chains`, `data["chains"]` 시험은 `cfg.devices`, `data["devices"]["hand"]["kind"] == "leap"` 로 바꾼다.

- [ ] **Step 2: 실행해서 실패 확인** — Run: `cd control_hub && .venv/bin/pytest tests/test_config_command.py tests/test_server.py -q` → FAIL (`devices` 없음)
- [ ] **Step 3: 구현** — `_device(did, raw, processes, checks)` 를 `_process`/`_check` 와 같은 방식으로. `events[].level` 기본 `bad`. `tools` 의 각 id 는 `kind == "tool"` 인 프로세스여야 한다. 장치 id 와 프로세스·점검 id 가 겹쳐도 된다 (네임스페이스가 다르다).
- [ ] **Step 4: 실행해서 통과 확인** — 같은 명령 → PASS, 그리고 `.venv/bin/ruff check src tests` 깨끗
- [ ] **Step 5: 커밋** — `git commit -m "feat(control-hub): devices config, drop chains"`

---

### Task 2: 점검 — ping 지연, `serial` 새 종류, `usb` 를 sysfs 로

**Files:**
- Create: `control_hub/src/control_hub/sysfs.py` (USB·시리얼 정보 읽기. Task 3 탐색도 쓴다)
- Modify: `control_hub/src/control_hub/checks.py`, `control_hub/src/control_hub/config.py` (`CHECK_KINDS` 에 `serial`, 점검 키 `warn_below_mbps`)
- Test: `control_hub/tests/test_checks.py` (새 파일), `control_hub/tests/fake_sysfs.py` (가짜 트리 만드는 도우미)

**Interfaces:**
- Produces (`sysfs.py`):
  ```python
  @dataclass(frozen=True)
  class UsbInfo:
      usb_id: str            # "0403:6014"
      manufacturer: str
      product: str
      serial: str
      speed_mbps: int | None
      bus_path: str          # "1-2.3"
      ttys: tuple[str, ...]  # ("ttyUSB0",)
      by_id: tuple[str, ...] # ("usb-FTDI_USB__-__Serial_Converter_FT8ZABCD-if00-port0",)
      videos: tuple[str, ...]

  def usb_devices(sys_root: Path = Path("/sys"), dev_root: Path = Path("/dev")) -> list[UsbInfo]
  def tty_info(tty: str, sys_root=..., dev_root=...) -> dict   # {usb: UsbInfo|None, latency_timer: int|None, rw: bool}
  ```
  sysfs 읽는 곳: `/sys/bus/usb/devices/*/{idVendor,idProduct,manufacturer,product,serial,speed}`, tty 는 `/sys/class/tty/<tty>/device` 를 거슬러 올라가 USB 장치를 찾는다, latency 는 `/sys/bus/usb-serial/devices/<tty>/latency_timer`, video 는 `/sys/class/video4linux/video*/device`.
- Produces (`checks.py`): `CheckResult` 에 `info: dict = {}` 와 `warn: str = ""` 를 더한다 (`to_json` 에 포함). `ping` 은 `info={"ms": 0.4}`. `serial` 은 대상 경로(glob 허용)의 첫 tty 에 대해 `info={"path", "tty", "by_id", "serial", "usb_id", "latency_timer", "rw"}`, latency ≠ 1 이면 `warn="latency timer {n} (1 이어야 빠름). USB 를 다시 꽂으면 16 으로 돌아갑니다"`, 읽기·쓰기 권한이 없으면 `ok=False, detail="권한 없음 (dialout 그룹)"`. `usb` 는 sysfs 로 찾고 `info={"speed_mbps", "serial", "product"}`, 점검에 `warn_below_mbps` 가 있고 속도가 그보다 낮으면 `warn="USB {speed} Mbps 로 잡힘 (USB3 포트에 꽂기)"`.
  `run_check(check, hosts, sys_root=Path("/sys"), dev_root=Path("/dev"))`.

- [ ] **Step 1: 실패하는 시험 쓰기** — `fake_sysfs.make_usb(tmp, usb_id, serial, speed, tty=None, video=None, latency=1)` 도우미로 트리를 만든다.

```python
def test_ping_reports_ms(monkeypatch):  # _sh 를 바꿔 "64 bytes ... time=0.412 ms" 반환
    assert run_check(Check("p","p","ping","x"), {}).info["ms"] == pytest.approx(0.412)
def test_serial_found_with_latency_warning(tmp_path):   # latency=16
    r = run_check(Check("l","l","serial", str(dev / "ttyUSB0")), {}, sys_root=sys_, dev_root=dev)
    assert r.ok and r.info["serial"] == "FT8ZABCD" and "latency timer 16" in r.warn
def test_serial_missing(tmp_path): ...            # ok False, detail "없음"
def test_serial_no_permission(tmp_path): ...      # chmod 0 → ok False, "권한 없음"
def test_usb_speed_warning(tmp_path): ...         # 480 < warn_below_mbps 5000 → warn 에 "480 Mbps"
def test_usb_absent(tmp_path): ...                # ok False, "꽂혀 있지 않음"
```
- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest tests/test_checks.py -q` → FAIL
- [ ] **Step 3: 구현** — `CheckRunner` 는 `sys_root`/`dev_root` 를 생성자 인자로 받아 `run_check` 에 넘긴다 (기본 실제 경로).
- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest -q` 전체 PASS
- [ ] **Step 5: 커밋** — `feat(control-hub): serial check, usb via sysfs, ping latency`

---

### Task 3: 장치 탐색 (보여 주기만)

**Files:**
- Create: `control_hub/src/control_hub/discovery.py`
- Test: `control_hub/tests/test_discovery.py`

**Interfaces:**
- Consumes: `sysfs.usb_devices`, `HubConfig.known_usb`, `HubConfig.devices`, `CheckResult`
- Produces:
  ```python
  def scan(cfg: HubConfig, checks: dict[str, CheckResult],
           sys_root: Path = Path("/sys"), dev_root: Path = Path("/dev")) -> dict
  # {"devices": [ {usb_id, label, manufacturer, product, serial, speed_mbps, bus_path,
  #                ttys, by_id, videos} ],
  #  "misplaced": [ {device: "leap", check: "leap_port", expected: "/dev/ttyUSB0",
  #                  found: "/dev/ttyUSB1", text: "LEAP 이 /dev/ttyUSB1 에 있는 것 같습니다"} ]}
  ```
  `label` = `known_usb[usb_id]`, 없으면 "". `misplaced`: 장치에 `usb_id` 가 있고, 그 장치의 `serial`/`file` 점검이 실패했는데, 탐색에서 같은 `usb_id` 의 tty 가 다른 경로에 있을 때.

- [ ] **Step 1: 실패하는 시험** — `test_scan_lists_and_labels` (가짜 트리 2개 장치, known_usb 이름표), `test_misplaced_leap` (점검 대상 ttyUSB0 실패, 탐색에 0403:6014 가 ttyUSB1 → misplaced 1건, 문구 포함), `test_no_misplaced_when_check_ok`.
- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest tests/test_discovery.py -q` → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: 커밋** — `feat(control-hub): usb/serial discovery view`

---

### Task 4: 로그에서 장치 사건 뽑기

**Files:**
- Modify: `control_hub/src/control_hub/logscan.py`, `control_hub/src/control_hub/supervisor.py`
- Test: `control_hub/tests/test_logscan.py` (새 파일), `control_hub/tests/test_supervisor.py`

**Interfaces:**
- Produces (`logscan.py`):
  ```python
  @dataclass(frozen=True)
  class LogEvent:
      t: float              # 읽은 시각 (time.time())
      level: str
      text: str             # rule.text 에 그룹 값을 넣은 것
      line: str             # 원래 줄 (400자까지)
      motors: tuple[int, ...]  # "motors" 그룹의 숫자들, 없으면 ()
      offset: int           # 그 줄을 읽은 덩어리의 시작 바이트 (로그 API offset 으로 그 근처를 연다)
      hint: str | None
      generic: bool         # 규칙이 아니라 GENERIC_ERROR/힌트로 잡힌 줄 (장치 없으면 "기타")
  ```
  `LogScanner(path, ready, hints, events: Sequence[EventRule] = (), now=time.time)`. `drain() -> list[LogEvent]` 은 마지막 drain 뒤 생긴 사건을 돌려주고 비운다. 사건이 되는 줄: 규칙(`events`)에 맞는 줄은 규칙 수준으로, 규칙에 안 맞고 지금의 `issues` 에 들어가는 줄은 `level="bad"`(힌트 있음) / `"warn"`(GENERIC_ERROR 만), `generic=True`. `ignore` 힌트 줄은 사건이 아니다. **같은 text 는 1초에 한 번**만 사건이 되고, 그 사이 반복은 다음 사건의 횟수로 센다 (`LogEvent` 에 `count: int = 1` 추가).
  `LogScanner.skip_existing()`: 파일 끝으로 offset 을 옮긴다 (재시작 시 옛 줄을 사건으로 만들지 않기). 준비 판정은 영향 없어야 하므로, 이 함수는 `ready_seen` 을 판정하기 위해 끝까지 **읽기는 하되** 사건과 issues 는 만들지 않는다.
- Produces (`supervisor.py`): 스캐너를 만들 때 그 프로세스가 속한 장치들의 `events` 를 넘긴다. `drain_events() -> dict[str, list[LogEvent]]` (pid → 사건). hub 시작 때 이미 도는 창을 받아들일 때(`_load_run` from `__init__`)는 `skip_existing()` 을 부른다. `Supervisor.log_path(pid, run) -> Path` 를 공개한다 (Task 7 이 쓴다).

- [ ] **Step 1: 실패하는 시험**

```python
def test_rule_extracts_motors(tmp_path):
    rule = EventRule(re.compile(r"IDs: \[?(?P<motors>[\d, ]+)"), "bad", "모터 응답 없음: {motors}")
    log = write(tmp_path, "$ cmd\nMissing or unresponsive DYNAMIXEL IDs: [3, 7]\n")
    sc = LogScanner(log, None, [], [rule]); sc.poll()
    [ev] = sc.drain()
    assert ev.motors == (3, 7) and ev.text == "모터 응답 없음: 3, 7" and not ev.generic
def test_generic_error_becomes_warn_event(tmp_path): ...
def test_ignored_hint_is_not_event(tmp_path): ...
def test_event_rate_limit(tmp_path):  # 같은 줄 500번을 now 고정으로 → 사건 1개, 1.1초 뒤 한 줄 더 → count 가 반영된 사건 1개
def test_header_line_is_not_event(tmp_path): ...  # "$ ... IDs: [1]" 첫 줄은 무시
def test_skip_existing_keeps_ready_but_no_events(tmp_path): ...
```
`test_supervisor.py`: `test_drain_events_by_process` (fake 프로세스가 규칙 줄을 찍으면 `drain_events()["server"]` 에 나옴).
- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest tests/test_logscan.py tests/test_supervisor.py -q` → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — 전체 PASS
- [ ] **Step 5: 커밋** — `feat(control-hub): device events from logs`

---

### Task 5: `leap_check` 출력 읽기

**Files:**
- Create: `control_hub/src/control_hub/leapcheck.py`
- Test: `control_hub/tests/test_leapcheck.py`

**Interfaces:**
- Produces:
  ```python
  LEAP_JOINTS = ("index_mcp_side", ..., "thumb_ip_flex")   # 16개, recorder streams/specs.py HAND_JOINTS 와 같은 순서 (복사, import 금지)
  def parse_leap_check(text: str) -> dict | None
  # {"ok": bool, "missing": [7], "motors": [ {id, joint, responded: bool|None, pos, temp, volt, hw_err} x16 ]}
  # 알아볼 줄이 하나도 없으면 None (화면은 원래 출력을 보여 준다)
  ```
  읽는 줄 (`user_pc/src/leap_teleop/tools/check_hardware.py:89-96`): `Motor IDs/model numbers: {0: 1060, ...}`, `Positions: [..] deg`, `Temperatures: [..] C`, `Input voltages: [..] V`, `Hardware errors: [..]`, 그리고 연결 실패 `Missing or unresponsive DYNAMIXEL IDs: [3, 7]`. 값 배열은 모터 ID 0~15 순서다. 리스트는 `ast.literal_eval` 로 읽는다.

- [ ] **Step 1: 실패하는 시험** — `test_parse_ok_output` (실제 형식의 샘플 문자열, 16개 모두 responded True, temp 값), `test_parse_missing` (`Missing ... [3, 7]` + Traceback → missing [3,7], 해당 칸 responded False, 나머지 None), `test_parse_unknown_returns_none`, `test_hw_error_nonzero_marks_not_ok`.
- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `feat(control-hub): parse leap_check output into motor table`

---

### Task 6: 세션 기록과 장치 상태 계산

**Files:**
- Create: `control_hub/src/control_hub/session.py`, `control_hub/src/control_hub/devices.py`
- Test: `control_hub/tests/test_session.py`, `control_hub/tests/test_devices.py`

**Interfaces:**
- Produces (`session.py`):
  ```python
  @dataclass(frozen=True)
  class Event:
      t: float
      dev: str | None        # 장치 id, 없으면 None ("기타")
      source: str            # "check" | "process" | "log" | "tool"
      level: str             # info | warn | bad
      text: str
      data: dict             # pid, run, offset, motors, check id, exit_code, count ...
      def to_json(self) -> dict

  SESSION_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")
  class SessionLog:
      def __init__(self, root: Path, keep: int = 30, now=time.time) -> None   # 시작하면 새 세션
      current: str                               # 세션 id
      def new_session(self) -> str
      def add(self, event: Event) -> None        # events.jsonl 에 한 줄 + 메모리 최근 500개
      def recent(self, seconds: float | None = None, dev: str | None = None) -> list[Event]
      def note_run(self, pid: str, run: str, log_path: Path) -> None   # runs.json
      def sessions(self) -> list[dict]           # [{id, started, events, incidents}] 최신순
      def read_events(self, sid: str) -> list[dict]   # sid 는 SESSION_PATTERN 이어야 함, 아니면 KeyError
      def dir(self, sid: str | None = None) -> Path
  ```
  `keep` 초과 세션은 새 세션을 만들 때 오래된 것부터 지운다.
- Produces (`devices.py`):
  ```python
  def device_states(cfg: HubConfig, procs: dict[str, dict], checks: dict[str, CheckResult],
                    recent: list[Event], now: float) -> dict[str, dict]
  # {dev_id: {"level": "ok"|"warn"|"bad"|"idle", "summary": str, "last_event": Event json | None,
  #           "motors": {id: {"t": float, "text": str}}  # leap 만: 최근 60초 사건의 모터
  #           }, "_other": {...}}   # 장치 없는 bad/warn 사건
  ```
  규칙: `bad` = 장치 점검 중 `ok False`, 또는 관련 프로세스 `failed`, 또는 최근 60초 bad 사건. `warn` = 점검 `warn`, 또는 최근 60초 warn 사건. `idle` = 점검이 없고 관련 프로세스가 모두 꺼짐. 그 밖 `ok`. `summary` 는 가장 나쁜 원인 한 줄 (예: "모터 응답 없음: 7", "LEAP USB 없음", "leap_manus 오류").

- [ ] **Step 1: 실패하는 시험**

```python
def test_session_writes_jsonl_and_recent(tmp_path): ...
def test_new_session_and_retention(tmp_path):   # keep=2, 세션 3개 만들면 가장 오래된 폴더 없음
def test_read_events_rejects_bad_id(tmp_path):  # "../x" → KeyError
def test_device_bad_from_check(cfg): ...
def test_device_bad_from_recent_event_then_ok_after_60s(cfg): ...
def test_device_idle_when_nothing_runs(cfg): ...
def test_leap_motors_from_events(cfg):           # data.motors (7,) → states["hand"]["motors"][7]
def test_unassigned_issue_goes_to_other(cfg):    # dev None 인 bad 사건 → states["_other"]
```
- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `feat(control-hub): session log and device state`

---

### Task 7: 사고 폴더

**Files:**
- Create: `control_hub/src/control_hub/incidents.py`
- Test: `control_hub/tests/test_incidents.py`

**Interfaces:**
- Consumes: `SessionLog.dir()`, `Event`, `Supervisor.log_path(pid, run)`, `logscan.clean`
- Produces:
  ```python
  class Incidents:
      def __init__(self, session: SessionLog, log_path: Callable[[str, str], Path],
                   now=time.time, group_s=30.0, after_s=30.0, before_lines=200,
                   tool_window_s=300.0) -> None
      def on_event(self, ev: Event, running: dict[str, str], checks: dict, scan: dict) -> str | None
      # bad 사건만. running = {pid: run} (그 순간 도는 프로세스). 새 폴더 id 또는 묶인 폴더 id
      def on_tool_done(self, dev: str, pid: str, run: str) -> None  # 5분 안의 그 장치 사고에 <pid>.txt
      def tick(self) -> None        # after_s 가 지난 사고의 로그 파일을 채운다
      def list(self, sid: str) -> list[dict]          # [{id, t, dev, text, count, last_t}]
      def read(self, sid: str, iid: str) -> dict      # {summary: str, files: {name: text}}
      def zip(self, sid: str, iid: str | None) -> bytes   # iid None = 세션 전체
  ```
  폴더: `<session>/incidents/<HHMMSS>_<dev or other>_<짧은 문구>/`, 문구는 공백 → `_`, `[^\w가-힣_-]` 제거, 30자까지. 내용: `summary.md` (시각, 장치, 사건 문구, 원래 줄, 힌트, 횟수, 마지막 시각, 그때 도는 프로세스), `<pid>.log` (사건의 프로세스: 사건 시점 파일 크기 S0 기준 직전 200줄 + S0 부터 tick 시점까지, 정리된 글자), `others/<pid>.log` (다른 도는 프로세스: 직전 100줄 + 이후), `checks.json` (점검 결과 + 탐색 표). 같은 장치·같은 text 가 `group_s` 안에 또 오면 새 폴더 없이 `count`·`last_t` 만 올리고 `summary.md` 를 다시 쓴다. `read`/`zip` 은 sid·iid 가 패턴(`SESSION_PATTERN`, `^\d{6}_[\w가-힣-]+$`)이 아니면 KeyError.

- [ ] **Step 1: 실패하는 시험** — `test_incident_folder_contents` (가짜 로그 300줄 + 사건 → tick 전엔 summary 만, `now` 를 31초 넘기고 tick → `<pid>.log` 에 직전 200줄과 이후 줄), `test_incident_groups_repeats`, `test_tool_result_attached_within_5min` / `test_tool_result_ignored_after_5min`, `test_read_rejects_traversal`, `test_zip_has_files`.
- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋** — `feat(control-hub): incident folders per error`

---

### Task 8: Watcher 와 API

**Files:**
- Create: `control_hub/src/control_hub/watcher.py`
- Modify: `control_hub/src/control_hub/server.py`
- Test: `control_hub/tests/test_watcher.py`, `control_hub/tests/test_server.py`

**Interfaces:**
- Consumes: Task 1~7 전부.
- Produces (`watcher.py`):
  ```python
  class Watcher:
      def __init__(self, cfg: HubConfig, supervisor: Supervisor, runner: CheckRunner,
                   session: SessionLog, incidents: Incidents, scan_fn=discovery.scan,
                   interval_s: float = 1.0, now=time.time) -> None
      def reload(self, cfg: HubConfig) -> None
      def step(self) -> None      # 한 번: 상태 읽기 → 변화 사건 → 사고 → tick
      def snapshot(self) -> dict  # {"processes", "checks", "devices", "scan", "session"} 마지막 step 결과
      def start(self) -> None; def stop(self) -> None
  ```
  `step` 이 만드는 사건: 점검 ok 변화(첫 결과는 사건 아님, 이후 True→False 는 bad "…없음", False→True 는 info "…다시 잡힘"; warn 이 새로 생기면 warn), 프로세스 상태 변화(시작 info, 준비 info, `failed` bad + 종료 코드, `done` info), `drain_events()` 의 로그 사건(pid 가 속한 장치 첫 번째, 없으면 dev None; `data` 에 pid·run·offset·motors·count), 탐색 장치가 생기거나 사라짐(info). 도구 프로세스가 `done`/`failed` 가 되면 그 도구를 `tools` 에 가진 장치마다 `incidents.on_tool_done`, 그리고 leap 장치면 `parse_leap_check(log)` 결과를 `snapshot()["devices"][dev]["check"]` 에 보관 (시각 포함). 프로세스 시작을 보면 `session.note_run`.
- `server.py`: `create_app` 이 `SessionLog(cfg.session_dir, cfg.keep_sessions)`, `Incidents`, `Watcher` 를 만들고 lifespan 에서 start/stop. `/api/state` 는 지금 필드 + `devices`, `scan`, `session` (현재 id) 를 `watcher.snapshot()` 에서. 새 API:
  - `GET /api/sessions` → `{"current", "sessions": [...]}`
  - `POST /api/sessions/new` → `{"current"}`
  - `GET /api/sessions/{sid}/events?dev=&level=` → `{"events": [...]}`
  - `GET /api/sessions/{sid}/incidents` → `{"incidents": [...]}`
  - `GET /api/sessions/{sid}/incidents/{iid}` → `{"summary", "files"}`
  - `GET /api/sessions/{sid}/export?incident=` → zip (`Content-Disposition: attachment`)
  - KeyError → 404.

- [ ] **Step 1: 실패하는 시험**

```python
def test_watcher_records_without_browser(cfg, tmux, tmp_path):
    # Watcher 만 start (HTTP 요청 없음), fake 프로세스가 "IDs: [7]" 출력
    # → wait_for: session.read_events 에 dev "hand", motors [7] 사건, incidents 폴더 1개
def test_check_transition_events(...):   # 가짜 runner 결과 None→True(사건 없음)→False(bad)→True(info)
def test_restart_does_not_replay_old_log(...):  # 출력 후 Supervisor·Watcher 새로 만들기 → 새 사건 0
def test_tool_done_parses_leap_check(...):     # greet 도구 cmd 를 leap_check 샘플 출력으로 → devices.hand.check.motors
```
`test_server.py`: `test_state_has_devices_and_scan`, `test_sessions_api_flow` (new → list → events), `test_session_paths_are_confined` (`/api/sessions/..%2F..%2Fetc/events` 와 iid `../x` → 404), `test_export_zip`.
- [ ] **Step 2: 실패 확인** → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest -q` 전체 PASS
- [ ] **Step 5: 커밋** — `feat(control-hub): watcher, session and incident API`

---

### Task 9: 화면 — 틀, 오른쪽 상태 패널, 홈

**Files:**
- Modify: `control_hub/src/control_hub/static/index.html`, `app.js`, `style.css`

**Interfaces:**
- Consumes: `/api/describe` (`devices`), `/api/state` (`devices`, `checks`, `processes`, `session`).
- Produces (JS): 해시 경로 `#home`, `#device/<id>`, `#scan`, `#run`, `#logs`, `#all`. 함수 `renderHome()`, `renderRail()`, `setPage(page, arg)`. 기존 `renderSide`/`renderLinks`/`evalChain` 과 연결 페이지는 지운다.

- [ ] **Step 1: 틀** — 3단(왼쪽 메뉴 220px, 가운데, 오른쪽 상태 패널 260px). 메뉴: 홈, 장치(장치 7개 하위 항목, 각 앞에 상태 점), 장치 탐색, 실행표, 로그, 전체. 1100px 미만에서 오른쪽 패널은 가운데 위 띠로 접는다. 첫 화면은 `#home`.
- [ ] **Step 2: 오른쪽 상태 패널** — 점검 전체(점 + 제목 + `ping` 이면 ms, `warn` 이면 노란 줄), 프로세스 "도는 수/전체", 최근 60초 문제 수(누르면 `#logs`). 모든 페이지에서 보인다.
- [ ] **Step 3: 홈** — 장치 칸 격자(칸: 제목, 상태 색 점, `summary` 한 줄; 누르면 `#device/<id>`), 프로세스 한 줄(도는 것만 점과 이름, 누르면 기존 프로세스 상세), 최근 문제 목록(`level` bad/warn 사건 최신 20개: 시각, 장치, 문구, 그 장치의 첫 도구 버튼 "▸ <도구 제목>", 줄을 누르면 사고가 있으면 사고 보기, 없으면 해당 프로세스 로그를 `offset` 에서 연다). `_other` 사건은 장치 이름 "기타".
- [ ] **Step 4: 확인** — `cd control_hub && .venv/bin/control-hub serve --config config/hub.fake.yaml --port 8711` 를 띄우고 `google-chrome --headless=new --window-size=1440,900 --screenshot=/tmp/home.png http://127.0.0.1:8711/#home` 와 `--window-size=1000,800` 로 스크린샷. 홈 칸 7개(fake 설정은 Task 11 전이면 conftest 수준이어도 됨), 오른쪽 패널, 좁은 화면 띠가 보인다. 브라우저 콘솔 오류 없음 (`--enable-logging=stderr --v=0` 출력에 `Uncaught` 없음).
- [ ] **Step 5: 커밋** — `feat(control-hub): home, device-first navigation, status rail`

---

### Task 10: 화면 — 장치 페이지, LEAP 모터 표, 장치 탐색, 로그·사고

**Files:**
- Modify: `control_hub/src/control_hub/static/app.js`, `style.css`

**Interfaces:**
- Consumes: Task 8 의 API, `describe.devices`, `state.devices[dev].check` (Task 8), `state.scan`.
- Produces (JS): `renderDevice(id)`, `renderMotorTable(dev)`, `renderScan()`, `renderLogs()`, `openIncident(sid, iid)`.

- [ ] **Step 1: 장치 페이지 공통 틀** — (1) 연결: 장치 `checks` 각각의 결과와 `info`(경로, by-id, 시리얼, USB 속도, latency, 권한, ping ms)와 `warn`. (2) 관련 프로세스·도구 줄(기존 `processRow` 재사용, 누르면 기존 상세 패널). (3) 마지막 확인 결과: 장치 `tools` 의 마지막 실행 시각·종료 코드·출력 마지막 30줄. (4) 이 장치 사건(현재 세션, 최신 50개). 카메라 장치(`cam_wrist`, `cam_ext`)는 영상 없이 이 틀만, 그리고 "영상은 녹화기 화면에서" 한 줄과 `recorder_ui` 점검이 있으면 링크.
- [ ] **Step 2: LEAP 모터 표** — `kind == "leap"` 이면 (3) 대신 4×4 표(손가락별 줄: 검지, 중지, 약지, 엄지). 칸: ID, 관절 이름, 응답(초록/빨강/회색=모름), 위치°, 온도°C, 전압 V, 오류 비트(0 이 아니면 빨강). 칸 값은 마지막 `leap_check` 결과(확인 시각 표시), 그 위에 최근 60초 로그 사건의 모터는 빨간 테두리와 "14:31 응답 없음". 표 위에 "leap_check 실행" 버튼: 텔레옵이 돌면 막고 "먼저 leap_manus 를 끈다" (기존 `blockers` 문구 사용).
- [ ] **Step 3: 장치 탐색 페이지** — `state.scan.devices` 표(이름표, vendor:product, 제품, 시리얼, 속도, tty/by-id/video, 버스 위치), 위에 `misplaced` 경고 줄. 안내 한 줄: "보여 주기만 합니다. 포트 자동 지정은 추후."
- [ ] **Step 4: 로그 페이지** — 세션 선택(현재 세션 기본, "새 세션" 버튼), 사건 시간표(장치·수준 필터), 사고 목록(시각, 장치, 문구, 횟수). 사고를 누르면 `summary.md` 와 파일 탭(프로세스 로그, others, checks.json, 도구 결과), "zip 받기" 버튼. 사건을 누르면 그 프로세스 로그를 `offset` 에서 연다. 지난 실행 로그 선택 상자는 기존 상세 패널에 그대로 둔다.
- [ ] **Step 5: 확인** — fake 설정으로 띄우고 `#device/leap`, `#scan`, `#logs` 스크린샷. 가짜 LEAP 오류(Task 11)가 모터 7 칸을 빨갛게 하고, 사고 1개가 보이고, zip 이 받아진다 (`curl -s -o /tmp/i.zip ".../export?incident=<id>" && unzip -l /tmp/i.zip`).
- [ ] **Step 6: 커밋** — `feat(control-hub): device pages, LEAP motor table, discovery and incident views`

(Task 10 의 Step 5 는 Task 11 의 fake 설정이 필요하다. Task 11 을 먼저 하거나, Step 5 를 Task 11 뒤에 돌린다.)

---

### Task 11: 설정 파일과 사용법

**Files:**
- Modify: `control_hub/config/hub.example.yaml`, `control_hub/config/hub.fake.yaml`, `docs/data_preparation/control_hub_usage.md`
- Test: `control_hub/tests/test_config_command.py` (기존 "예시·가짜 설정이 검증을 통과" 시험이 두 파일을 읽는다)

- [ ] **Step 1: `hub.example.yaml`** — `chains` 삭제, `devices` 7개 추가. 배정: `robot` (checks robot_ping, robot_ssh, zenoh_port; tools robot_precheck), `arm` (processes zenohd, arm, arm_stock; tools arm_controllers, leader_echo, check_arm_state, check_arm_action; recorder_stream [arm_state, arm_action]; events: `Multi-turn|0xc` bad "팔 모터 Multi-turn 오류"), `leap` (설계 5.1 의 블록 그대로 + usb_id `0403:6014`, checks leap_port, processes leap_manus, leap_leader, tools leap_check, leap_zero, check_hand), `glove` (checks manus_core_off, manus_dongle; processes manus; tools leap_glovecal, manus_hz, check_glove; recorder_stream glove), `tactile` (checks paxini_port; tools check_tactile_a; recorder_stream tactile_a; usb_id 는 현장 확인 주석), `cam_wrist` (checks realsense_usb; processes camera_ros; tools check_cam_wrist; recorder_stream cam_wrist), `cam_ext` (checks cam_ext_usb 새 점검 `usb: "8086:0b3a"` 현장 확인 주석; recorder_stream cam_ext). `leap_port` 를 `serial: /dev/ttyUSB0` 으로, `paxini_port` 를 `serial: /dev/ttyACM*` 로, `realsense_usb` 를 `usb: "8086:0b5b"` + `warn_below_mbps: 5000` 으로, `manus_dongle` 은 `command` 그대로(현장 확인). `known_usb`: `0403:6014: "FTDI (LEAP?)"`, `0403:6001: "FTDI"`, `8086:0b5b: "RealSense D405"`, `8086:0b3a: "RealSense D435i"`, Manus 동글 id(70-manus-hid.rules 에서 복사). `recorder` 프로세스는 어느 장치에도 넣지 않는다(홈 프로세스 줄과 "기타"에 보인다).
- [ ] **Step 2: `hub.fake.yaml`** — 같은 장치 7개를 가짜로. `fake_leap` 프로세스: 3초 뒤 `Missing or unresponsive DYNAMIXEL IDs: [7]` 한 줄, 이후 10초마다 `[leap] feedback read failed: ...` 한 줄, 계속 돈다. `fake_leap_check` 도구: 설계 5.2 형식의 정상 출력(16개, 온도 30~41) 을 `printf` 로. `chains` 삭제.
- [ ] **Step 3: 사용법** — `control_hub_usage.md` 에 홈·장치·탐색·로그 화면 설명, 세션·사고 폴더 위치와 내용, 현장 확인 항목(설계 9장 마지막 단락 그대로).
- [ ] **Step 4: 확인** — `.venv/bin/control-hub validate --config config/hub.example.yaml` 와 `hub.fake.yaml` 둘 다 통과, `.venv/bin/pytest -q` PASS
- [ ] **Step 5: 커밋** — `feat(control-hub): v2 configs and usage doc`

---

### Task 12: 텔레옵 — 삼킨 읽기 실패를 로그에 한 줄

**Files:**
- Modify: `user_pc/src/leap_teleop/hand/leap_driver.py:30-35`
- Test: `user_pc/tests/test_drivers.py`

**Interfaces:**
- Produces: `LeapHandDriver(controller, log=print, clock=time.monotonic)`. `read_feedback()` 은 지금처럼 실패 시 `None`. 실패하면 `log(f"[leap] feedback read failed: {error}")`, 같은 함수로 1초 안의 다음 실패는 찍지 않는다. 그 밖 동작·호출 순서는 그대로.

- [ ] **Step 1: 실패하는 시험**

```python
def test_feedback_failure_is_logged_once_per_second():
    lines, t = [], [0.0]
    drv = LeapHandDriver(FailingController(), log=lines.append, clock=lambda: t[0])
    assert drv.read_feedback() is None and drv.read_feedback() is None
    t[0] = 1.01; drv.read_feedback()
    assert lines == ["[leap] feedback read failed: feedback sync read failed for ID None: x"] * 2
def test_feedback_success_logs_nothing(): ...
```
- [ ] **Step 2: 실패 확인** — `cd user_pc && python3 -m pytest tests/test_drivers.py -q` (이 패키지의 기존 시험 실행 방식을 따른다) → FAIL
- [ ] **Step 3: 구현** — `LeapHandDriver` 를 만드는 곳(cli)은 바꾸지 않는다 (기본값 `print`).
- [ ] **Step 4: 통과 확인** — `user_pc` 시험 전체 PASS
- [ ] **Step 5: 커밋 (따로)** — `feat(leap_teleop): log swallowed feedback read failures (rate-limited)`

---

## 자체 점검 메모

- 설계의 `line`(로그 줄 번호)은 `offset`(그 줄을 읽은 덩어리의 시작 바이트)으로 바꿨다. 로그 API 가 이미 offset 으로 읽고, 줄 번호는 256 KB 건너뛰기 때문에 틀릴 수 있다.
- 사고의 "다른 프로세스 직전 60초"는 로그에 시각이 없어 "직전 100줄"로 했다.
