# 녹화기 설계 컨텍스트 (Fable 세션 시작용)

2026-11-13 기준. 다음 세션에서 **자체 녹화 프로그램의 인터페이스와 수집 항목**을 정하기 위한 출발점이다. 이 문서는 사실과 결정만 모은다. 설계는 아직 하지 않았다.
같이 읽을 문서: [`2026-11-13-cyclo-analysis.md`](2026-11-13-cyclo-analysis.md) (ROBOTIS Cyclo가 녹화·변환을 어떻게 하는지).

## 1. 목표

- 팔 · 손(LEAP) · 촉각(Paxini) · 손목 카메라(D405)를 **같은 시간축으로** 기록한다.
- 출력은 **LeRobot 표준 데이터셋**이다. 용도는 pi0.5 fine-tune, 그리고 우리 아키텍처(Tactile RL Token, `research/idea/`, `prior-work/Tactile RL Token/`) 학습.
- **촉각은 고주파(센서 원래 속도, 약 90 Hz)로 받는 것이 목표다.** 학습에 어떤 주기로 쓸지는 아직 모른다.
- 나중에 지금 여러 터미널로 하는 bring-up과 녹화를 GUI 하나로 묶는다. 디버깅이 끝난 뒤의 일이다.

## 2. 지금까지의 결정

| 결정 | 이유 |
|---|---|
| Cyclo 대신 **얇은 자체 녹화기** | Cyclo로 가면 풀어야 할 문제가 셋이다: Humble↔Jazzy 통신, Paxini ROS 발행기, 촉각 변환 미지원. 자체 녹화기는 팔 데이터 가져오기 하나만 풀면 된다 |
| 유력안: **LeRobot 녹화 방식** + **원본 고주파 로그를 따로** | LeRobot에 직접 정의한 `Robot` 클래스와 센서별 최신값 어댑터를 쓰면 표준 데이터셋이 바로 나온다. 고정 fps에서 잃는 고주파 촉각은 원본 로그로 남긴다. **아직 확정 아님** |
| Cyclo에서 가져올 것 | 로봇 config YAML 구조(observation: images / state / tactile, action), 센서별 Hz·지연 모니터, 에피소드 저장 / 버리기 / 다시 찍기 흐름, 원본에 `header_stamp`와 `recv` 시각 둘 다 남기기 |
| 장착 | LEAP을 90° 돌려 단다. 팔은 `omy_ai_wrist_flip`(joint6 offset π/2)으로 띄운다. 순정 장착 데이터와 섞지 않는다 |

## 3. 하드웨어와 PC

```text
[ROBOT PC: OMY 본체 안, Docker open_manipulator, ROS 2 Jazzy, rmw_zenoh, ROS_DOMAIN_ID=30]
  zenohd :7447
  omy_ai_wrist_flip
    follower OMY-F3M (6축 + rh_r1_joint)  → /joint_states
    leader   OMY-L100 (6축 + 트리거)        → /leader/joint_trajectory  (= leader 위치 + offsets)
        │ USB 랜 (User PC 10.42.0.1 ↔ 로봇 10.42.0.241, NetworkManager shared)
[USER PC: jiwoo-950QDB, Ubuntu 22.04, ROS 2 Humble, GPU 없음]
  Manus 글러브 동글 → manus_data_publisher (ROS 2) → /manus_glove_0 (약 120 Hz, timestamp 없음)
  leap_teleop (Python, 50 Hz 루프) → LEAP Hand v1 (FTDI /dev/ttyUSB0, 16모터, 5V)
  D405 (OMY Camera 포트 → USB, 지금은 USB2) → realsense2_camera (ROS 2)
  Paxini GEN3 → High-Speed 통신 보드 → /dev/ttyACM0 (Python SDK, ROS 없음)
```

| 장치 | 접속 | 속도·형식 | 코드 |
|---|---|---|---|
| 팔 follower 상태 | Robot PC ROS 토픽 `/joint_states` | `JointState`, joint1..6 (+`rh_r1_joint`) | ROBOTIS 순정 |
| 팔 action | Robot PC `/leader/joint_trajectory` | `JointTrajectory` 7값, 마지막이 트리거. joint6에 π/2 offset 포함 | `OMY_Tactile_Robot_PC/omy_leap_bringup` |
| LEAP 명령·상태 | User PC, `leap_teleop` 프로세스 안 | 50 Hz 루프 (`--rate` 10~200). 상태는 16모터 위치·속도·전류. 피드백 읽기 비용 때문에 약 43~50 Hz | `user_pc/src/leap_teleop/` |
| Manus 글러브 | User PC ROS 토픽 | ergonomics 20개(도), 키포인트. 120 Hz로 마지막 값 반복 발행 | `third_party/manus` |
| D405 | User PC ROS 토픽 | `/camera/cam_wrist/color/image_raw(/compressed)`. USB2: 424x240@30, 깊이 끔이면 18~30 Hz | apt `ros-humble-realsense2-camera` |
| Paxini | User PC `/dev/ttyACM0` | 약 90 Hz auto-push (Hz 설정 옵션 없음). 센서마다 합력 3축 + 분포 힘(DP-S2015: 52점, IP-S1610: 25점) | `third_party/paxini` (`HighSpeedHandBoard`) |

- Paxini 구매 계획(`research/paxini-integration.md`): DP-S2015 5개, IP-S1610 5개, 보드 2개. 손가락 4개의 끝·마디에 하나씩, 보드당 4센서. **지금 실제로 몇 개가 어디 붙어 있는지는 확인이 필요하다.** 11/12 연동 확인 때의 구성도 문서에 없다.
- Paxini LeRobot 연동 예시: `third_party/paxini/integrations/lerobot/paxini.py` (아직 검토 안 함).

## 4. 지금 있는 기록 경로 (`leap_teleop --publish`, Cyclo용으로 만든 것)

`user_pc/src/leap_teleop/app.py`의 루프: source.poll → retarget → stale guard → driver.command → (선택) publisher.
publisher(`ros_out.py`)는 기록 전용이다. 실패해도 손은 멈추지 않는다. stamp는 노드 시계 `now()`.

| 토픽 | 형식 | 내용 |
|---|---|---|
| `/leap/joint_command` | `JointState` (rad) | LEAP에 실제로 보낸 최종 명령 (= 손 action) |
| `/leap/joint_states` | `JointState` (rad, mA) | LEAP 측정값 (= 손 state) |
| `/leap/human_hand` | `JointState` | 글러브 ergonomics |
| `/leap/human_keypoints` | `PoseArray` | 글러브 키포인트 |
| `/leap/teleop_mode` | `String` | live / hold / release |

11/03 정의: state·action은 각각 팔 6 + 손 16 = 22차원. 설계 문서는 `docs/superpowers/specs/2026-10-29-ros-data-interface-design.md`.
`--log-csv`(`diag_log.py`)는 틱마다 글러브 원값, 명령, 전송값, 위치, 전류를 CSV로 남긴다. 고주파 원본 로그의 선례로 쓸 수 있다.

## 5. 남은 핵심 제약

1. **팔 데이터만 PC를 건넌다.** User PC Humble `rmw_zenoh`(0.1.11)는 Robot PC Jazzy 토픽을 목록에서는 보지만 데이터는 0개다 (`docs/field-test/2026-11-12-results.md` 8절). 후보:
   - DDS로 통일: 설치 없음. Humble↔Jazzy 표준 메시지는 대개 통한다. **미검증**
   - Robot PC 컨테이너 안에 작은 중계 노드: 팔 토픽 + Robot PC 시각 → UDP 또는 순수 zenoh. ROS 버전과 무관
   - Cyclo의 `cyclo_brain/sdk/zenoh_ros2_sdk`: ROS 없이 `rmw_zenoh` 토픽을 읽는 것으로 보인다. **소스 미확인**
2. **시간 기준**: User PC 한 시계로 수신 시각을 찍을지, 두 PC를 chrony로 맞추고 원천 시각을 쓸지. USB 랜 지연은 수 ms 수준으로 예상한다(**미측정**).
3. **센서마다 주기와 시각 정보가 다르다**: Manus는 timestamp가 없고, LEAP은 루프 시각, 카메라는 `header.stamp`, Paxini는 수신 시각(보드 timestamp가 있는지 미확인), 팔은 Robot PC 시각.
4. **D405가 USB2**라서 30 Hz가 빠듯하다.
5. User PC에 **GPU가 없다**. 실시간 비디오 인코딩 부하를 고려해야 한다.

## 6. 정해야 할 것 (다음 세션의 안건)

**인터페이스**
- 센서 어댑터 공통 인터페이스: 최신값 읽기, 원본 스트림 버퍼, 시각 정보(원천 시각 / 수신 시각), 상태(Hz, 끊김).
- `leap_teleop`과의 경계: 같은 프로세스에 넣을지, 별도 프로세스에서 공유 메모리·소켓·ROS로 받을지. 텔레옵 루프의 안전 동작(hold / release)은 녹화와 무관하게 유지돼야 한다.
- 팔 데이터를 받는 방법 (5절 1번).
- 녹화 제어: 시작 / 저장 / 버리기 / 다시 찍기, 태스크 문장. CLI 먼저 하고 GUI는 나중에.

**수집 항목**
- observation.state: 팔 6 (joint6 π/2 offset을 그대로 둘지), 손 16 (위치만? 전류도?), 그리퍼 트리거 제외 여부.
- action: 팔 = leader 명령(offset 포함), 손 = 최종 전송 명령.
- 촉각: 합력 3축만 쓸지, 분포 힘 전체를 쓸지. 센서 몇 개를 어떤 순서로. LeRobot feature 이름(`observation.tactile.*`), 정규화.
- 카메라: 해상도·fps, 깊이 사용 여부.
- 부가 정보(데이터셋에 넣지 않고 원본에만 남길 것): 글러브 원값·키포인트, teleop_mode, 모터 전류, 장착 모드.

**출력 형식**
- LeRobot 버전(v2.1 / v3.0)과 pi0.5 학습 코드가 기대하는 키·차원 (`vla-docker-rtxpro6000/`의 pi0.5 환경 기준).
- 데이터셋 fps (30?), 고주파 원본 로그의 형식과 위치, 둘을 잇는 방법(같은 에피소드 id·시각).

## 7. 레포에서 볼 곳

| 경로 | 내용 |
|---|---|
| `docs/manus_teleop_guide.html` / `.md` | 현장 all-in-one 절차 (90° 장착 반영) |
| `docs/field-test/2026-11-12-results.md` | 최신 현장 결과, 11/13 정리, Humble↔Jazzy 문제 |
| `docs/data_preparation/omy_leap_cyclo_recording.md` | Cyclo용 토픽·차원 정의 (보류됐지만 참고) |
| `docs/superpowers/specs/2026-10-29-ros-data-interface-design.md` | `/leap/*` 인터페이스 설계 근거 |
| `user_pc/src/leap_teleop/` | 텔레옵 코드: `app.py` 루프, `ros_out.py` 기록 발행, `diag_log.py` CSV, `hand/leap_v1.py` 드라이버, `sources/manus.py` |
| `user_pc/config/omy_f3m_leap_config.yaml` | Cyclo 형식 로봇 config (카메라 토픽은 `image_rect_raw`로 틀려 있음) |
| `third_party/paxini/` | Paxini SDK, `docs/SETUP_LINUX.md`, `integrations/lerobot/` |
| `research/paxini-integration.md` | Paxini 구매·배선 계획 |
| `research/idea/`, `prior-work/Tactile RL Token/` | 우리 아키텍처 아이디어와 관련 연구 |
| `vla-docker-rtxpro6000/` | pi0.5 / FTP-1 학습 환경 |
| 별도 레포 `~/Projects/OMY_Tactile_Robot_PC` | Robot PC 쪽 `omy_leap_bringup` (wrist_flip launch) |
