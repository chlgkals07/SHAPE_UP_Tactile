# OMY + LEAP (+ Manus) 시연을 Cyclo Intelligence로 기록하기

세화형의 `omy_demonstration_runbook.md`(OMY + 카메라 3대 기록)에 **LEAP Hand와 Manus 글러브를 얹는 차이만** 적은 문서다. 그 실행표의 A, B1–B6, B8–D2는 그대로 쓰고, 이 문서는 아래만 다룬다.

- 무엇이 기록되고 Cyclo가 그걸 어떻게 읽는가 (1–2절)
- 실행표에서 바뀌는 단계 (3절)
- 추가 단계 E1–E7 (4절)
- 확인할 것과 아직 모르는 것 (5–6절)

설계 근거: `../superpowers/specs/2026-10-29-ros-data-interface-design.md`. 손 구동 절차: `../../user_pc/README.md`.
상태: 코드와 config는 만들었고(2026-11-03, `--publish`), **Cyclo 컨테이너에서 녹화·변환까지는 아직 해 보지 않았다.** `[미검증]`은 실물에서 처음 확인하는 항목이다.

---

## 1. 무엇이 기록되나

Cyclo는 로봇 config에 적힌 **ROS 토픽만** rosbag2(MCAP)에 기록하고, LeRobot으로 변환한다. 그래서 LEAP 손 상태와 명령이 토픽으로 나와야 한다.

| 구분 | 토픽 | 발행 | Cyclo 역할 |
|---|---|---|---|
| 팔 state | `/joint_states` (joint1..6) | OMY follower (ROBOT PC) | `observation.state.arm` |
| 팔 action | `/leader/joint_trajectory` (joint1..6) | OMY leader (ROBOT PC) | `action.arm` |
| 손 state | `/leap/joint_states` | `leap_teleop --publish` (USER PC) | `observation.state.hand` |
| 손 action | `/leap/joint_command` | `leap_teleop --publish` | `action.hand` |
| 영상 | `/camera/cam_*/.../compressed` | RealSense (USER PC) | `observation.images` |
| 부가 | `/leap/human_hand`, `/leap/human_keypoints`, `/leap/teleop_mode`, 카메라 info, `/tf` | 위와 같음 | `recording.extra_topics` (bag에만) |

- `observation.state` = 팔 6 + 손 16 = **22차원**, `action` = 팔 6 + 손 16 = **22차원**.
- **action은 로봇에 실제로 보낸 최종 명령**이다. 손은 리타겟팅, 필터, StaleGuard를 모두 거친 값이다 (`/leap/joint_command`). 사람 원본(`/leap/human_*`)은 분석·재처리용으로 따로 남는다.
- 손 토픽 단위는 rad (`effort`만 mA). 관절 이름은 `leap_` + 관절 이름 (예: `leap_index_mcp_flex`). OMY의 `joint1..6`와 겹치지 않는다.
- 팔 토픽에는 `rh_r1_joint`(leader 트리거)가 계속 실리지만 config의 `joint_names`에서 뺐으므로 변환 때 이름으로 걸러진다 (spec D1). `[미검증]`: 변환기가 실제로 걸러내는지는 B10 형식의 확인으로 본다.
- Manus 전용 메시지(`manus_ros2_msgs`)는 기록하지 않는다. `/leap/human_*`가 표준 타입(`JointState`, `PoseArray`)이라 Cyclo 컨테이너에 설치할 것이 없다.

## 2. 구조와 제약

```
[ROBOT PC · 컨테이너]                         [USER PC]
 zenohd (:7447) ◄──── zenoh client ──────── 모든 USER PC 노드 (ROS_DOMAIN_ID=30, rmw_zenoh_cpp)
 omy_ai.launch.py                             Manus SDK 노드 ─► /manus_glove_0
   leader ─► /leader/joint_trajectory         leap_teleop --publish (LEAP USB)
   follower ─► /joint_states                    ├─► /leap/joint_command, /leap/joint_states
                                                └─► /leap/human_hand, /leap/human_keypoints, /leap/teleop_mode
                                              RealSense ×3 ─► /camera/...
                                              Cyclo Intelligence ─► rosbag2 (MCAP) ─► LeRobot
```

- 팔 루프는 ROBOT PC 안에서 닫히고, 손 루프는 `leap_teleop` 한 프로세스 안에서 닫힌다. **ROS 발행은 기록용일 뿐 제어 경로가 아니다.** 발행이 실패하거나 Cyclo가 죽어도 손은 계속 움직이고, `--publish` 쪽 예외는 삼킨다.
- **`leap_teleop`을 어디서 돌리나**: LEAP USB가 꽂힌 USER PC 호스트다 (`user_pc/README.md`의 A 방식, ROS source 필요). Cyclo와 카메라는 컨테이너에서 돈다. 호스트와 컨테이너가 같은 zenoh 라우터(ROBOT PC)에 client로 붙으므로 토픽이 서로 보여야 한다. `[미검증]`: 호스트의 `rmw_zenoh_cpp` 환경이 컨테이너와 같은 `ROS_DOMAIN_ID=30`, 같은 라우터 주소인지.
- 시계: 팔 토픽은 ROBOT PC → zenoh → USER PC로 온다. Cyclo는 수신 시각으로 정렬하므로 네트워크 지연만큼 어긋날 수 있다 (`[미검증]`, 6절).

## 3. 세화형 실행표에서 바뀌는 단계

| 실행표 단계 | 이 문서에서 |
|---|---|
| A3 `omy_env.sh` | 변경 없음. 호스트에서 `leap_teleop`을 돌릴 때도 같은 `ROS_DOMAIN_ID`, `RMW_IMPLEMENTATION`, `ZENOH_CONFIG_OVERRIDE`를 export한다 |
| B2 `omy_ai` | 손은 **주먹으로 대기**시킨 뒤 켠다. 팔이 움직이는 동안 손이 펴져 있으면 안 된다 (`--safe-pose fist`) |
| B6 토픽 확인 | 카메라 토픽 실제 경로를 적는다. E2에서 이 값을 config에 넣는다 |
| **B7 수집 설정 편집** | `omy_f3m_config.yaml`을 고치지 **않는다.** 대신 E2의 `omy_f3m_leap_config.yaml`을 복사한다 (새 로봇 타입) |
| B8 Cyclo 실행 | E2 이후에 실행한다 (config는 시작 시 읽는다) |
| B9 시험 에피소드 | 로봇 유형을 **`OMY F3M + LEAP`**(`omy_f3m_leap`)로 선택한다 |
| B10 기록 확인 | E6의 항목을 더한다 |
| D2 종료 | `leap_teleop`을 `omy_ai`보다 먼저 끈다 (E7) |

## 4. 추가 단계

### E1 · USER PC 호스트 · Manus 노드와 LEAP 준비
`../../user_pc/README.md`의 1단계(LEAP 영점·관절 시험)와 3-1(Manus 노드 확인)을 먼저 끝내 둔다. 손만 단독으로 구동되는 상태(README 3·4단계)가 되어 있어야 기록 단계로 온다.

- [ ] LEAP 5V를 **편 손으로** 켰다. `config/hardware_motors.yaml`이 있다.
- [ ] Manus 노드가 도는 PC에서 `ros2 topic echo /manus_glove_0 --once`가 나온다.
- [ ] `config/manus_calibration.yaml`이 이 작업자의 손으로 만들어져 있다.

### E2 · USER PC 호스트 · Cyclo 로봇 config 복사

```bash
cp <repo>/user_pc/config/omy_f3m_leap_config.yaml ~/cyclo_intelligence/shared/shared/robot_configs/
nano ~/cyclo_intelligence/shared/shared/robot_configs/omy_f3m_leap_config.yaml
```

- 파일 이름이 로봇 타입이 된다 (`omy_f3m_leap`). 파일을 두면 Cyclo가 자동으로 등록한다 (spec 5절 근거: `orchestrator_node.py`). `[미검증]` Cyclo를 다시 시작해야 UI 목록에 나타나는지.
- **카메라 3개의 `topic`을 B6에서 확인한 실제 RGB 압축 토픽으로 바꾼다.** 파일의 값은 예시다. 깊이 토픽을 기록하려면 세화형 B7처럼 `extra_topics`에 추가한다.
- `observation.state.hand`, `action.hand`의 `joint_names` 16개는 `leap_teleop`이 내는 이름과 **글자까지 같아야** 한다. 바꾸지 않는다.
- 팔 `joint_names`는 `joint1..6`만 둔다 (`rh_r1_joint` 제외).
- 원본은 우리 레포(`user_pc/config/`)에 두고 복사해서 쓴다. 고쳤다면 레포 쪽에도 반영한다.

### E3 · USER PC 호스트 · `leap_teleop --publish` 시작
세화형 B2(`omy_ai`) **이후**, B8(Cyclo) **이전**에 켠다. 셸은 `user_pc/README.md` 2단계의 zenoh 환경을 쓴다.

```bash
cd <repo>/user_pc
source /opt/ros/jazzy/setup.bash        # Humble이면 humble
source ~/open_manipulator/workspace/omy_env.sh
export PYTHONPATH="src:$PYTHONPATH"
# 먼저 로그만 (손을 건드리지 않음)
python3 -m leap_teleop.cli --source manus --safe-pose fist --thumb ik --dry-run --publish
# 실물
python3 -m leap_teleop.cli --source manus --safe-pose fist --thumb ik --publish
```

- leader 트리거로 기록하려면 `--source leader`로 바꾼다 (Manus 없이 같은 파이프라인 확인용).
- `[teleop] live`가 뜨면 손이 글러브를 따라간다. `--dry-run`에서는 피드백이 없어 `/leap/joint_states`가 나가지 않는다 (정상).
- 안전 수칙은 `user_pc/README.md`와 같다: 5V 차단 수단, 팔 이동 중 주먹, leader는 손으로 잡는다.

### E4 · USER PC · 토픽 확인
Cyclo를 켜기 전에 컨테이너(또는 같은 환경의 셸)에서:

```bash
ros2 topic list -t | grep -E '^/leap|joint_states|leader'
ros2 topic hz /leap/joint_command /leap/joint_states     # 50 Hz 근처
ros2 topic echo /leap/joint_states --once                # name 16개, position(rad), effort(mA)
ros2 topic echo /leap/teleop_mode --once                 # live
```

- [ ] `/leap/joint_command`, `/leap/joint_states`가 모두 보이고 50 Hz에 가깝다.
- [ ] `joint_states`가 훨씬 느리면 16모터 피드백 읽기가 tick을 먹는 것이다. 이 경우 발행 주기를 낮춘다 (코드 수정 필요, 6절).
- [ ] 호스트에서 낸 토픽이 **컨테이너에서** 보인다. 안 보이면 2절의 zenoh 환경 불일치다.

### E5 · 브라우저 · 시험 에피소드
세화형 B9와 같다. 다른 점만:

1. `Home`에서 로봇 유형을 **`OMY F3M + LEAP`**으로 선택한다.
2. `Record → Topic Monitor`에서 `/leap/joint_states`, `/leap/joint_command`, 팔 두 토픽, 카메라 3개가 모두 수신되는지 본다.
3. 손과 팔을 시작 상태에 놓고 `Record Start` → 팔은 leader, 손은 글러브로 짧게 시연 → `Save Episode`.
4. 팔 이동 중에 글러브를 벗거나 노드를 끄면 `hold` → `release`가 된다. 이 구간이 에피소드에 들어가지 않게 한다 (`/leap/teleop_mode`로 나중에 검수 가능).

### E6 · USER PC · 기록 확인
세화형 B10의 항목에 더해:

```bash
ros2 bag info /workspace/rosbag2/실제_데이터셋_폴더/0/
```

- [ ] 토픽 목록에 `/leap/joint_command`, `/leap/joint_states`, `/leap/human_hand`, `/leap/human_keypoints`, `/leap/teleop_mode`가 있고 메시지 수가 0보다 크다.
- [ ] `/leap/joint_states`와 `/leap/joint_command` 메시지 수가 비슷하다 (피드백 실패가 많으면 state가 적다).
- [ ] `/leap/human_keypoints`가 0이면 키포인트를 못 찾은 것이다 (`user_pc/README.md` 3-1의 손목·엄지 DIP 확인).
- [ ] `Data Tools → Review Episodes`에서 영상, 팔·손 관절 타임라인이 같이 재생된다.
- [ ] `Convert Dataset`으로 LeRobot v2.1/v3.0으로 변환해 본다. `observation.state`와 `action`이 22차원인지 `info.json`(또는 모양)으로 확인한다. `[미검증]`

### E7 · 종료 순서
1. 녹화가 끝났는지 확인한다.
2. **`leap_teleop` `Ctrl+C`** (Torque OFF 후 종료). 손이 풀려 처질 수 있으니 물체가 손에 없는지 본다.
3. 카메라 U1·U2·U3, `omy_ai`(팔 받치기), Cyclo U5, 마지막으로 `zenohd` 순으로 끈다 (세화형 D2).
4. LEAP 5V OFF. Manus 노드 종료.

## 5. 이 구성에서 알려진 제약

- **리타겟터를 바꾸면 같은 사람 입력이 다른 action이 된다.** 그래서 `/leap/human_*`를 남긴다. 단 영상은 당시 리타겟터로 움직인 결과이므로, 재리타겟팅한 action을 그 영상과 짝지어 학습하지는 않는다 (분석·비교용).
- **촉각(PaXini/HX5)은 기록 대상이 아니다.** `observation.tactile`은 bag에는 들어갈 수 있지만 LeRobot 변환기가 아직 없다. 센서를 붙일 때 별도 변환 스크립트를 짠다.
- **추론은 아직 아니다.** Cyclo 추론은 `action` 토픽에 발행한다. 팔은 `/leader/joint_trajectory`로 가지만, 손은 `/leap/joint_command`를 구독해 구동하는 `--source command`(가칭)가 아직 없다 (spec 6절). 그 모드에서는 `leap_teleop`이 `/leap/joint_command`를 발행하지 않아야 되먹임이 생기지 않는다.
- 이 구성은 LEAP Hand v1 전용이다. ROBOTIS 핸드로 바꾸면 관절 이름과 차원이 달라 config를 새로 만든다.

## 6. 아직 모르는 것 (실물에서 확인)

| 항목 | 확인 방법 | 틀리면 |
|---|---|---|
| 호스트 `leap_teleop`의 토픽이 컨테이너 Cyclo에 보이는가 | E4 | 호스트 zenoh 환경을 `omy_env.sh`와 맞춘다 |
| `/leap/joint_states` 주기 (16모터 피드백 비용) | E4 `ros2 topic hz` | `RosPublisher` 호출을 N tick마다로 줄인다 |
| `OMY F3M + LEAP`이 UI 로봇 목록에 나타나는가 | E5 | Cyclo 컨테이너를 다시 시작한다 |
| 변환기가 `rh_r1_joint`를 걸러내는가 (22차원) | E6 변환 결과 | config 팔 `joint_names`와 변환 로그를 확인한다 |
| 팔·손 `header.stamp` 대 bag 수신 시각 차이 | 첫 에피소드에서 비교 | 크면 두 PC를 chrony로 맞춘다 |
| 카메라 토픽 실제 경로 | 세화형 B6 | E2에서 config의 `topic`을 고친다 |
| 손목·엄지 DIP 노드 이름 (키포인트 유무) | `user_pc/README.md` 3-1 | 키포인트만 빠지고 엄지는 affine으로 돈다 |
