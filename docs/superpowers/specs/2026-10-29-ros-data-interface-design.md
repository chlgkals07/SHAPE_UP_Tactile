# OMY + LEAP (+ Manus) ROS 2 데이터 인터페이스 설계

- 작성일: 2026-10-29
- 상태: 승인 (8절 결정 반영)
- 목적: OMY + LEAP 텔레오퍼레이션 시연을 **세화형의 Cyclo Intelligence 수집 경로**(`docs/data_preparation/omy_demonstration_runbook.md`)에서 그대로 기록하고, 같은 토픽 계약으로 나중에 추론까지 돌린다.

---

## 1. 근거 요약

| 사실 | 출처 |
|---|---|
| Cyclo는 로봇 config의 `observation.images/state/tactile`, `action`, `recording.extra_topics`에 적힌 **ROS 토픽만** 기록한다 | `cyclo_intelligence/shared/shared/robot_configs/schema.py` |
| state/action 수치 파서는 `JointState`, `JointTrajectory`(deprecated), `Odometry`, `Twist`뿐 | `cyclo_data/recorder/replay_handler.py:447-511` |
| `action` 토픽은 기록 대상이면서 **추론 시 정책이 명령을 발행하는 곳** | `schema.py` 주석, `converter/orchestrator.py:tensor_array2joint_msgs` |
| 로봇 타입은 `*_config.yaml` 파일 추가만으로 자동 등록 | `orchestrator/orchestrator_node.py:861` |
| `observation.tactile`은 bag에만 들어가고 LeRobot 변환은 아직 없다 | `schema.py:get_tactile_topics` 주석 |
| 현재 `leap_teleop`은 ROS를 **구독만** 하고 손 상태·명령은 아무 토픽에도 내지 않는다 | `user_pc/src/leap_teleop/app.py`, `sources/*.py` |
| LEAP 공식 ROS 2 노드는 명령은 `cmd_leap` 토픽(`JointState`)으로 받지만 상태는 **service로만** 준다 → bag에 안 남는다 | `LEAP_Hand_API/ros2_module/scripts/leaphand_node.py:36-45` |
| 공식 `omy_ai.launch.py`는 그리퍼를 떼고 LEAP을 단 상태에서도 동작하고, `rh_r1_joint`는 토픽에 계속 남는다 | `docs/field-test/2026-10-09-results.md` 3번 |

선행연구 기록 방식 비교(ACT, HATO, TeleVision, RDP, BiDex): **action = 로봇에 보낸 최종 명령**이 다수이고, TeleVision은 사람 원본 입력(`action/cmd`)도 따로 남긴다. HATO·RDP는 촉각 원본을 obs에 그대로 넣고 변환은 직접 짠다.

---

## 2. 전체 구조

```
[ROBOT PC · OMY 컨테이너]                           [USER PC]
 zenohd (router, :7447) ◄──────── zenoh client ──────── 모든 USER PC 노드 (ROS_DOMAIN_ID=30, rmw_zenoh_cpp)
 omy_ai.launch.py
   OMY-L100 leader ──► /leader/joint_trajectory ─────► (Cyclo 기록: action.arm)
   OMY-F3M follower ─► /joint_states ────────────────► (Cyclo 기록: state.arm)

                                                     Manus SDK ROS 2 노드 ──► /manus_glove_0 (ManusGlove)
                                                                                   │
                                                     leap_teleop (노드 1개, 50 Hz) ◄┘
                                                       source → retarget → StaleGuard → LeapHandDriver ──► LEAP (USB, Dynamixel)
                                                       │                                      │
                                                       ├─► /leap/joint_command  (action.hand) │
                                                       ├─► /leap/joint_states   (state.hand) ◄┘ read_feedback()
                                                       ├─► /leap/human_hand     (extra: Manus 각도 원본)
                                                       ├─► /leap/human_keypoints(extra: Manus 키포인트 원본)
                                                       └─► /leap/teleop_mode    (extra: live/hold/release)

                                                     realsense ×3 ──► /camera/cam_{wrist,front,side}/... (세화형 실행표 B3–B5)
                                                     Cyclo Intelligence ──► rosbag2 (MCAP) ──► LeRobot
```

- 팔의 텔레오퍼레이션 루프는 지금처럼 ROBOT PC 안에서 닫힌다. 우리는 건드리지 않는다.
- 손의 루프는 USER PC의 `leap_teleop` 한 프로세스 안에서 닫힌다. ROS는 **기록용 출력**으로만 붙고, 제어 경로에는 들어가지 않는다. 그래서 ROS가 끊겨도 StaleGuard와 하드웨어 경로는 그대로다.

---

## 3. 토픽 계약

### 3.1 우리가 새로 내는 토픽 (`leap_teleop`)

| 토픽 | 타입 | 주기 | 내용 | Cyclo 역할 |
|---|---|---|---|---|
| `/leap/joint_command` | `sensor_msgs/JointState` | 제어 tick (50 Hz) | `StaleGuard.resolve()` 결과 = 실제로 `driver.command()`에 넘긴 값. `position`만 채움 | `action.hand` |
| `/leap/joint_states` | `sensor_msgs/JointState` | 제어 tick (50 Hz) | `read_feedback()`의 위치/속도/전류 → `position`/`velocity`/`effort` | `observation.state.hand` |
| `/leap/human_hand` | `sensor_msgs/JointState` | Manus 수신 시 | `HumanHand.angles` 20개 (`HUMAN_ANGLE_NAMES`, Manus ergonomics 원본) | `recording.extra_topics` |
| `/leap/human_keypoints` | `geometry_msgs/PoseArray` | Manus 수신 시 | `HumanHand.keypoints` 8개 (`KEYPOINT_NAMES` 순서, 글러브 frame, m). 없으면 발행 안 함 | `recording.extra_topics` |
| `/leap/teleop_mode` | `std_msgs/String` | 모드 변경 시 + 1 Hz | `waiting / live / hold / release` | `recording.extra_topics` |

규칙:
- **관절 이름**: `leap_` + `ANGLE_NAMES` (예: `leap_index_mcp_flex`). OMY의 `joint1..6`와 겹치지 않게 하고, Cyclo가 feature 이름을 만들 때 그대로 쓴다.
- **단위**: ROS 관례(REP-103)대로 **rad, rad/s**. 0 = 편 손은 내부 규약과 같다. `effort`는 mA 그대로 (JointState에 단위 필드가 없으니 이 문서가 계약이다).
- **header.stamp**: 발행 시점의 노드 시계. `joint_command`와 `joint_states`는 같은 tick의 같은 stamp를 쓴다.
- `/leap/human_*`는 `--source manus`일 때만 낸다. Manus 전용 메시지(`manus_ros2_msgs`) 없이 표준 타입만 쓰므로, Cyclo 컨테이너에 따로 설치할 것이 없다.
- feedback 읽기가 실패한 tick은 `/leap/joint_states`만 건너뛴다. 제어는 멈추지 않는다.

### 3.2 기존 토픽 (변경 없음)

| 토픽 | 타입 | 발행 | 관절 | Cyclo 역할 |
|---|---|---|---|---|
| `/joint_states` | `JointState` | follower (ROBOT PC) | `joint1..6`, `rh_r1_joint` | `observation.state.arm` |
| `/leader/joint_trajectory` | `JointTrajectory` | leader broadcaster (ROBOT PC) | `joint1..6`, `rh_r1_joint` | `action.arm` |
| `/manus_glove_0` | `manus_ros2_msgs/ManusGlove` | Manus SDK 노드 (USER PC) | – | 기록 안 함 (`/leap/human_*`로 대체) |
| `/camera/cam_*/color/.../compressed` | `CompressedImage` | realsense (USER PC) | – | `observation.images` |

---

## 4. state / action 정의

| 벡터 | 구성 | 차원 |
|---|---|---|
| `observation.state` | `arm`(`/joint_states`: joint1..6) + `hand`(`/leap/joint_states`: 16) | 6 + 16 = 22 |
| `action` | `arm`(`/leader/joint_trajectory`: joint1..6) + `hand`(`/leap/joint_command`: 16) | 6 + 16 = 22 |

토픽에는 `rh_r1_joint`가 계속 실리지만 config의 `joint_names`에서 빼면 변환기가 이름으로 걸러낸다 (`base_converter.py:3219`).

- action은 **로봇에 보낸 최종 명령**이다 (ACT/HATO/TeleVision/Cyclo와 같은 방식). 리타겟팅·필터·StaleGuard를 모두 거친 값이라 정책은 "LEAP이 받은 명령"을 배운다.
- "다음 시점 state를 action으로" 쓰는 방식(RDP)이 필요해지면, 실측 state가 기록되어 있으니 변환할 때 만들 수 있다. 수집할 때 고를 필요가 없다.
- 리타겟터를 바꾸면 같은 사람 입력이 다른 action이 된다. 그래서 `/leap/human_*`를 남긴다. 단, 녹화된 영상은 당시 리타겟터로 움직인 결과이므로, 재리타겟팅한 action을 그 영상과 짝지어 학습하지는 않는다 (분석·비교용).

---

## 5. Cyclo 로봇 config

`~/cyclo_intelligence/shared/shared/robot_configs/omy_f3m_leap_config.yaml` (파일 이름 = 로봇 타입 `omy_f3m_leap`). 원본은 우리 레포에 두고 복사해서 쓴다.

```yaml
orchestrator:
  ros__parameters:
    omy_f3m_leap:
      robot_name: "OMY F3M + LEAP"
      urdf_path: urdf/omy_f3m.urdf        # UI 표시용. LEAP 포함 URDF는 필요해지면
      observation:
        images:
          cam_wrist: {topic: /camera/cam_wrist/color/image_rect_raw/compressed, msg_type: sensor_msgs/msg/CompressedImage}
          cam_front: {topic: /camera/cam_front/color/image_raw/compressed, msg_type: sensor_msgs/msg/CompressedImage}
          cam_side:  {topic: /camera/cam_side/color/image_raw/compressed,  msg_type: sensor_msgs/msg/CompressedImage}
        state:
          arm:
            topic: /joint_states
            msg_type: sensor_msgs/msg/JointState
            joint_names: [joint1, joint2, joint3, joint4, joint5, joint6]
          hand:
            topic: /leap/joint_states
            msg_type: sensor_msgs/msg/JointState
            joint_names: [leap_index_mcp_side, leap_index_mcp_flex, leap_index_pip_flex, leap_index_dip_flex,
                          leap_middle_mcp_side, leap_middle_mcp_flex, leap_middle_pip_flex, leap_middle_dip_flex,
                          leap_ring_mcp_side, leap_ring_mcp_flex, leap_ring_pip_flex, leap_ring_dip_flex,
                          leap_thumb_cmc_side, leap_thumb_cmc_flex, leap_thumb_mcp_flex, leap_thumb_ip_flex]
      action:
        arm:
          topic: /leader/joint_trajectory
          msg_type: trajectory_msgs/msg/JointTrajectory
          joint_names: [joint1, joint2, joint3, joint4, joint5, joint6]
        hand:
          topic: /leap/joint_command
          msg_type: sensor_msgs/msg/JointState
          joint_names: [ ...state.hand와 동일한 16개... ]
      recording:
        extra_topics:
          - /tf
          - /camera/cam_wrist/color/camera_info
          - /camera/cam_front/color/camera_info
          - /camera/cam_side/color/camera_info
          - /leap/human_hand
          - /leap/human_keypoints
          - /leap/teleop_mode
```

카메라 토픽 경로는 세화형 실행표 B6에서 확인한 실제 값으로 바꾼다. 깊이 토픽을 넣는 방법은 실행표 B7과 같다.

---

## 6. 추론 시 같은 계약 재사용

- Cyclo 추론 Process B는 `action` 토픽에 발행한다 → 팔은 `/leader/joint_trajectory`(공식 경로), 손은 `/leap/joint_command`.
- 손 쪽은 `leap_teleop`에 `--source command`(가칭)를 추가한다. 이 source는 `/leap/joint_command`를 구독해서 `Reading(hand=...)`으로 넘기고, 기존 StaleGuard → driver를 그대로 탄다. 정책이 멈추면 hold → release로 손이 안전 자세로 간다.
- 이 모드에서 `leap_teleop`은 `/leap/joint_command`를 **발행하지 않는다** (자기 입력을 되먹이지 않도록). `/leap/joint_states`는 계속 발행한다 (정책의 state 입력).
- 이 절은 계약만 고정하고, 구현은 추론 단계에서 한다.

---

## 7. 범위 밖 / 나중에

- **촉각 (PaXini / HX5)**: `observation.tactile`로 bag에는 넣을 수 있지만 LeRobot 변환기가 없다. 변환 스크립트는 우리가 직접 짠다 (HATO·RDP와 같은 방식). 토픽 이름과 타입은 센서 연동 때 정한다.
- **PC 간 시계**: 팔 토픽은 ROBOT PC → zenoh → USER PC로 넘어온다. Cyclo는 수신 시각으로 정렬하므로 네트워크 지연(수 ms)만큼 어긋날 수 있다. 첫 시험 에피소드에서 `header.stamp`와 bag 수신 시각의 차이를 확인하고, 크면 chrony로 맞춘다.
- **feedback 읽기 비용**: 50 Hz tick마다 16모터 sync read를 추가한다. 실측해서 tick 예산을 넘으면 state 발행 주기를 낮춘다 (예: 2 tick마다).

---

## 8. 결정 (2026-10-29)

| # | 항목 | 결정 | 근거 |
|---|---|---|---|
| D1 | `rh_r1_joint` | **뺀다** (arm 6관절) | LEAP 장착 후 의미 없는 차원. follower `arm_controller`가 `allow_partial_joints_goal: true`라 추론 때 6관절 명령도 받는다 (`omy_f3m_follower_ai/hardware_controller_manager.yaml:38`) |
| D2 | LEAP 토픽 단위 | **rad** | ROS 관례, OMY와 통일 |
| D3 | 사람 원본 기록 | **각도 20 + 키포인트 8** | 엄지 IK 재처리에 키포인트 필요 |
| D4 | `/leap/teleop_mode` | **기록** | hold/release 구간 검수·trim |
