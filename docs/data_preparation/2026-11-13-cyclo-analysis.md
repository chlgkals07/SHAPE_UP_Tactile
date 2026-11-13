# Cyclo Intelligence 구조 분석 (자체 녹화 프로그램 설계용)

대상: `ROBOTIS-GIT/cyclo_intelligence` `11800ba` (2026-11-09, main). 11/12 User PC에 설치한 이미지는 `robotis/cyclo-intelligence:1.4.5`라 세부가 조금 다를 수 있다.
목적: 팔·손·촉각·카메라를 같은 시간축으로 기록해 LeRobot 데이터셋(pi0.5와 우리 모델 학습용)을 만드는 **우리 녹화 프로그램**을 설계하기 전에, Cyclo가 무엇을 어떻게 하는지 정리한다.

## 1. 전체 구성

Jazzy 컨테이너 하나에 여러 s6 서비스가 뜬다. 모든 노드가 `rmw_zenoh` 위에서 돈다.

| 구성요소 | 위치 | 하는 일 |
|---|---|---|
| UI (React) + nginx | `orchestrator/ui/` | 페이지: Home, Record, Replay, EditDataset, Training, Inference, AutonomyStudio. 브라우저 `:7080` |
| `orchestrator_node` | `orchestrator/orchestrator/orchestrator_node.py` (3.3k줄) | 제어 평면. 로봇 타입 선택, 토픽 목록, 녹화·학습·추론 명령을 다른 노드에 전달 |
| `cyclo_data` 노드 | `cyclo_data/` | 데이터 평면. 녹화, 변환, 편집, HF 업로드, 재생 |
| `rosbag_recorder` (C++) | `cyclo_data/recorder/rosbag_recorder/` | 실제 bag 기록기 |
| `cyclo_brain` | 백엔드별 policy 컨테이너 | 추론. LeRobot / GR00T 엔진, action chunk 처리 |
| `bt_node`, `supervisor_api` | | 행동 트리, 서비스 수명 관리, Nav2 (AI Worker용) |

로봇마다 `shared/shared/robot_configs/<robot>_config.yaml` 하나가 기준이다. 녹화 토픽, 변환할 state·action 차원, 추론 때 구독·발행할 토픽이 모두 여기서 정해진다.

```yaml
observation:
  images:  {cam_wrist: {topic, msg_type, rotation_deg}}
  state:   {arm: {topic, msg_type: JointState, joint_names: [...]}}
  tactile: {<name>: {topic, msg_type}}     # 기록만 한다. 변환하지 않는다 (아래 4절)
action:    {arm: {topic, msg_type: JointTrajectory, joint_names: [...]}}   # 추론 명령 대상이자 기록 대상
recording: {extra_topics: [/tf, ...]}
```

## 2. 녹화

순서: UI → `orchestrator` → `cyclo_data` `RecordingCommand.srv` → C++ `rosbag_recorder` `SendCommand.srv` (`prepare` → `start uri` → `stop` / `stop_and_delete` → `finish`).

- 저장 형식: **MCAP rosbag2** 한 개 + 카메라별 **MP4**.
- 이미지 토픽(`Image`, `CompressedImage`)은 bag에 넣지 않는다. 받는 즉시 FFmpeg 파이프로 H.264 MP4를 만든다. bag에는 프레임 메타데이터(`frame_index`, `header_stamp_ns`, `recv_ns`)만 남긴다. FPS는 첫 10프레임 간격으로 자동 감지한다.
- 그 밖의 토픽은 `GenericSubscription`으로 직렬화된 메시지를 그대로 bag에 쓴다. 타입을 몰라도 기록된다.
- 녹화 명령: START / STOP / PAUSE / RESUME / MOVE_TO_NEXT / RERECORD / SKIP_TASK / CANCEL. 서브태스크 구간(START_SEGMENT, STOP_SEGMENT …)과 태스크 문장(`TaskInfo`)도 지원한다.
- 상태 토픽 `RecordingStatus`: 녹화 단계, 경과 시간, 에피소드 번호, **카메라별 수신 Hz·마지막 수신 후 경과 시간·타임스탬프 skew**, 인코딩 진행률, 저장공간·CPU·RAM.

## 3. 변환 (MCAP + MP4 → LeRobot)

`cyclo_data/cyclo_data/converter/`. 출력은 LeRobot **v2.1과 v3.0** 둘 다 된다 (`to_lerobot_v21.py`, `to_lerobot_v30.py`). 출력 fps는 설정값이고 기본 30이다.

**시간 맞추기** (`base_converter._resample_to_fps`)
1. 기준 격자: `observation.state` 메시지 시각으로 만든다. state와 action이 **둘 다 처음 나온 시점**부터 끝까지, 1/fps 간격.
2. state 시각은 **`header.stamp`**를 쓴다. 없으면 MCAP log_time(받은 시각)으로 대신한다 (경고가 남는다).
3. action 시각은 **MCAP log_time**을 쓴다. `JointTrajectory`에 의미 있는 stamp가 없기 때문이다.
4. 격자의 각 시점에서 **그 시점 이전의 가장 최근 값**을 쓴다 (causal, 보간 없음). 얼마나 오래된 값인지(staleness)를 재서 경고·오류 기준(1/fps의 배수)으로 품질을 보고한다.
5. 카메라: 프레임의 `header_stamp_ns`로 각 격자 시점 이전의 마지막 프레임을 고른다. MP4를 다시 인코딩해 **격자 한 칸에 프레임 하나**로 맞춘다 (LeRobot 비디오 로더가 parquet 행과 1:1을 가정). 반복된 프레임 수는 `frame_reuse` 메타데이터로 남는다.

- state·action 그룹이 여러 개면 `joint_names` 순서로 이어 붙인다.
- 지원하는 메시지: `JointState.position`, `JointTrajectory`, `Odometry`/`Twist`(속도).
- 그 밖에: trim, 구간 제외, 서브태스크 이어 붙이기, 통계(`stats`), 캐시, HF 업로드, 에피소드 편집, 재생(웹, `:8082`).

## 4. 촉각 지원 상태

- 스키마에 `observation.tactile`이 있다 (`schema.get_tactile_topics`). 예시는 `ffw_sh5_rev1_config.yaml`의 `robotis_interfaces/msg/HandPressures`.
- **MCAP에 기록만 하고 LeRobot으로 변환하지 않는다.** 주석: *"not flattened into observation.state until the converter has a HandPressures parser."*
- 변환기는 `position` 필드가 있는 메시지만 숫자 벡터로 읽는다. 그래서 Paxini를 넣으려면 둘 중 하나다.
  - Paxini를 `JointState`처럼 위장해서 발행한다 (편법).
  - 변환기에 촉각 파서를 추가한다.

## 5. 우리 설정에서 막히는 점

| 문제 | 내용 |
|---|---|
| Humble ↔ Jazzy | 컨테이너는 Jazzy + `rmw_zenoh`. User PC Humble `rmw_zenoh`와는 데이터가 오가지 않는다 (11/12 결과 8절). 팔은 Robot PC(Jazzy)에, 손·카메라·촉각은 User PC(Humble)에 있다 |
| 촉각 | 위 4절. 기록은 되지만 데이터셋에 안 들어간다 |
| 무게 | UI, 학습, 추론, BT, Nav2까지 한 덩어리다. 우리가 지금 필요한 것은 녹화 + 변환이다. 이미지 pull도 11/12에 도중에 멈췄다 |
| action 시각 | action을 받은 시각(log_time)으로 맞춘다. 두 PC를 거쳐 오는 팔 action은 네트워크 지연이 그대로 섞인다 |
| 우리 손 action | `/leap/joint_command`는 `JointState`다. action 추출(`_extract_action_positions`)이 `JointState.position`도 받으므로 형식은 문제없다 (소스 확인) |

## 6. 우리 설계에 그대로 가져올 만한 것

1. **로봇 config YAML 하나가 기준**: observation(images / state / tactile) / action / extra 구조. Cyclo와 같은 키를 쓰면 나중에 Cyclo의 추론(`cyclo_brain`)이나 변환기를 재사용하기 쉽다.
2. **"원본 기록 → 나중에 변환" 2단계**: 녹화 중에는 받은 그대로 저장하고, 시간 맞추기·리샘플은 오프라인에서 한다. 같은 원본에서 fps나 차원을 바꿔 다시 뽑을 수 있다.
3. **메시지마다 `header_stamp`와 `recv_ns`를 둘 다 저장**: 무엇을 기준으로 맞출지 나중에 고를 수 있다.
4. **카메라는 녹화 중 바로 MP4로, 프레임별 타임스탬프는 따로**.
5. **causal 리샘플 + staleness 보고**: 미래 값을 쓰지 않는다. 오래된 값은 경고한다.
6. **녹화 상태 모니터**: 센서별 Hz, 마지막 수신 후 경과 시간. GUI에 그대로 쓸 만하다.
7. **에피소드 조작**: 저장 / 버리기 / 다시 찍기 / 다음 태스크, 태스크 문장 메타데이터.

## 7. 설계 때 정할 것 (계획 단계 입력)

- **시간 기준**: 두 PC의 시계(chrony)를 맞추고 `header.stamp`를 쓸지, User PC 한 곳에서 받은 시각으로 통일할지. 팔 토픽이 User PC에 도착하는지 자체가 먼저다 (DDS 통일 / Jazzy 컨테이너 / 24.04).
- **ROS를 통할지**: Paxini는 Python SDK, LEAP은 `leap_teleop` 프로세스 안에 있다. ROS 토픽으로 내보내 rosbag으로 받을지, 한 Python 프로세스에서 직접 모을지.
- **촉각 표현**: 합력 3축만 쓸지, 분포 힘(센서당 9~239점)까지 쓸지. LeRobot feature로 어떻게 펼칠지(`observation.tactile.*`).
- **action 정의**: 팔 = leader 명령 + offset (`/leader/joint_trajectory`), 손 = 실제로 보낸 최종 명령. wrist_flip이라 joint6 offset π/2.
- **출력**: LeRobot v2.1 / v3.0, fps, pi0.5가 기대하는 키 이름.
- **GUI**: 녹화 프로그램과 지금 여러 터미널로 하는 bring-up(zenohd, omy_ai_wrist_flip, Manus 노드, leap_manus, realsense, Paxini)을 한 화면으로 묶는 것은 디버깅이 끝난 뒤.

참고 파일 (Cyclo 레포): `docs/ARCHITECTURE.md`, `cyclo_data/README.md`, `cyclo_data/recorder/rosbag_recorder/FEATURES.md`, `shared/shared/robot_configs/schema.py`, `cyclo_data/cyclo_data/converter/base_converter.py` (`_extract_joint_data`, `_resample_to_fps`), `cyclo_data/cyclo_data/reader/frame_timestamps.py`, `interfaces/srv/RecordingCommand.srv`, `interfaces/msg/RecordingStatus.msg`.
