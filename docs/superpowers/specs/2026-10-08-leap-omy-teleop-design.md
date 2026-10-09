# OMY leader → LEAP Hand 텔레옵 1차 설계

- 작성일: 2026-10-08
- 상태: 1차 확정 대기 (리뷰 반영본)
- 범위: 1차 = 키보드 / OMY leader 그리퍼로 LEAP Hand v1을 쥐었다 펴기

## 1. 목표와 비목표

**목표**
1. 키보드로 LEAP Hand를 open ↔ fist 사이에서 움직인다.
2. OMY leader 그리퍼(`rh_r1_joint`)를 쥐면 ROS 2 토픽으로 받아 LEAP Hand가 닫힌다.
3. 입력 소스, 입력→손 변환, 손 드라이버를 각각 나중에 교체할 수 있는 구조로 만든다. 다음 단계는 Manus 글러브(+ Quest) 입력이다.

**비목표 (1차)**
- 16관절 개별 retargeting (Manus 단계에서 한다)
- 촉각 센서 연동, 데이터 수집(Cyclo Intelligence), 정책 추론
- LEAP Hand의 ROS 2 노드화 (필요해질 때 `hand/` 위에 얇게 씌운다)

## 2. 확인된 사실 (소스 근거)

| 사실 | 근거 |
|---|---|
| 텔레옵 루프(leader → follower)는 Robot PC 안에서 닫힌다 | `omy_ai.launch.py`: follower + `joint_trajectory_executor` + leader (L100) 실행 |
| follower는 `/leader/joint_trajectory`를 구독한다 | `omy_f3m_follower_ai.launch.py`: `/arm_controller/joint_trajectory` → `/leader/joint_trajectory` remap |
| 이 토픽은 7개 관절(`joint1~6`, `rh_r1_joint`)을 싣는다 | `omy_l100_leader_ai/hardware_controller_manager.yaml`: `joint_trajectory_command_broadcaster` |
| leader 그리퍼 값은 부호 반전(`reverse_joints`)과 offset 0.2가 적용돼 있다 | 위와 같은 파일 |
| 그리퍼 모터는 팔과 **별도의 ros2_control 시스템**(`OMYF3MEndUnitSystem`, 포트 `/dev/ttyAMA4`, Dynamixel ID 7)이다 | `omy_f3m_end_unit.ros2_control.xacro` |
| 그 시스템은 `use_mock_hardware` 옵션을 가진다 | 위와 같은 파일 |
| follower `arm_controller`의 `joints`에 `rh_r1_joint`가 포함된다 | `omy_f3m_follower_ai/hardware_controller_manager.yaml` |

**미확인 (실물/실행으로 확인 필요)**: 그리퍼를 물리적으로 떼고 공식 launch를 그대로 실행하면 실패할 것으로 **추정**한다 (end unit의 Dynamixel ID 7을 찾지 못함). 확인되지 않았다.

## 3. 그리퍼 제거 문제 해결

### 문제
- 공식 follower launch는 `omy_f3m.urdf.xacro`를 쓰고, 이 URDF는 end unit 시스템을 무조건 포함한다. launch argument만으로는 끌 수 없다.
- leader는 7관절 trajectory를 publish한다. follower를 6관절로 줄이면 `JointTrajectoryController`가 모르는 관절이 포함된 메시지를 거부할 가능성이 있다 (추정, 확인 필요).

### 선택: end unit만 mock으로 대체 ("가상 그리퍼 관절")
- 우리가 별도 URDF xacro를 만들고, **팔 시스템은 실제 하드웨어, end unit 시스템만 `use_mock_hardware:=true`** 로 포함한다. 이 xacro와 launch는 **별도 Robot PC용 레포**(5절)에 둔다.
- `rh_r1_joint`가 소프트웨어상 계속 존재하므로 `arm_controller` 설정과 leader의 7관절 토픽을 **그대로** 쓴다. 중계 노드가 필요 없다.
- 장점: 공식 설정과의 차이가 최소(URDF 1개, launch 1개)이고, 서브모듈은 수정하지 않는다.

### 대안 (선택안이 실패할 때만)
- 6관절 follower + `/leader/joint_trajectory` → `/follower/joint_trajectory` 중계 노드(7번째 관절 제거). 구조가 한 단계 늘어난다.

### 검증 순서
0. (선택) User PC에서 mock으로 사전 확인. 1차에서는 생략하고 실물에서 바로 확인한다.
1. 그리퍼를 제거한 상태에서 **공식 `omy_ai.launch.py`를 먼저 실행**한다. 정상이면 우리 Robot PC 레포는 필요 없다.
2. 실패하면 Robot PC 레포의 launch로 팔만 실제 하드웨어로 띄운다.
3. leader를 연결해 follower가 따라오는지 확인한다.

## 4. 아키텍처

```
[Robot PC / OMY 컨테이너]                  [User PC]
 leader ──/leader/joint_trajectory──►  follower (기존 루프, 그대로)
                    │ (DDS, ROS_DOMAIN_ID=30)
                    └────────────────►  Ros2LeaderSource ┐
                                        KeyboardSource ──┤ (둘 중 하나 선택)
                                                         ▼
                                     Retargeter (scalar → HandCommand)
                                                         ▼
                                     SafetyFilter (stale 감시, 속도/범위 제한)
                                                         ▼
                                     HandDriver (LEAP v1, USB 시리얼)
```

### 교체 가능한 경계 (3곳)
| 경계 | 인터페이스 | 1차 구현 | 이후 교체 예 |
|---|---|---|---|
| 입력 | `Source.poll() -> Reading` | Keyboard, Ros2Leader | Manus, 웹캠 |
| 변환 | `Retargeter: Reading -> HandCommand` | scalar→posture 보간 | Manus 16관절 직접 매핑 |
| 출력 | `HandDriver` | LEAP v1 | LEAP v2, 다른 손 |

**공통 계약 `HandCommand`**: 16개 각도(도), `ANGLE_NAMES` 순서, 0 = 편 손. 기존 `leap-hand` 레포의 표준 표현을 그대로 쓴다. `Reading`은 scalar(0~1) 또는 HandCommand 중 하나다.

## 5. 폴더 구조

```
SHAPE_UP_Tactile/
├── third_party/
│   └── open_manipulator/            # 서브모듈 (참고용, 수정 금지)
├── user_pc/                         # User PC에서 실행 (순수 Python 패키지)
│   ├── pyproject.toml
│   ├── src/leap_teleop/
│   │   ├── types.py                 # HandCommand, Reading
│   │   ├── hand/
│   │   │   ├── base.py              # HandDriver Protocol
│   │   │   ├── leap_v1.py           # (이식) LeapHandHardwareController
│   │   │   ├── calibration.py       # (이식) HardwareMotorCalibration
│   │   │   └── joints.py            # (이식) ANGLE_NAMES
│   │   ├── sources/
│   │   │   ├── base.py              # Source Protocol
│   │   │   ├── keyboard.py
│   │   │   └── ros2_leader.py       # rclpy, rh_r1_joint → 0~1
│   │   ├── retarget/
│   │   │   └── scalar_posture.py    # open↔fist 보간
│   │   ├── safety.py                # stale 감시 + fallback
│   │   ├── config.py                # yaml 로딩
│   │   ├── tools/                   # 실물 bring-up 도구 (이식), python -m leap_teleop.tools.<name>
│   │   │   ├── check_hardware.py
│   │   │   ├── calibrate_motors.py
│   │   │   └── joint_test.py
│   │   └── app.py                   # source→retarget→safety→driver 루프
│   ├── config/
│   │   ├── postures.yaml            # open / fist (추적됨)
│   │   ├── leader_gripper.yaml      # leader 값 min/max (추적됨)
│   │   └── hardware_motors.example.yaml   # 실제 hardware_motors.yaml은 gitignore
│   └── tests/
├── docs/superpowers/specs/
├── prior-work/  research/           # 기존
└── README.md
```

**Robot PC용 코드는 별도 레포에 둔다** (가칭 `omy-leap-bringup`, 이름과 공개 범위는 미정). Robot PC는 작은 레포 하나만 clone하고, 서브모듈과 User PC 코드는 갖지 않는다. 내용은 아래와 같으며, 공식 launch가 그리퍼 제거 상태에서 실패할 때만 필요하다.

```
omy-leap-bringup/                    # ROS 2 패키지 (overlay 방식, ROBOTIS 패키지 수정 없음)
├── package.xml, setup.py
├── urdf/omy_f3m_no_gripper.urdf.xacro   # end unit만 mock, 엔드이펙터는 별도 include 블록
├── config/hardware_controller_manager.yaml
└── launch/ follower_no_gripper.launch.py, omy_ai_no_gripper.launch.py
```

두 레포를 잇는 계약: 토픽 `/leader/joint_trajectory`(`JointTrajectory`), 관절 이름 `rh_r1_joint`, `ROS_DOMAIN_ID=30`. 이 값은 `user_pc/config/leader_gripper.yaml`에 명시한다.

원칙: **ROS 2 의존은 `sources/ros2_leader.py` 한 파일에만** 둔다. 나머지는 ROS 없이 import/테스트된다.

## 6. 기존 `leap-hand` 레포에서 이식할 것 (필요한 것만)

출처: https://github.com/shinjju1209/leap-hand (commit `ddfabaa`). 이식한 파일은 헤더에 출처 commit을 남긴다.

| 이식 | 원본 | 용도 |
|---|---|---|
| `hand/leap_v1.py` | `leap_hand_hardware_controller.py` | LEAP v1 제어, 안전 한계, Torque OFF 보장 |
| `hand/calibration.py` | `hardware_calibration.py` | 모터별 영점/방향 |
| `hand/joints.py` | `hand_angles.py`의 `ANGLE_NAMES`만 | 관절 순서 (MediaPipe 계산 코드는 가져오지 않음) |
| `tools/check_hardware.py` | `leap_hand_hardware_check.py` | Torque OFF 진단 |
| `tools/calibrate_motors.py` | `leap_hand_motor_calibration.py` | 영점 기록 |
| `tools/joint_test.py` | `leap_hand_joint_test.py` | 단일 관절 ±5° 시험 |
| `config/postures.yaml`의 fist 초기값 | `leap_hand_hardware_finger_test.py`의 `FINGER_TARGETS_DEGREES` | 손가락 굽힘 목표 |

fist 초기값은 손가락 테스트의 **보수적 값**을 쓴다 (검지/중지/약지 MCP 55° · PIP 60° · DIP 40°, 엄지 CMC 35° · MCP 40° · IP 35°). `rps/postures.py`의 rock(75/85/65)은 더 깊어서 1차에서는 쓰지 않는다. 값은 코드가 아닌 yaml로 둔다.

**이식하지 않음**: MediaPipe, MuJoCo, RL 정책, 부스 앱, 가위바위보, 모델 파일, 개인 보정 데이터.

## 7. 입력 소스

### KeyboardSource
- 키: `space` 한 개로 open ↔ fist 토글, `q` 종료. 토글하면 목표가 바뀌고 실제 움직임은 기존 속도 제한(120°/s)과 보간이 부드럽게 만든다.
- 터미널 raw 입력 사용. 하드웨어 첫 검증용.

### Ros2LeaderSource
- `/leader/joint_trajectory`(`trajectory_msgs/JointTrajectory`)를 구독한다.
- `joint_names`에서 `rh_r1_joint`의 인덱스를 **이름으로** 찾고(순서에 의존하지 않음), `points[0].positions`의 값을 읽는다.
- `leader_gripper.yaml`의 `open_value`, `closed_value`로 0~1 정규화 후 clip. 이 두 값은 부호 반전과 offset 0.2가 이미 적용된 토픽 값 기준으로 **실측**해서 채운다 (`ros2 topic echo`로 펴짐/쥠 값 기록).
- 관절 이름이 없거나 points가 비면 Reading을 만들지 않는다 (stale로 처리됨).

## 8. 안전

기존 컨트롤러 기능을 그대로 유지한다: 전류 300 mA, 관절 속도 120°/s, 명령 간격 제한 0.1 s, 500 ms 버스 워치독, 예외 시 Torque OFF, 관절 범위 clip.

추가:
- **stale 감시**: 마지막 Reading 이후 `stale_timeout` (기본 0.5 s) 초과 시 마지막 명령 유지 → `release_timeout` (기본 3 s) 초과 시 open으로 천천히 복귀
- **시작 시 open 자세 기준**: 첫 Reading은 현재 위치에서 목표까지 기존 속도 제한으로 접근 (점프 금지)
- **--dry-run**: 드라이버 대신 목표값만 로그에 출력 (하드웨어 없이 파이프라인 검증)
- fist 자세는 연결 후 첫 동작에서 반드시 yaml의 보수적 값으로 시작
- 시험 중 5V 전원을 즉시 차단할 수 있어야 한다 (기존 절차 유지)

## 9. 설정과 Git 관리

- `postures.yaml`, `leader_gripper.yaml`: 추적한다.
- `hardware_motors.yaml` (개인 장비 보정값): **gitignore**, 예시 파일만 추적한다.
- `third_party/`는 서브모듈만 둔다.

## 10. 환경

- User PC: Ubuntu 24.04, ROS 2 Jazzy 설치됨. `python -m venv --system-site-packages`로 `rclpy`와 `dynamixel-sdk`를 함께 사용한다.
- 기존 레포 requirements의 `numpy==2.5.2`는 시스템 `rclpy`와 충돌할 수 있다. 이식하는 코드는 numpy만 필요하므로 버전을 고정하지 않는다 (확인 필요).
- Robot PC용 레포를 컨테이너에 배포하는 방법은 레포를 만들 때 정한다 (13절).

## 11. 테스트 전략

**하드웨어 없이 (자동)**
- `retarget`: scalar 0 → open, 1 → fist, 0.5 → 중간. 범위 밖 입력 clip.
- `Ros2LeaderSource`의 파싱 로직: 관절 순서가 바뀐 메시지, `rh_r1_joint` 누락, 빈 points.
- `safety`: 시간 주입(fake clock)으로 stale → hold → release 전이.
- `leap_v1`: 기존 컨트롤러가 지원하는 `sdk_module` 주입으로 fake SDK 테스트 (원본 테스트 중 필요한 것만 이식).
- 파이프라인: fake source + fake driver로 end-to-end.

**하드웨어 (수동, 체크리스트)**: 12절.

## 12. 내일 순서와 완료 기준

1. 사전: User PC에서 `ros2 topic echo /leader/joint_trajectory` (`ROS_DOMAIN_ID=30`)로 7관절 값 확인, 펴짐/쥠 값 기록
2. 사전: `/dev/ttyUSB0` 권한과 FTDI `latency_timer` 설정
3. Robot PC: 그리퍼 제거 → 공식 `omy_ai.launch.py` 실행(3절). 실패하면 `omy-leap-bringup` 레포로 전환 → leader 텔레옵 확인
4. LEAP 단독: `check_hardware` (Torque OFF) → `calibrate_motors` → `joint_test` ±5°
5. 키보드로 open ↔ fist
6. leader 그리퍼 → LEAP 연동

**완료 기준**
- 팔 텔레옵이 그리퍼 없이 정상 동작한다.
- 키보드로 LEAP이 열리고 닫히며, 어떤 예외에도 Torque OFF가 된다.
- leader 그리퍼를 쥐면 LEAP이 닫히고 펴면 열린다. 토픽을 끊으면 3초 뒤 열린다.

## 13. 열린 질문

1. Robot PC용 레포를 만들 시점과 이름/공개 범위. 공식 launch가 실패한 뒤에 만들어도 된다. 만들면 확인할 것: Robot PC의 인터넷 접근, 컨테이너 안 워크스페이스/볼륨 경로, `ros2 pkg prefix open_manipulator_bringup` 위치.
2. 가상 그리퍼(mock)를 쓸 때 follower URDF에 남는 그리퍼 링크의 시각화/충돌 영향 (1차 범위에선 무시 가능, RViz 확인 시 재검토).
3. LEAP Hand 5V 전원과 USB 연결 위치 (OMY 팔 위로 케이블 배선 시 간섭).
4. (결정됨) 키보드는 `space` 토글. 
5. 이후 URDF에 LEAP Hand 모델을 넣을 때를 대비해, 엔드이펙터 부분(`rh_p12_rn_a` 링크, end unit)을 `omy_f3m_no_gripper.urdf.xacro` 안에서 별도 include 블록으로 분리해 둔다.
