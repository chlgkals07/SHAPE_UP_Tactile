# Control Hub 설계

작성 2026-11-14. 상태: 승인 대기.

## 1. 왜 만드는가

데이터 수집 한 번에 터미널을 6~8개 열고 가이드(`docs/manus_teleop_guide.html`)의 명령을 순서대로 복붙해야 한다. 셸마다 환경(ROS, zenoh, venv)이 달라서 자주 틀린다. 이것을 브라우저 한 화면에서 켜고, 끄고, 상태와 로그를 보는 프로그램으로 바꾼다.

조건 두 가지가 설계를 정한다.

- 녹화기(`recorder/`)는 아직 실물 검증 전이고 launch와 명령도 더 바뀐다. 그래서 녹화기와 합치지 않고, 명령은 파일 하나만 고치면 바뀌게 한다.
- 11월 17일 전에 현장에서 써야 한다. hub 자체도 실물 검증 없이 나가므로, hub가 틀려도 로봇이 영향받지 않아야 한다.

## 2. 목표와 범위

**목표**

- 가이드의 실행 명령(Robot PC, User PC 모두)을 버튼으로 켜고 끈다.
- 프로세스별 상태(꺼짐, 켜는 중, 준비됨, 끝남, 오류)와 로그를 한 화면에서 본다.
- 장치와 연결 상태(로봇 ping, zenoh 포트, LEAP 포트 등)를 한눈에 본다.
- 명령, 환경, 순서가 바뀌면 YAML 파일 하나만 고친다. 코드는 건드리지 않는다.
- 키 입력이 필요한 도구(LEAP 영점 기록, `leap_glovecal`)도 화면에서 돌린다.

**하지 않는 것 (이번 범위 밖)**

- 녹화기와의 통합. 녹화기는 hub가 켜는 프로세스 하나이고, 떠 있으면 "녹화기 열기" 링크만 보인다.
- Manus SDK 캘리브레이션(`sdk_client.py`). 별도 Dashboard에서 한다.
- 브라우저에서 YAML 편집, 로그인, 여러 사용자 동시 조작.
- 전부 한 번에 자동으로 켜기. 5V 투입이나 leader 잡기처럼 사람이 해야 하는 단계가 사이에 있어서 한 단계씩 누른다.

**이렇게 되면 실패**

- hub가 죽거나 재시작했을 때 팔이나 손이 같이 꺼진다.
- 브라우저에서 임의의 명령을 실행할 수 있다.
- 명령 하나 바꾸는 데 Python이나 JS를 고쳐야 한다.
- UI가 말썽일 때 지금 방식(터미널)으로 돌아갈 수 없다.

## 3. 접근 방식

| | 방식 | 장점 | 단점 |
|---|---|---|---|
| A | hub가 직접 자식 프로세스로 실행 | 상태와 종료 코드가 정확, 의존성 없음 | hub가 죽으면 팔과 손이 같이 죽는다 |
| **B** | **tmux가 프로세스를 붙들고 hub는 리모컨** | hub 재시작과 무관, `tmux attach`로 언제든 터미널로 복귀, 끄기가 가이드와 같은 Ctrl+C | 상태를 tmux에 물어서 알아낸다 |
| C | systemd, supervisor, process-compose | 코드가 적다 | 원격 컨테이너 실행, 확인 창, 충돌 관계, 녹화기와 같은 디자인을 얹기 어렵다 |

**B로 정했다 (11/14 하민).** hub, 녹화기, launch가 모두 미검증이라 hub가 틀려도 로봇에 영향이 없는 쪽을 골랐다.

## 4. 구조

### 4.1 폴더

```text
control_hub/                      # recorder/, user_pc/ 와 같은 층. 서로 import 하지 않는다
  pyproject.toml                  # 의존성: PyYAML, fastapi, uvicorn. 명령: control-hub
  README.md
  config/
    hub.example.yaml              # 실제 장비용. 복사해서 hub.yaml 로 쓴다 (gitignore)
    hub.fake.yaml                 # sleep, echo 만 쓰는 가짜 구성. 실물 없이 UI 전체를 돌린다
  src/control_hub/
    config.py                     # YAML 읽기와 검증 -> 데이터 클래스. 틀린 키는 바로 오류
    command.py                    # (프로세스, 환경, 실행 위치) -> 셸 명령 한 줄. 순수 함수
    tmux.py                       # tmux 를 부르는 유일한 파일
    supervisor.py                 # 켜기, 끄기, 상태, 입력 보내기. 선행 조건과 충돌 검사
    checks.py                     # 상태 점검 (ping, TCP 포트, 파일, pgrep, 명령)
    server.py                     # FastAPI. 얇은 층: 모든 동작은 supervisor 메서드
    cli.py                        # control-hub serve | status | validate
    static/                       # index.html, app.js, style.css (녹화기와 같은 색과 글꼴)
  tests/
docs/data_preparation/control_hub_usage.md
```

파일별 책임은 하나씩이다. 명령이 바뀌면 `hub.yaml`, tmux 다루는 법이 바뀌면 `tmux.py`, 원격 실행 방식이 바뀌면 `command.py`만 고친다.

### 4.2 tmux를 쓰는 방식

- 전용 소켓(`tmux -L shapeup`)과 세션 하나(`hub`)를 쓴다. 사용자의 다른 tmux와 섞이지 않는다.
- 프로세스 하나가 창 하나이고 창 이름이 프로세스 id다. hub가 다시 뜨면 창 이름으로 이미 도는 프로세스를 그대로 인식한다.
- `remain-on-exit`를 켜서 끝난 프로세스의 종료 코드를 읽는다 (`pane_dead`, `pane_dead_status`).
- 로그는 `pipe-pane`으로 파일에 쓴다 (`~/.local/state/control_hub/logs/<id>/<시작 시각>.log`). hub는 그 파일을 따라 읽어 브라우저로 보낸다. hub가 꺼져 있던 동안의 로그도 남는다.
- 끄기는 Ctrl+C 전송이다. 프로세스별 대기 시간(기본 10초) 안에 안 끝나면 화면에 "강제 종료" 버튼이 나온다. 자동으로 강제 종료하지 않는다.
- 입력은 그 창에 글자와 Enter를 보낸다. `input: true`인 프로세스에만 허용한다.
- 터미널로 돌아가기: `tmux -L shapeup attach`. 화면에도 이 명령을 적어 둔다.

### 4.3 실행 위치

| `host` | 실제로 창에서 도는 것 |
|---|---|
| `local` | `bash -lc '<환경 준비>; <명령>'` |
| `robot` | `ssh -tt root@<로봇> '<환경 준비>; <명령>'` |
| `robot_container` | `ssh -tt root@<로봇> docker exec -it <컨테이너> bash -lc '<환경 준비>; <명령>'` |

- Robot PC 프로세스도 User PC의 tmux 창에서 ssh로 돈다. Robot PC에는 아무것도 설치하지 않는다.
- 이더넷이 끊기면 ssh가 끊기고 원격 프로세스도 끝난다. 지금 ssh 터미널로 띄울 때와 같은 동작이다.
- 컨테이너 이름과 `docker exec` 진입이 `container.sh enter`와 같은 환경을 주는지는 **현장 확인 항목**이다. 다르면 YAML의 환경 준비 줄만 고친다.

### 4.4 설정 파일

```yaml
hosts:
  robot: {ssh: root@omy-snpr44b1050.local, container: open_manipulator}

envs:                       # 이름 붙인 환경 준비 줄. 프로세스가 이름으로 고른다
  teleop:                   # Humble, zenoh 끔 (3, 4단계)
    - export LEAP_NO_ZENOH=1
    - source {repo}/user_pc/scripts/leap_aliases.sh && leap_env
  recorder:
    - cd {repo}/recorder && source .venv/bin/activate
  robot_ros:
    - source /opt/ros/jazzy/setup.bash
    - export ROS_DOMAIN_ID=30 RMW_IMPLEMENTATION=rmw_zenoh_cpp
    - source /workspace/omy_ws/install/setup.bash

processes:
  zenohd:
    title: zenoh 라우터
    group: Robot PC
    kind: service           # service: 계속 도는 것 / tool: 한 번 돌고 끝나는 것
    host: robot_container
    env: robot_ros
    cmd: ros2 run rmw_zenoh_cpp rmw_zenohd
    ready: {check: zenoh_port}

  arm:
    title: 팔 bringup (omy_ai_wrist_flip)
    group: Robot PC
    kind: service
    host: robot_container
    env: robot_ros
    cmd: ros2 launch omy_leap_bringup omy_ai_wrist_flip.launch.py
    requires: [zenohd]
    conflicts: [pack, unpack]
    ready: {log: "leader.*(started|sync)"}
    confirm_start:
      - 작업 공간을 비웠다. 누르는 즉시 팔이 움직인다 (home -> ready, 약 20초)
      - LEAP 은 주먹 상태다
      - leader 트리거를 쥐고 있다
    confirm_stop:
      - 팔을 손으로 받치고 있다

  leap_manus:
    title: Manus -> LEAP 텔레옵
    group: User PC
    kind: service
    host: local
    env: teleop
    cmd: leap_manus --record-udp
    flags:
      - {id: dry_run, label: dry-run (LEAP 을 건드리지 않음), arg: --dry-run, default: true}
    requires: [manus]
    ready: {log: "\\[teleop\\] live"}

  leap_zero:
    title: LEAP 영점 기록
    group: 도구
    kind: tool
    host: local
    env: teleop
    cmd: python3 -m leap_teleop.tools.calibrate_motors
    input: true
    conflicts: [leap_manus]

checks:
  robot_ping: {title: 로봇 ping, ping: 10.42.0.241}
  zenoh_port: {title: zenoh :7447, tcp: "10.42.0.241:7447"}
  leap_port:  {title: LEAP USB, file: /dev/ttyUSB0}
  manus_core: {title: MANUS Dashboard 꺼짐, no_process: MANUS_Core}
  recorder_ui: {title: 녹화기 UI, http: "http://127.0.0.1:8800", link: 녹화기 열기}

profiles:                   # 화면에 순서대로 보이는 실행표. note 는 사람이 하는 단계
  - id: hand_only
    title: 손만 (Manus 단독)
    steps: [{note: LEAP 5V 를 편 손으로 켠다}, manus, leap_check, leap_manus]
  - id: collect
    title: 수집 (팔 + 손 + 녹화)
    steps: [{note: LEAP 5V 를 편 손으로 켠다}, manus, zenohd, arm, leap_manus, recorder]
```

- `{repo}`는 레포 루트로 치환된다.
- 첫 구성에 넣는 프로세스: `zenohd`, `arm`(wrist_flip), `arm_stock`(순정 `omy_ai`), `pack`, `unpack`, `manus`, `leap_manus`, `leap_leader`, `leap_check`, `leap_zero`, `leap_glovecal`, `camera_ros`(녹화기와 충돌), `recorder`, `recorder_fake`, 그리고 `tactile-rec check <스트림>` 도구들.
- 검증: 모르는 키, 없는 id를 가리키는 `requires`/`conflicts`/`steps`, 없는 `env`나 `host`는 시작할 때 오류다. `control-hub validate`로 미리 볼 수 있다.
- 화면의 "설정 다시 읽기"로 hub를 끄지 않고 다시 읽는다. 틀렸으면 오류를 보여 주고 이전 설정을 유지한다. 도는 프로세스는 건드리지 않고, 시작할 때의 명령과 지금 설정이 다르면 "설정이 바뀜, 다시 켜야 적용"이라고 표시한다.

### 4.5 켜고 끌 때의 규칙

- `requires`의 프로세스가 준비 상태가 아니면 켜지지 않고 이유가 나온다.
- `conflicts`의 프로세스가 돌고 있으면 켜지지 않는다 (카메라 ROS 노드와 녹화기, `arm`과 pack/unpack, 영점 기록과 텔레옵).
- `confirm_start`/`confirm_stop`이 있으면 항목을 모두 체크해야 버튼이 눌린다.
- `ready`가 없으면 떠 있는 것만으로 준비로 본다. `log` 정규식이나 `check` id를 주면 그것이 만족될 때 준비다.
- 다른 프로세스가 `requires`로 기대고 있는 것을 끄려 하면 경고하고 한 번 더 묻는다.

### 4.6 API

브라우저가 보낼 수 있는 것은 id뿐이다. 명령 문자열은 받지 않는다.

- `GET /api/describe`: 설정에서 온 프로세스, 점검, 실행표 목록
- `WS /ws`: 1초마다 상태와 점검 결과, 로그 줄
- `POST /api/process/{id}/start` (본문: 켠 flag id 목록, 확인했다는 표시), `/stop`, `/kill`, `/input` (본문: 한 줄), `/clear` (끝난 창 닫기)
- `GET /api/process/{id}/log?tail=N`
- `POST /api/reload`

기본은 `127.0.0.1:8700`이다. 로그인이 없으므로 `--host 0.0.0.0`은 믿을 수 있는 네트워크에서만 쓴다 (녹화기와 같은 규칙).

## 5. 화면

녹화기와 같은 틀이다: 왼쪽 메뉴, 흰 바탕, 색은 상태에만 쓴다.

```text
┌──────────────┬───────────────────────────────────────────────────────────────┐
│ Control Hub  │ 실행표 [ 수집 (팔+손+녹화) ▾ ]                    설정 다시 읽기 │
│              ├───────────────────────────────┬───────────────────────────────┤
│ ■ 실행       │ 1 ☐ LEAP 5V 를 편 손으로 켠다  │ 팔 bringup          ● 준비됨   │
│   도구       │ 2 ● Manus 노드      준비됨 [끄기]│ ssh root@omy… docker exec …   │
│   상태       │ 3 ● zenoh 라우터    준비됨 [끄기]│ ┌───────────────────────────┐ │
│   로그       │ 4 ◐ 팔 bringup     켜는 중 [끄기]│ │ [follower] controllers ok │ │
│              │ 5 ○ Manus→LEAP           [켜기]│ │ [executor] home -> ready  │ │
│              │     ☑ dry-run                 │ │ ...                       │ │
│ ● 로봇 ping  │ 6 ○ 녹화기                [켜기]│ └───────────────────────────┘ │
│ ● zenoh      │                               │ 입력 [____________] [보내기]   │
│ ● LEAP USB   │ 전체 끄기 (역순)               │                               │
│ ○ 녹화기 UI  │                               │ tmux -L shapeup attach        │
└──────────────┴───────────────────────────────┴───────────────────────────────┘
```

- **실행**: 고른 실행표의 단계를 순서대로 보여 준다. 줄을 누르면 오른쪽에 그 프로세스의 실제 명령과 로그가 나온다. "전체 끄기"는 역순으로 하나씩 끄고, 확인 항목이 있는 것에서 멈춰 묻는다.
- **도구**: `kind: tool` 목록. 돌리고 결과(종료 코드, 로그)를 본다. 입력 줄이 여기서 쓰인다.
- **상태**: 점검 전체와 프로세스 전체 표.
- **로그**: 프로세스를 골라 지난 실행의 로그 파일을 본다.
- 왼쪽 아래에 핵심 점검 몇 개가 항상 보인다.

## 6. 테스트

- `config.py`, `command.py`: 순수 함수라 단위 테스트로 전부 덮는다 (검증 오류, 세 실행 위치의 명령 문자열, 따옴표 처리).
- `supervisor.py`: 실제 tmux를 임시 소켓으로 띄워 `sleep`, `echo`, `read` 스크립트로 시험한다. 켜기, 준비 판정, Ctrl+C 종료, 종료 코드, 입력, hub 재시작 후 다시 인식, 충돌과 선행 조건 거부.
- `server.py`: httpx로 API 시험. 모르는 id와 입력이 허용되지 않은 프로세스에 대한 입력은 거부.
- `hub.fake.yaml`로 실물 없이 화면 전체를 눌러 본다.
- 실물 확인은 현장 체크리스트로 `control_hub_usage.md`에 적는다: ssh와 `docker exec` 환경, 원격 Ctrl+C가 launch까지 전달되는지, `ready` 정규식이 실제 로그와 맞는지.

## 7. 내가 정한 것 (바꿀 수 있다)

- 폴더 이름은 `control_hub/`. 녹화기 안에 이미 `hub.py`(스트림 묶음)가 있어서 `hub`만 쓰면 헷갈린다.
- 포트 8700, 전용 tmux 소켓 `shapeup`.
- 스타일은 녹화기 `style.css`의 색과 글꼴 값을 복사한다. 파일을 공유하지 않는다 (지금은 서로 묶지 않기 위해).
- "전부 켜기" 버튼은 없다. 한 단계씩 켠다.
- 자동 재시작은 없다. 죽으면 "오류"로 보이고 사람이 다시 켠다.
- LEAP 캘리브레이션은 영점 기록(`calibrate_motors`)과 `leap_glovecal` 둘 다 도구로 넣는다.
- 가이드 HTML은 이번에 고치지 않는다. hub 사용법은 새 md 한 장으로 쓴다.

## 8. 구현하면서 달라진 것 (11/14)

승인 뒤 "끊긴 곳과 오류를 볼 수 있는 올인원 UI"라는 목표에 맞춰 더하거나 바꾼 것이다.

- **사슬(`chains`) 추가.** 점검과 프로세스를 신호가 흐르는 순서로 늘어놓고, 처음 막힌 곳을 "여기서 끊김"으로 보여 준다. 왼쪽 메뉴 아래에 항상 보인다.
- **힌트(`hints`) 추가.** 로그 줄에 맞는 정규식이 있으면 조치 문구를 같이 보여 준다. 가이드의 문제 해결 표를 옮겼다. `ignore: true` 는 알려진 무해한 줄을 문제 목록에서 뺀다.
- **`requires` 에 점검 id 도 쓸 수 있다.** zenohd 가 컨테이너에서 이미 떠 있는 경우가 있어, 팔 bringup 은 "zenoh 라우터 프로세스"가 아니라 "zenoh :7447 점검"을 선행 조건으로 둔다.
- **`flags`.** `--dry-run` 처럼 켤 때 고르는 옵션. 확인 항목은 `unless_flag` 로 dry-run 일 때 생략할 수 있다.
- **실행 위치는 `hosts` 의 이름으로.** `host: robot` / `host: robot_container` 는 예약어가 아니라 `hosts` 에 정의한 이름이다. `container` 가 있으면 `docker exec` 를 거친다.
- **메뉴는 실행 / 전체 / 연결.** 도구는 "전체"에, 지난 로그는 상세 화면의 선택 상자에 넣었다.
- **WebSocket 대신 1초 폴링.** `GET /api/state` 와 `GET /api/process/{id}/log?offset=`. 로컬에서 쓰기에 충분하고 끊김 처리가 단순하다.
- **종료 코드는 실행 스크립트가 직접 파일에 남긴다.** tmux 는 바로 끝나는 프로세스의 종료 코드를 놓칠 때가 있었다.
- **로그 첫 줄(실행한 명령)은 준비 판정과 오류 탐지에서 뺀다.** 명령 문자열에 든 단어가 출력으로 오인되지 않게.

## 9. 만드는 사람에게 남기는 것

- `ready`의 로그 정규식은 추정이다. 실제 로그를 보고 YAML에서 맞춘다.
- `hub.example.yaml`의 나머지 프로세스 항목은 가이드의 명령을 그대로 옮긴다.
- JS의 세부 구성과 화면 문구.
