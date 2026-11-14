# Control Hub 사용법

`control_hub/` 는 가이드(`docs/manus_teleop_guide.html`)의 명령을 브라우저 한 화면에서 켜고, 끄고, 상태와 로그를 보는 프로그램이다.
터미널 여러 개에 명령을 복붙하던 것을 대신한다. 설계는 [`docs/superpowers/specs/2026-11-14-control-hub-design.md`](../superpowers/specs/2026-11-14-control-hub-design.md) 에 있다.

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
| **실행** | 실행표(수집, 팔 + 손, 손만, leader 트리거, 센서 확인)를 고르면 단계가 순서대로 나온다. 위에서부터 하나씩 켠다. 체크박스 줄은 사람이 직접 하는 단계다 (5V 투입 등) |
| **전체** | 실행표와 무관하게 모든 프로세스와 도구. 캘리브레이션, pack / unpack, 확인 도구가 여기 있다 |
| **연결** | 신호가 흐르는 순서대로 점검을 늘어놓은 것. 처음 막힌 곳에 "여기서 끊김"과 조치가 나온다 |

- 왼쪽 아래에 팔 / 손 / 녹화 사슬의 상태가 항상 보인다. 빨간 줄이 지금 끊긴 곳이다.
- 줄을 누르면 오른쪽에 설명, 실제 실행되는 명령, 로그가 나온다.
- 상태: **꺼짐**, **켜는 중**(떴지만 준비 조건을 아직 못 봄), **준비됨**, **끄는 중**, **끝남**(도구가 정상 종료), **오류**(예상 밖 종료).
- 켤 수 없을 때는 버튼이 흐려지고 이유가 줄 아래에 나온다 ("먼저 필요: zenoh :7447").
- 팔 bringup 처럼 위험한 것은 확인 항목을 모두 체크해야 켜진다. 끌 때도 묻는다 ("팔을 손으로 받치고 있다").

### 오류를 볼 때

- 오류로 끝난 프로세스는 화면 맨 위에 빨간 띠로 뜨고, **전체** 메뉴에 개수가 붙는다.
- 상세 화면의 "로그에서 찾은 문제"에 오류 줄과 조치(가이드의 문제 해결 표)가 같이 나온다.
- 로그 창에서 오류 줄은 붉게 보인다. 위의 선택 상자로 지난 실행의 로그도 본다 (프로세스당 30개 보관, `~/.local/state/control_hub/logs/`).
- hub 자체가 죽으면 왼쪽 아래가 "hub 와 끊김"이 된다. 프로세스는 계속 돌고 있으니 hub 만 다시 띄운다.

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
| 1 | **연결** 페이지에서 로봇 ping, 로봇 ssh 가 정상 | `hosts.*.ssh`, `checks.robot_ping` 의 주소 |
| 2 | **전체 → 로봇 중복 실행 확인**이 `ros2 node list` 까지 출력 | 컨테이너 이름(`hosts.robot_container.container`), `envs.robot_ros` 의 source 줄. Robot PC 에서 `docker ps` 로 이름을 본다 |
| 3 | zenoh 라우터를 켜면 "zenoh :7447" 이 정상, **끄기**로 실제로 꺼짐 | ssh 를 거친 Ctrl+C 가 안 닿으면 `tmux attach` 로 확인하고 알려 준다 |
| 4 | 팔 bringup 이 leader 동기화 뒤 "준비됨"이 됨 | `processes.arm.ready.log` 를 leader 가 시작될 때 실제로 찍히는 문구로 바꾼다. 안 맞으면 계속 "켜는 중"이다 (동작에는 영향 없음) |
| 5 | 팔 bringup 을 **끄기** 했을 때 follower / leader 가 모두 끝남 | `stop_grace_s` 를 늘린다 |
| 6 | Manus 노드가 "준비됨" (`integrated mode`) | `processes.manus.ready.log` |
| 7 | Manus 동글, 손목 카메라 USB 점검이 꽂았을 때만 정상 | `lsusb` 로 id 를 보고 `checks.manus_dongle`, `checks.realsense_usb` 의 id 를 고친다 |
| 8 | `leap_manus` dry-run 이 `[teleop] live` 에서 "준비됨" | `ready.log` |
| 9 | 녹화기를 켜면 "녹화기 UI" 가 정상이고 링크가 열림 | 포트(`checks.recorder_ui`) |

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
| 새 점검 | `checks` 에 `ping` / `tcp` / `file` / `http` / `ssh` / `usb` / `process` / `no_process` / `command` 중 하나 |
| 끊긴 곳 표시의 순서 | `chains.*.items` |

`cmd` 와 `envs` 의 줄은 그대로 셸에 들어간다. `{repo}` 는 레포 루트로 바뀐다.

## 7. 문제 해결

| 증상 | 확인 |
|---|---|
| `tmux 가 없습니다` | `sudo apt install tmux` |
| 켜자마자 "오류", 로그에 `command not found` | 그 프로세스의 `env` 줄이 빠졌거나 순서가 틀렸다. 상세의 "실행하는 명령"을 터미널에 붙여 넣어 본다 |
| Robot PC 프로세스가 켜자마자 끝남 | **연결** 페이지의 ping, ssh 를 본다. `ssh root@10.42.0.241` 이 비밀번호를 물으면 키를 등록한다 |
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
| `logscan.py` | 로그에서 준비 문구와 오류 찾기 |
| `checks.py` | 점검 (ping, 포트, 장치) |
| `server.py`, `static/` | API 와 화면. 브라우저는 id 만 보낸다. 명령 문자열은 받지 않는다 |
