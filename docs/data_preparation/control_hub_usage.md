# Control Hub 사용법

`control_hub/` 는 가이드(`docs/manus_teleop_guide.html`)의 명령을 브라우저 한 화면에서 켜고, 끄고, 상태와 로그를 보는 프로그램이다.
터미널 여러 개에 명령을 복붙하던 것을 대신한다. 설계는 [`2026-11-14-control-hub-design.md`](../superpowers/specs/2026-11-14-control-hub-design.md) (프로세스·실행표), [`2026-11-15-control-hub-devices-design.md`](../superpowers/specs/2026-11-15-control-hub-devices-design.md) (홈·장치·탐색·로그) 에 있다.

녹화기와 함께 본 전체 구조, 버튼별 실제 명령, 실물 시험 순서는 [`control_hub_and_recorder_overview.html`](control_hub_and_recorder_overview.html) 에 있다.

실물로 확인하지 않은 부분에는 **[현장 미검증]** 표시가 있다. 5절이 그 확인 절차다.

## 1. 어떻게 동작하나

- 프로세스는 hub 가 아니라 **tmux** 가 붙들고 있다. hub 는 창을 만들고, Ctrl+C 를 보내고, 로그를 읽는 리모컨이다.
- 그래서 hub 를 끄거나 고치느라 재시작해도 팔, 손, Manus 는 계속 돈다. 다시 띄우면 도는 것을 그대로 인식한다.
- 화면이 말썽이면 언제든 터미널로 돌아간다.

  ```bash
  tmux -L shapeup attach -t hub      # Ctrl+b w 로 창 선택, Ctrl+b d 로 빠져나오기
  ```

- Robot PC 의 프로세스도 User PC 의 tmux 창에서 `ssh -tt ... docker exec -it ...` 로 돈다. Robot PC 에는 아무것도 설치하지 않는다. 이더넷이 끊기면 원격 프로세스도 끝난다 (지금 ssh 터미널로 띄울 때와 같다).

## 2. 설치

User PC 에서 한 번.

```bash
sudo apt install tmux
cd ~/SHAPE_UP_Tactile/control_hub
python3 -m venv .venv && source .venv/bin/activate     # venv 가 없으면: uv venv .venv
pip install -e .
cp config/hub.example.yaml config/hub.yaml             # hub.yaml 은 git 에 올라가지 않는다
control-hub validate --config config/hub.yaml
```

Robot PC 에 비밀번호 없이 ssh 가 되어야 한다 (`ssh root@10.42.0.241` 로 확인).

## 3. 실물 없이 돌려 보기

모든 프로세스가 `echo` 와 `sleep` 인 설정이 들어 있다. 화면의 모든 동작을 눌러 볼 수 있다.

```bash
control-hub serve --config config/hub.fake.yaml        # http://localhost:8701
```

- **전체 → 가짜 로봇 전원 켜기** 를 실행하면 "로봇 ping" 점검이 통과하고 zenoh 라우터를 켤 수 있게 된다.
- **오류 연습** 실행표: 오류로 끝나는 프로세스, Ctrl+C 를 무시하는 프로세스, 입력을 받는 도구가 있다.
- **Manus → LEAP 텔레옵(가짜)** 을 켜면 3초 뒤 "모터 응답 없음: 7" 이 나고 LEAP 칸이 빨개지며 사고 폴더가 생긴다. 끈 뒤 **LEAP 모터 확인(가짜)** 을 실행하면 모터 표가 채워진다 (7번 오류 비트).
- 가짜 세션·사고는 `~/.local/state/control_hub/fake-sessions/` 에 따로 쌓인다.
- 끝나면 `tmux -L shapeup-fake kill-server` 로 가짜 프로세스를 모두 지운다.

## 4. 쓰는 법

```bash
cd ~/SHAPE_UP_Tactile/control_hub && source .venv/bin/activate
control-hub serve --config config/hub.yaml             # http://localhost:8700
```

**ROS 를 source 하지 않은 새 터미널에서 띄운다.** tmux 서버는 처음 띄운 셸의 환경을 물려받는다. 환경이 꼬였다고 의심되면 전부 끈 뒤 `tmux -L shapeup kill-server` 하고 hub 를 다시 띄운다.

### 화면

| 메뉴 | 내용 |
|---|---|
| **홈** | 장치 7칸(로봇 PC, 팔, LEAP, 글러브, 촉각, 손목 카메라, 외부 카메라)의 상태, 켜진 프로세스, 최근 문제. 문제 줄 옆 버튼으로 그 장치의 확인 도구(`leap_check` 등)를 바로 돌린다 |
| **장치 / 각 장치** | 연결 정보(경로, by-id, 시리얼, USB 속도, latency timer, ping 지연), 관련 프로세스와 도구, 마지막 확인 결과, 이 장치의 기록. LEAP 은 모터 16개 표 (손가락 × 관절) |
| **장치 탐색** | 지금 꽂힌 USB 장치 목록과 설정과 다른 곳에 꽂힌 것 경고. 보여 주기만 한다 (포트 자동 지정은 추후) |
| **실행표** | 실행표(수집, 팔 + 손, 손만, leader 트리거, 센서 확인)를 고르면 단계가 순서대로 나온다. 위에서부터 하나씩 켠다. 체크박스 줄은 사람이 직접 하는 단계다 (5V 투입 등) |
| **녹화** | 녹화기(`tactile-rec`)의 화면을 hub 안에 그대로 띄운다. 녹화기가 꺼져 있으면 켜는 버튼으로 안내한다. 주소는 `checks` 에서 `link` 가 있는 http 점검의 것이고, `127.0.0.1` 이면 hub 를 연 호스트 이름으로 바꿔 연다 (태블릿에서 쓰려면 녹화기도 `--host 0.0.0.0`). 녹화기의 키(Space 등)는 그 화면 안을 한 번 누른 뒤에 듣는다 |
| **로그** | 세션별 사건 기록과 사고 폴더. 장치·수준으로 거른다. 사건을 누르면 그 실행의 로그가, 사고를 누르면 모아 둔 파일이 열린다 |
| **전체** | 실행표와 무관하게 모든 프로세스와 도구. 캘리브레이션, pack / unpack, 확인 도구가 여기 있다 |

- 오른쪽 띠에 모든 점검(ping 지연, 포트, USB)이 항상 보인다. 창이 좁으면 위로 올라간다.
- 카메라 영상은 hub 에 없다. 장치 상세에 정보만 나오고 영상은 녹화기 화면에서 본다.
- 실행표·전체에서 줄을 누르면 오른쪽에 설명, 실제 실행되는 명령, 로그가 나온다.
- 상태: **꺼짐**, **켜는 중**(떴지만 준비 조건을 아직 못 봄), **준비됨**, **끄는 중**, **끝남**(도구가 정상 종료), **오류**(예상 밖 종료).
- 켤 수 없을 때는 버튼이 흐려지고 이유가 줄 아래에 나온다 ("먼저 필요: zenoh :7447").
- 팔 bringup 처럼 위험한 것은 확인 항목을 모두 체크해야 켜진다. 끌 때도 묻는다 ("팔을 손으로 받치고 있다").

### 오류를 볼 때

- 오류로 끝난 프로세스는 화면 맨 위에 빨간 띠로 뜨고, **전체** 메뉴에 개수가 붙는다.
- 상세 화면의 "로그에서 찾은 문제"에 오류 줄과 조치(가이드의 문제 해결 표)가 같이 나온다.
- 로그 창에서 오류 줄은 붉게 보인다. 위의 선택 상자로 지난 실행의 로그도 본다 (프로세스당 30개 보관, `~/.local/state/control_hub/logs/`).
- hub 자체가 죽으면 왼쪽 아래가 "hub 와 끊김"이 된다. 프로세스는 계속 돌고 있으니 hub 만 다시 띄운다.

### 기록: 세션과 사고 폴더

브라우저를 열지 않아도 hub 가 1초마다 상태를 보고 바뀐 것을 적는다. 제어 주기에는 끼어들지 않는다 (로그 파일과 sysfs 를 읽기만 한다).

```
~/.local/state/control_hub/sessions/<YYYY-MM-DD_HHMMSS>/     hub 를 켤 때마다, 또는 로그 화면의 "새 세션"
    events.jsonl        사건 한 줄씩: 점검 끊김/복구, 프로세스 켜짐/오류, 로그의 오류 줄, USB 꽂음/뺌
    runs.json           이 세션에 돈 프로세스 로그 위치
    incidents/<HHMMSS>_<장치>_<내용>/     오류 하나마다
        summary.md      무엇이, 언제, 어디서, 힌트, 그때 돌던 프로세스
        checks.json     그 순간의 모든 점검 결과와 USB 목록
        <pid>.log       오류 낸 프로세스: 직전 200줄 + 직후 30초
        others/*.log    같이 돌던 프로세스: 직전 100줄 + 직후 30초
        leap_check.txt  5분 안에 그 장치의 확인 도구를 돌렸으면 그 출력
```

- 같은 장치에서 30초 안에 난 오류는 한 폴더에 모인다 (횟수와 "같이 난 오류"가 늘어난다).
- 세션은 30개까지 보관한다. 로그 화면에서 세션 또는 사고 하나를 zip 으로 받는다.
- LEAP 모터가 빠지면: 홈의 LEAP 칸이 "모터 응답 없음: 7" 처럼 번호를 보여 준다. 텔레옵을 끄고 **LEAP 모터 확인**을 돌리면 모터 표에 응답, 온도, 전압, 오류 비트가 나오고 그 출력이 사고 폴더에 붙는다. 번호를 모르는 읽기 실패(`[leap] feedback read failed`)는 주의로 남는다.

### 끄기

- **끄기**는 Ctrl+C 를 보낸다. 가이드의 종료 방식과 같다 (`leap_*` 는 Torque OFF).
- 정해진 시간(기본 10초) 안에 안 끝나면 **강제 종료**가 나온다. 자동으로 강제 종료하지 않는다. 강제 종료는 정리 동작 없이 창을 닫는다.
- **전체 끄기**는 켠 순서의 역순으로 하나씩 끈다. 하나가 안 꺼지면 거기서 멈춘다.
- 마지막에 LEAP 5V 를 끈다 (hub 가 할 수 없는 단계).

### 입력이 필요한 도구

`LEAP 영점 기록`, `글러브 편 손/주먹 기록`은 로그 아래 입력 줄이 생긴다. 글자를 쳐서 **보내기**를 누르면 그 줄과 Enter 가 전달된다. 비워 두고 누르면 Enter 만 간다.
Manus SDK 캘리브레이션(`.mcal`)은 hub 에 없다. 별도 Dashboard 에서 한다.

## 5. 현장 확인 체크리스트 **[현장 미검증]**

hub 는 가짜 설정과 자동 시험으로만 확인했다. 실물에서 아래를 순서대로 본다. 전부 `hub.yaml` 만 고쳐서 맞춘다.

| 순서 | 볼 것 | 다르면 |
|---|---|---|
| 1 | 오른쪽 띠에서 로봇 ping, 로봇 ssh 가 정상 | `hosts.*.ssh`, `checks.robot_ping` 의 주소 |
| 2 | **전체 → 로봇 중복 실행 확인**이 `ros2 node list` 까지 출력 | 컨테이너 이름(`hosts.robot_container.container`), `envs.robot_ros` 의 source 줄. Robot PC 에서 `docker ps` 로 이름을 본다 |
| 3 | zenoh 라우터를 켜면 "zenoh :7447" 이 정상, **끄기**로 실제로 꺼짐 | ssh 를 거친 Ctrl+C 가 안 닿으면 `tmux attach` 로 확인하고 알려 준다 |
| 4 | 팔 bringup 이 leader 동기화 뒤 "준비됨"이 됨 | `processes.arm.ready.log` 를 leader 가 시작될 때 실제로 찍히는 문구로 바꾼다. 안 맞으면 계속 "켜는 중"이다 (동작에는 영향 없음) |
| 5 | 팔 bringup 을 **끄기** 했을 때 follower / leader 가 모두 끝남 | `stop_grace_s` 를 늘린다 |
| 6 | Manus 노드가 "준비됨" (`integrated mode`) | `processes.manus.ready.log` |
| 7 | Manus 동글, 손목 카메라 USB 점검이 꽂았을 때만 정상 | `lsusb` 로 id 를 보고 `checks.manus_dongle`, `checks.realsense_usb` 의 id 를 고친다 |
| 8 | `leap_manus` dry-run 이 `[teleop] live` 에서 "준비됨" | `ready.log` |
| 9 | 녹화기를 켜면 "녹화기 UI" 가 정상이고 링크가 열림 | 포트(`checks.recorder_ui`) |
| 10 | LEAP 모터가 빠졌을 때 홈의 LEAP 칸에 모터 번호가 뜨고 사고 폴더가 생김 | 실제로 찍힌 줄을 보고 `devices.leap.events` 의 정규식을 맞춘다 |
| 11 | **장치 탐색**에 LEAP, Paxini 보드 두 개, 카메라 두 대, Manus 동글이 각각 구분되어 보임. 특히 Paxini 두 보드의 시리얼 번호가 서로 다른지 | 이름이 안 붙으면 `known_usb` 에 id 를 더한다. 구분이 되면 포트 자동 지정(추후)의 근거가 된다 |
| 12 | LEAP 상세의 USB 속도, latency timer 가 맞게 나옴 (latency timer 1 이 정상) | 16 이면 경고가 뜬다. udev 규칙으로 1 로 맞춘다 |
| 13 | 손목 카메라가 USB3 (5000 Mbps) 로 잡힘 | 480 이면 경고가 뜬다. USB3 포트·케이블로 바꾼다 |
| 14 | 녹화기를 켠 채 촉각 보드 USB 를 뽑으면 촉각 칸이 빨강이 되고 "녹화기 tactile_a: 오류/끊김" 이 뜸. 다시 꽂으면 풀림 | `devices.tactile.recorder_stream` 의 이름이 `rig.yaml` 의 스트림 이름과 같은지 |
| 15 | 녹화기가 켜진 동안 "스트림 확인" 도구가 막히고, 도구가 켜진 동안 녹화기가 막힘 | `processes.recorder.conflicts` |

결과는 `docs/field-test/YYYY-MM-DD-results.md` 에 적는다.

## 6. 명령이 바뀌었을 때

`config/hub.yaml` 만 고치고 화면 왼쪽 아래 **설정 다시 읽기**를 누른다. hub 를 끌 필요가 없다.

- 파일이 틀렸으면 화면 맨 위에 어디가 틀렸는지 나오고, 이전 설정이 그대로 유지된다.
- 도는 프로세스는 건드리지 않는다. 명령이 바뀐 프로세스에는 "설정이 바뀜, 다시 켜야 적용"이 뜬다.
- 팀에 공유할 변경은 `hub.example.yaml` 에도 반영해서 커밋한다.

| 하고 싶은 것 | 고치는 곳 |
|---|---|
| launch 파일 이름, 옵션이 바뀜 | `processes.<id>.cmd` |
| ROS 배포판, 로봇 IP, 워크스페이스 경로 | `envs.*`, `hosts.*` |
| 새 프로세스나 도구 추가 | `processes` 에 항목 추가, 필요하면 `profiles` 의 `steps` 에 넣는다 |
| 켜기 전에 물어볼 것 | `confirm_start`, `confirm_stop` |
| 켜는 순서, 사람이 하는 단계 | `profiles.*.steps` (`{note: ...}` 가 사람 단계) |
| 같이 켜면 안 되는 것 | `conflicts` (한쪽에만 적어도 양쪽에 적용) |
| 먼저 떠 있어야 하는 것 | `requires` (프로세스 id 또는 점검 id) |
| "준비됨" 판정 | `ready: {log: 정규식}` 또는 `ready: {check: 점검 id}` |
| 자주 보는 오류에 조치 붙이기 | `hints: [{match: 정규식, hint: 조치}]`. 무시할 줄은 `{match: ..., ignore: true}` |
| 새 점검 | `checks` 에 `ping` / `tcp` / `file` / `http` / `ssh` / `usb` / `serial` / `process` / `no_process` / `command` 중 하나. `usb` 는 `warn_below_mbps` 로 느린 포트를 경고한다 |
| 장치 칸에 묶을 것 | `devices.<id>` 의 `checks` / `processes` / `tools` / `recorder_stream` |
| 녹화기 스트림을 장치에 | `devices.<id>.recorder_stream: [tactile_a, tactile_b]`. 녹화기가 그 스트림을 오류·끊김·느림·없음이라고 하면 이 장치 칸이 빨강/노랑이 되고, 녹화기가 다시 정상이라고 할 때까지 유지된다. 오류·끊김은 사건(사고 폴더)으로도 남는다 |
| 로그 줄을 사건으로 | `devices.<id>.events: [{match: 정규식, level: bad/warn/info, text: "모터 응답 없음: {motors}"}]`. `(?P<motors>...)` 로 모터 번호를 뽑는다 |
| 탐색 화면의 이름표 | `known_usb: {"vendor:product": 이름}` |

`cmd` 와 `envs` 의 줄은 그대로 셸에 들어간다. `{repo}` 는 레포 루트로 바뀐다.

## 7. 문제 해결

| 증상 | 확인 |
|---|---|
| `tmux 가 없습니다` | `sudo apt install tmux` |
| 켜자마자 "오류", 로그에 `command not found` | 그 프로세스의 `env` 줄이 빠졌거나 순서가 틀렸다. 상세의 "실행하는 명령"을 터미널에 붙여 넣어 본다 |
| Robot PC 프로세스가 켜자마자 끝남 | 오른쪽 띠의 로봇 ping, ssh 를 본다. `ssh root@10.42.0.241` 이 비밀번호를 물으면 키를 등록한다 |
| 시리얼 점검이 "권한 없음 (dialout 그룹)" | `sudo usermod -aG dialout $USER` 뒤 다시 로그인 |
| 계속 "켜는 중" | 준비 조건(상세에 나온다)이 실제 로그와 안 맞는다. 프로세스는 돌고 있다. `ready` 를 고친다 |
| 화면은 "꺼짐"인데 실제로는 돌고 있음 | hub 밖에서 띄운 것이다 (다른 터미널, 컨테이너 자동 실행). hub 는 자기가 띄운 것만 안다. 점검(포트 등)으로 확인한다 |
| 환경 변수가 이상함 (RMW 등) | hub 를 ROS 를 source 한 셸에서 띄웠다. 전부 끄고 `tmux -L shapeup kill-server` 뒤 새 터미널에서 다시 |
| 시험이 ROS 플러그인 오류로 시작도 못 함 | `env -u PYTHONPATH python -m pytest -q` |

## 8. 개발

```bash
cd control_hub
pip install -e '.[dev]'
env -u PYTHONPATH python -m pytest -q      # 실제 tmux 를 임시 소켓으로 띄워 시험한다
ruff check src tests
```

| 파일 | 하는 일 |
|---|---|
| `config.py` | YAML 읽기와 검증. 틀린 곳의 위치를 알려 준다 |
| `command.py` | 프로세스 → 창에서 실행할 한 줄 (로컬 / ssh / ssh + 컨테이너) |
| `tmux.py` | tmux 를 부르는 유일한 파일 |
| `supervisor.py` | 켜기, 끄기, 상태, 선행 조건, 충돌, 확인 |
| `logscan.py` | 로그에서 준비 문구, 오류, 장치 사건 찾기 |
| `checks.py`, `sysfs.py` | 점검 (ping, 포트, 장치). USB 정보는 sysfs 를 읽기만 한다 |
| `discovery.py` | 장치 탐색 표와 "다른 곳에 꽂힘" |
| `watcher.py` | 1초마다 바뀐 것을 사건으로 적는 백그라운드 스레드 |
| `session.py`, `incidents.py` | 세션 사건 기록과 사고 폴더 |
| `devices.py`, `leapcheck.py` | 장치 상태 계산, `leap_check` 출력 → 모터 표 |
| `server.py`, `static/` | API 와 화면. 브라우저는 id 만 보낸다. 명령 문자열은 받지 않는다 |
