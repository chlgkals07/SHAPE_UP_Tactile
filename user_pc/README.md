# leap_teleop (User PC)

LEAP Hand v1을 키보드, OMY leader 그리퍼 또는 Manus 글러브로 구동한다.
설계: `../docs/superpowers/specs/2026-10-08-leap-omy-teleop-design.md`, Manus: `../docs/superpowers/specs/2026-10-27-manus-leap-retargeting-design.md`
10/09 실물 검증 기록: `../docs/field-test/2026-10-09-omy-leap-field-test.md`, `2026-10-09-results.md`

이 문서가 실물 시험의 **최종 절차**다. 위에서 아래로, 단계마다 통과 조건을 만족해야 다음으로 간다.

## 전체 흐름

| 단계 | 하는 일 | 통과 조건 |
|---|---|---|
| 0 | 셸 준비, 테스트 | `pytest` 전부 통과 |
| 1 | LEAP 단독 준비 (포트, 영점, 관절 시험, 키보드) | 키보드 `space`로 펴기/쥐기, 부딪힘 없음 |
| 2 | 팔 + leader 그리퍼로 LEAP 열고 닫기 (Manus 없음) | 팔이 따라오고, 트리거로 손이 열리고 닫힌다 |
| 3 | 2를 끄고 Manus 단독 (팔 없음) | dry-run 후 LEAP이 글러브를 따라간다 |
| 4 | Manus + 팔 | 팔은 leader, 손은 글러브로 동시에 움직인다 |
| 5 | Cyclo 기록 | `--publish`로 `/leap/*`가 나가고 bag에 팔·손·카메라가 같이 들어간다 |

팔은 Robot PC의 `omy_ai`가, 손은 User PC의 `leap_teleop`이 따로 구동한다. 두 프로세스는 서로 독립이다.
Cyclo 기록은 5단계에서 `--publish`를 붙여 한다 (구현됨, 실물 미검증). 설계: `../docs/superpowers/specs/2026-10-29-ros-data-interface-design.md`.

## 구성
- **Robot PC**: OMY 내부 PC (컨테이너 `open_manipulator`). `zenohd`, `omy_ai`.
- **User PC**: LEAP USB(`/dev/ttyUSB0`)가 꽂힌 PC. `leap_teleop`.
- **Manus 글러브**: SDK ROS 2 노드(`manus_ros2`)가 도는 PC에서 `/manus_glove_0` 토픽을 낸다. 이 PC는 Ubuntu 22.04 + ROS 2 Humble이다. `leap_teleop`을 같은 PC에서 돌리면 별도 설정이 필요 없고, 다른 PC면 두 PC가 같은 ROS 토픽을 볼 수 있어야 한다(`ROS_DOMAIN_ID`, DDS/zenoh 설정).
- Manus 노드는 Integrated 모드로 고정이고, 라이선스에 `integrated` 기능이 있어야 한다 (없으면 "SDK Integrated license" 에러).

## 안전 (매 단계 공통)
- LEAP 5V 전원을 즉시 차단할 수 있어야 한다. 시험 중 손가락 주변에 손·케이블을 두지 않는다. LEAP Hand v1(16모터) 전용이다.
- LEAP 5V는 **항상 손을 편 상태에서 켠다.**
- `omy_ai`는 launch 즉시 움직인다. 작업 공간을 비운다. 팔이 움직이는 동안 손은 주먹(`--safe-pose fist`)으로 둔다.
- 팔 텔레옵 중에는 **leader를 손으로 잡고** 있는다 (10/09에 leader가 갑자기 튄 적이 있다).
- 이상하면 먼저 5V를 끊고, 다음에 `Ctrl+C`.

## 0. 준비
`dynamixel-sdk`는 `ros-jazzy-dynamixel-sdk`라서 **ROS를 source 해야** 시스템 `python3`에서 import 된다 (Humble이면 `ros-humble-dynamixel-sdk`). source 하지 않은 셸에서는 `ModuleNotFoundError: dynamixel_sdk`가 난다. 둘 중 하나로 실행한다.

```bash
cd user_pc
# A) 시스템 파이썬 + ROS (leader·Manus 구동에 필요)
source /opt/ros/<jazzy|humble>/setup.bash && export PYTHONPATH="src:$PYTHONPATH" && PY=python3
# B) .venv (dynamixel-sdk 포함, 키보드·도구 전용)
export PYTHONPATH=src && PY=.venv/bin/python

$PY -m pytest -q                 # 하드웨어 없이 전부 통과해야 한다
```
`pip`를 쓸 수 있으면 `pip install -e ".[dev,hardware]"` 후 `leap-teleop` 명령을 쓸 수 있다. 아래에서는 `$PY -m leap_teleop.cli`로 쓴다. 명령은 줄이 잘리지 않게 한 줄로 붙여 넣는다.
`assets/leap_hand_right.urdf`를 소스 트리에서 읽으므로 `PYTHONPATH=src` 또는 `pip install -e`로 실행한다 (`pip install .`은 안 됨).

## 1. LEAP 단독 준비 (건너뛰지 않는다)
`config/hardware_motors.yaml`이 이미 있고 이번에도 5V를 편 손으로 켰다면 3~4는 건너뛰어도 된다.

1. 포트 권한과 지연 설정 (`/dev/ttyUSB0`)
   ```bash
   sudo usermod -aG dialout $USER   # 이후 재로그인, 또는 임시로: sudo chmod 666 /dev/ttyUSB0
   echo 1 | sudo tee /sys/bus/usb-serial/devices/ttyUSB0/latency_timer
   ```
2. Torque OFF 연결 진단 (ID 0~15, 오류 0 확인)
   ```bash
   $PY -m leap_teleop.tools.check_hardware --port /dev/ttyUSB0
   ```
3. 편 손 영점 기록. **손을 편 채 LEAP 5V를 껐다 켠 다음**, 편 자세로 고정하고 `RECORD` 입력. `config/hardware_motors.yaml`에 저장한다 (gitignore됨). 다시 잡을 때는 `--force`.
   ```bash
   $PY -m leap_teleop.tools.calibrate_motors --port /dev/ttyUSB0 --output config/hardware_motors.yaml
   ```
   - 모터가 모드 5에서 회전수를 누적하므로, 껐다 켜지 않으면 영점이 한 바퀴 밖(예: 629°)으로 기록될 수 있다. 그러면 다음 전원 투입 때 360° 어긋난다. 기록 후 `open_motor_radians`가 모두 0~6.283인지 본다.
4. 단일 관절 +5° 저속 시험 (관절마다 `MOVE` 입력). 펴지는 방향으로 움직이는 관절은 `config/hardware_motors.yaml`에서 `sign: -1`로 고치고 그 관절만 다시 시험한다.
   ```bash
   for j in index_mcp_flex index_pip_flex index_dip_flex middle_mcp_flex middle_pip_flex middle_dip_flex \
            ring_mcp_flex ring_pip_flex ring_dip_flex thumb_cmc_flex thumb_mcp_flex thumb_ip_flex; do
     echo "=== $j ==="; $PY -m leap_teleop.tools.joint_test --port /dev/ttyUSB0 --joint $j --delta 5 --motor-calibration-file config/hardware_motors.yaml || break
   done
   ```
   `outside the safe range`면 `--delta -5`로 시험한다.
5. 파이프라인만 확인 (하드웨어 없음): `$PY -m leap_teleop.cli --dry-run`
6. 키보드로 실물 구동: `$PY -m leap_teleop.cli` — `space`로 open/fist 토글, `q`로 종료
   - `fist`는 완전히 쥐는 값(손가락 90/100/80°, 엄지 60/75/70°)이다. 처음엔 한 번만 눌러 손가락끼리 부딪히지 않는지 본다. 크거나 작으면 `config/postures.yaml`의 `fist` 값을 조금씩 조정한다.

## 2. 팔 + leader 그리퍼로 LEAP 열고 닫기
Manus 없이 팔, zenoh, LEAP 구동 경로가 정상인지 먼저 확인한다. 이 단계가 안 되면 3으로 가지 않는다.

User PC 셸 (A 방식만 가능, rclpy가 필요하다):
```bash
source /opt/ros/<jazzy|humble>/setup.bash
export ROS_DOMAIN_ID=30 RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_CONFIG_OVERRIDE='mode="client";connect/endpoints=["tcp/<ROBOT_IP>:7447"]'   # 44B1050: 10.42.0.241
export PYTHONPATH="src:$PYTHONPATH"
```
1. **Robot PC 터미널 A (zenohd)**: User PC에서 ssh로 들어가 컨테이너에서 `zenohd`를 띄운다. 종료하지 않는다.
   ```bash
   ssh root@<omy-...local>                       # OMY 호스트 이름. 아래 두 줄은 ROBOT PC 호스트에서
   cd /data/docker/open_manipulator && ./docker/container.sh start && ./docker/container.sh enter
   export ROS_DOMAIN_ID=30 && zenohd
   ```
   User PC에서 `ros2 topic list`가 에러 없이 나오면 연결된 것이다 (`leap_topics`로도 된다).
2. leader 그리퍼 값: 편 상태와 쥔 상태에서 `ros2 topic echo /leader/joint_trajectory --field points`의 7번째 값(`rh_r1_joint`)을 `config/leader_gripper.yaml`의 `open_value` / `closed_value`에 넣는다. (현재 임시값 0.0 / 1.0. 10/09 편 상태 실측 약 0.197)
3. dry-run으로 로그 확인: 트리거를 쥐고 펼 때 값이 0과 1 사이에서 따라가야 한다.
   ```bash
   python3 -m leap_teleop.cli --source leader --safe-pose fist --dry-run
   ```
4. 손을 주먹으로 대기시킨 뒤 **Robot PC 터미널 B (omy_ai)**를 띄운다. 새 터미널에서 ssh로 들어가 같은 컨테이너에 enter한다. 팔이 즉시 움직이니 작업 공간을 비우고 비상 정지 수단을 확인한다. omy_ai를 켤 때·팔을 크게 옮길 때는 leader 그리퍼를 쥔 채로 둔다.
   ```bash
   ssh root@<omy-...local>
   cd /data/docker/open_manipulator && ./docker/container.sh enter
   export ROS_DOMAIN_ID=30
   ros2 launch open_manipulator_bringup omy_ai.launch.py     # 초기 이동·동기화가 끝날 때까지 기다린다
   ```
5. 실물:
   ```bash
   python3 -m leap_teleop.cli --source leader --safe-pose fist
   ```
   주먹 쥔 채 `[teleop] waiting` → 토픽이 들어오면 `[teleop] live`.
6. 확인: (a) 팔을 천천히 움직이면 follower가 따라온다 (b) 트리거를 열고 닫으면 LEAP이 열리고 닫힌다 (c) 팔을 움직이면서 동시에 열고 닫아도 서로 간섭이 없다.
7. 종료: Robot PC `omy_ai` `Ctrl+C` (팔 받치기) → User PC `Ctrl+C` → `zenohd`는 3, 4단계까지 그대로 둔다.

토픽이 0.5초 끊기면 마지막 자세를 유지하고, 3초 끊기면 안전 자세로 간다. 안전 자세는 첫 입력 전(`waiting`)에도 쓰며 기본은 편 손이다. `Ctrl+C`로 종료하면 Torque OFF 후 종료한다.

## 3. Manus 글러브 단독 (팔 없음)
2를 종료하고, LEAP 5V를 **편 손으로** 껐다 켠다 (모터 회전수 누적 초기화).
손가락은 affine(편 손~주먹 비율), 엄지는 `--thumb ik`(기본: BiDex처럼 엄지 끝 + IP 관절 두 점 IK) 또는 `--thumb affine`.
근거: `../docs/superpowers/specs/2026-10-28-manus-leap-thumb-ik-rationale.md`. A 방식(ROS source)으로 실행한다.

### 3-1. SDK 노드와 메시지 확인 (처음 한 번)
글러브를 착용하고 Manus PC에서 `manus_ros2` 워크스페이스를 빌드·source한 뒤 노드를 띄운다 (패키지 `manus_ros2`, 실행 파일 `manus_data_publisher`, `third_party/manus/ROS2 package`의 CMakeLists에서 확인).
빌드는 처음 한 번만 한다. 동글 접근용 udev 규칙(`third_party/manus/70-manus-hid.rules`)이 `/etc/udev/rules.d/`에 있어야 한다.
```bash
source /opt/ros/<humble|jazzy>/setup.bash
cd "<repo>/third_party/manus/ROS2 package" && colcon build          # 처음 한 번
source install/setup.bash                     # manus_ros2_msgs. 이 경로를 LEAP_MANUS_WS로 export하면 leap_* 함수가 자동 source
ros2 run manus_ros2 manus_data_publisher      # 별도 셸. 오른손을 /manus_glove_right로 고정하려면 -p glove_topic_template:=manus_glove_{side}
ros2 topic list | grep -i manus
ros2 topic echo /manus_glove_0 --once > echo.txt
```
코드가 `ManusDataPublisher.cpp` 소스에서 읽어 가정한 값 (2026-11-03). 실제 echo로 **아래 세 가지를 확인**한다.
- **손목** raw node가 `chain_type=Hand`, `joint_type=Invalid`인가 (`sources/manus.py`의 `KEYPOINT_NODES["wrist"]`)
- **엄지**에 `joint_type=DIP` 노드가 있는가 (`thumb_ip`). 없으면 키포인트가 빠져 엄지가 조용히 affine으로 돈다.
- **ergonomics 단위**가 도(°)인가.

이름 체계: ergonomics는 손 방향 접두어 없이 `ThumbSpread`, `ThumbCMCStretch`, `ThumbMCPStretch`, `ThumbIPStretch`, `IndexSpread`, `IndexMCPStretch`, `IndexPIPStretch`, `IndexDIPStretch` … (`types.py`의 `HUMAN_ANGLE_NAMES` 20개). raw node의 joint_type은 `MCP/PIP/IP/DIP/TIP`이고 손가락의 MCP 관절 위치는 `PIP` 노드다.
토픽 이름(기본 `/manus_glove_0`, 왼손/오른손 순서는 처음 발행된 순)을 바꿨다면 `config/manus_leap.yaml`의 `topic`과 `--glove-side Left|Right`를 맞춘다.
노드는 120 Hz로 마지막 값을 반복 발행하고 timestamp가 없다. ergonomics가 0.5초 이상 완전히 같으면 끊김으로 보고 hold한다 (`FROZEN_AFTER_S`).
dry-run용으로 편 손 → 주먹 → pinch를 녹화해 둘 수 있다:
```bash
ros2 bag record /manus_glove_0 -o manus_open_fist_pinch
```

### 3-2. 글러브 캘리브레이션 (사용자마다)
LEAP 없이 한다. 결과 `config/manus_calibration.yaml` (gitignore).
```bash
$PY -m leap_teleop.tools.calibrate_manus           # 편 손 Enter → 주먹 Enter. 다시 잡을 때 --force
```
마지막 줄 `fist thumb, mm in front of palm`에서 두 값의 부호가 다르면(WARNING) `config/manus_leap.yaml`의 `thumb_ik.flip_normal`을 바꾸고 다시 한다.

### 3-3. dry-run
글러브를 착용하고 (또는 `ros2 bag play manus_open_fist_pinch`를 다른 셸에서 틀고):
```bash
$PY -m leap_teleop.cli --source manus --dry-run
```
`[teleop] live`가 되고 손을 움직일 때 값이 바뀌어야 한다. `--thumb ik`일 때 로그가 `affine`으로 떨어지면 키포인트를 못 찾은 것이다 (3-1의 손목·엄지 노드).

### 3-4. LEAP 실물
```bash
$PY -m leap_teleop.cli --source manus --safe-pose fist --thumb affine
```
편 손, 주먹, 손가락 벌리기, 엄지 순서로 천천히. 손가락 방향이 반대면 `side_gain`(측면) 또는 `joint_map`을, 엄지가 이상하면 먼저 `--thumb affine`으로 대응표를 맞춘 뒤 `--thumb ik`로 바꾼다.
글러브를 벗거나 노드를 끄면 hold → release 되는지 일부러 확인한다.

### 3-5. pinch 시험 (affine vs IK 비교)
`--thumb affine`과 `--thumb ik` 각각으로 엄지 끝–검지/중지/약지 끝 붙이기, 펜·작은 블록 집기. 결과를 `docs/field-test/`에 10/09 형식으로 남긴다. IK에서 손끝 틈이 남으면 pinch snap을 추가한다 (spec 7절).

## 4. Manus + 팔
1. 2의 1~4번을 반복한다 (`zenohd`가 살아 있으면 그대로). 손은 주먹으로 대기시킨다.
2. User PC:
   ```bash
   python3 -m leap_teleop.cli --source manus --safe-pose fist --thumb ik
   ```
3. 팔은 leader를 손으로 움직이고, 손은 글러브로 움직인다. leader 트리거는 LEAP에 영향이 없다 (`--source manus`이므로). leader 트리거 모터 제거는 `OMY_Tactile_Robot_PC`에서 따로 한다.
4. 확인: 팔을 움직이는 중에도 손이 글러브를 따라가는가, 글러브를 벗으면 hold → release 되는가. 가능하면 물체 하나를 집어 본다.
5. 종료: Robot PC `omy_ai` `Ctrl+C` (팔 받치기) → User PC `Ctrl+C` → `zenohd` `Ctrl+C` → LEAP 5V OFF.

## 5. Cyclo 기록
4와 같은 명령에 `--publish`를 붙이면 `leap_teleop`이 기록용 토픽을 낸다 (rclpy 필요, 제어 경로와 무관: 발행이 실패해도 손은 멈추지 않는다).

| 토픽 | 타입 | 내용 |
|---|---|---|
| `/leap/joint_command` | `JointState` | LEAP에 실제로 보낸 명령 (rad). Cyclo `action.hand` |
| `/leap/joint_states` | `JointState` | LEAP 실측 위치(rad)·속도(rad/s)·전류(mA). `observation.state.hand` |
| `/leap/human_hand` | `JointState` | Manus ergonomics 원본 20개 (**도**, 변환 안 함) |
| `/leap/human_keypoints` | `PoseArray` | 키포인트 8개 (`KEYPOINT_NAMES` 순서, 글러브 frame, m). 없으면 안 나감 |
| `/leap/teleop_mode` | `String` | `waiting/live/hold/release`. 변경 시 + 1 Hz |

관절 이름은 `leap_` + 관절 이름 (예: `leap_index_mcp_flex`). `--dry-run`에서는 피드백이 없어 `/leap/joint_states`가 나가지 않는다.
1. `config/omy_f3m_leap_config.yaml`을 `cyclo_intelligence/shared/shared/robot_configs/`에 복사한다. 카메라 토픽은 세화형 실행표 B6의 실제 값으로 바꾼다 (현재 미확인 값).
2. 카메라 3대를 켜고, `leap_teleop --publish ...`를 실행한 뒤 `ros2 topic hz /leap/joint_states /leap/joint_command`로 50 Hz 근처인지 본다. 16모터 피드백 읽기가 tick 예산을 넘으면 `joint_states`가 느려진다 (넘으면 발행 주기를 낮춘다).
3. Cyclo UI에서 로봇 타입 `omy_f3m_leap`을 선택하고 에피소드 하나를 녹화한다.
4. 확인: bag에 `/joint_states`, `/leader/joint_trajectory`, `/leap/*`, 카메라가 모두 들어갔는가, `header.stamp`와 bag 수신 시각이 크게 어긋나지 않는가 (크면 두 PC를 chrony로 맞춘다).

## 단축 함수 (선택)
긴 명령은 `scripts/leap_aliases.sh`의 함수로 줄일 수 있다. `source`한 셸에서 ROS, zenoh, `PYTHONPATH`를 한 번에 잡고 `user_pc/`로 이동한다. 인자는 그대로 전달된다.
```bash
source <repo>/user_pc/scripts/leap_aliases.sh          # ~/.bashrc에 넣어도 된다
export LEAP_ROS_DISTRO=jazzy OMY_ROBOT_IP=10.42.0.241 LEAP_MANUS_WS="<repo>/third_party/manus/ROS2 package"   # 필요한 것만
leap_check                  # 연결 진단 (1단계)
leap_leader --dry-run       # 2단계: leader 그리퍼 -> LEAP 로그만. 실물은 --dry-run 없이
leap_glovecal --force       # 3-2: 글러브 캘리브레이션
leap_manus --dry-run        # 3-3. 실물은 leap_manus --thumb affine, 이후 leap_manus
leap_record                 # 5단계: leap_manus --publish
leap_topics                 # 토픽 확인
```
Robot PC 쪽(`zenohd`, `omy_ai`)은 이 함수에 포함되지 않는다. 위 2단계의 ssh 명령을 쓴다.

## 켜는 순서 / 끄는 순서
- 켜기: `LEAP 5V (편 손)` → `Manus 노드` → `zenohd` → `omy_ai` → `leap_teleop`
- 끄기: `leap_teleop` → `omy_ai` (팔 받치기) → `zenohd` → `Manus 노드` → `LEAP 5V`. 팔을 받친 뒤에 `omy_ai`를 끈다.

## 조정 값
모두 `config/manus_leap.yaml`(추적, 공통)에 있다: 토픽, 대응표, `side_gain`, `fist_override_deg`(엄지 12번 주먹 목표), 결합 제한, IK 가중치, One-Euro, URDF 영점 offset.

## 아직 안 된 것
- Cyclo 기록(5단계)은 코드와 config만 있고 Cyclo 컨테이너에서 변환·학습까지는 확인 전이다. 카메라 토픽 경로, `rh_r1_joint` 제외(arm 6관절), PC 간 시계는 실물에서 본다.
- 3-1의 세 항목(손목 joint_type, 엄지 DIP 노드, 단위)과 `libManusSDK-amd64.so`만으로 Integrated 모드가 되는지는 실물 확인 전이다.

## 문제 해결
- `error: ... not found. Run calibrate_motors`: 1의 3번을 먼저 한다 (공칭 영점으로 움직이지 않는다).
- `Missing or unresponsive DYNAMIXEL IDs`: 5V 전원, USB 케이블, Dynamixel Wizard가 포트를 점유 중인지 확인한다.
- `No module named 'dynamixel_sdk'`: ROS를 source 하지 않은 셸이다. 0의 A 또는 B로 실행한다.
- 토픽이 안 보임 / `[teleop] waiting`에서 안 바뀜 (leader): User PC에서 `ros2 topic info /leader/joint_trajectory`의 Publisher count를 본다. 0이면 Robot PC에서 omy_ai를 띄운 셸의 `echo $RMW_IMPLEMENTATION $ROS_DOMAIN_ID`가 `rmw_zenoh_cpp 30`인지 확인한다. 컨테이너 `.bashrc`가 로드되지 않은 셸이면 둘 다 빠져 있다(`zenohd: command not found`도 같은 원인). export 후 다시 띄운다.
- 그 외: 두 PC가 같은 네트워크인지, 포트 7447, `ZENOH_CONFIG_OVERRIDE`, Robot PC `zenohd` 실행 여부 순으로 확인한다.
- `No module named 'manus_ros2_msgs'`: Manus SDK의 ROS 2 워크스페이스를 source 하지 않았다 (`source <manus_ws>/install/setup.bash`).
- `[teleop] waiting`에서 안 바뀜 (Manus): ① 노드가 도는지, `ros2 topic echo`로 값이 오는지 ② 토픽 이름(`manus_leap.yaml`), `--glove-side`(Left/Right) ③ ergonomics 이름이 `HUMAN_ANGLE_NAMES`와 맞는지(하나라도 빠지면 reading을 버린다) ④ 글러브가 멈춘 값만 반복 중이 아닌지(0.5초 이상 동일하면 버린다).
- 노드 시작 시 "SDK Integrated license" 에러: 라이선스에 `integrated` 기능이 없다.
- `No module named rclpy`: `PYTHONPATH=src`가 ROS 경로를 덮어쓴 것이다. `PYTHONPATH="src:$PYTHONPATH"`로 쓴다.
