# HX5-D20 × OMY 촉각 보조 텔레오퍼레이션 준비

이 문서는 OMY-F3M follower의 RH-P12-RN 그리퍼를 제거하고 HX5-D20을 장착해, OMY-L100 leader의 그리퍼 입력으로 손을 연속 개폐하기 위한 준비 및 현장 검증 순서다. **HX5 장착·통전·실물 구동은 아직 검증하지 않았다.** 2026-10-09의 LEAP Hand 실물 성공은 leader 입력과 OMY 팔의 선행 근거이며, HX5의 기구·전기 호환성을 입증하지 않는다.

표기: **[공식]** ROBOTIS 문서 또는 이 브랜치의 공식 `robotis_hand` 소스, **[실측 LEAP]** [10/09 현장 결과](field-test/2026-10-09-results.md), **[계획]** 이 통합의 설계·검증 항목, **[미검증]** HX5 실물에서 확인해야 할 사항.

## 준비된 소프트웨어와 필요한 부품

| 항목 | 상태와 근거 |
|---|---|
| ROBOTIS Hand ROS 2 Jazzy 소스 | [공식 저장소](https://github.com/ROBOTIS-GIT/robotis_hand)의 `jazzy`를 [`third_party/robotis_hand`](../third_party/robotis_hand)에 서브모듈로 고정했다 (`d8399e606207e5dbf5beda0f433c435bac31ee1f`). bringup, 설명 모델, pressure broadcaster, playground 데모를 포함한다. |
| 실행 환경 | [공식 Setup Guide](https://docs.robotis.com/docs/systems/hx5_d20/quick_start_guide/setup_guide/)는 Linux 호스트의 Git·Docker Engine과 Ubuntu 24.04/ROS 2 Jazzy 컨테이너를 요구한다. [`docker-compose.yml`](../third_party/robotis_hand/docker/docker-compose.yml)은 `robotis/robotis-hand:1.0.2`를 지정한다. 이 이미지는 이 PC에 이미 있었으며 내부 `robotis_interfaces`·HX5 bringup을 확인했다. |
| 손과 연결 부품 | 실제 좌/우 모델에 맞는 HX5-D20 1대, U2D2 1대, U2D2 Power Hub 1대, **24V SMPS**, RS-485 **4핀 Robot Cable 2개**, USB 케이블 및 장착 부품이 필요하다. [공식 Setup Guide](https://docs.robotis.com/docs/systems/hx5_d20/quick_start_guide/setup_guide/) 기준이다. 부품 보유·케이블 길이는 현장에서 확인한다. |
| 진단 도구 | [DYNAMIXEL Wizard 2.0](https://docs.robotis.com/docs/systems/hx5_d20/quick_start_guide/dxl_wizard_guide/)은 장치 진단·설정용이다. 공식 기본 bringup에 별도 펌웨어 갱신 단계는 없다. 펌웨어 변경은 장치 상태 확인 후 필요할 때만 한다. |

서브모듈 복원과 이미지 확인에는 다음 명령을 쓴다. 이미지를 다시 받을 때는 `docker pull`만 수행하면 컨테이너와 호스트 설정을 변경하지 않는다.

```bash
git submodule update --init --recursive
docker image inspect robotis/robotis-hand:1.0.2
docker pull robotis/robotis-hand:1.0.2
```

실제 bringup 때 공식 `third_party/robotis_hand/docker/container.sh start`를 사용한다. 이 스크립트는 이미지 다운로드뿐 아니라 **`xhost +local:docker` 실행(DISPLAY가 있을 때), `/etc/udev/rules.d/99-u2d2.rules` 복사, udev 재로드·트리거, Docker Compose 기동**까지 수행한다. 따라서 소프트웨어 다운로드 단계에서 `start`를 실행하지 않는다. 스크립트와 구성은 [`container.sh`](../third_party/robotis_hand/docker/container.sh), [`docker-compose.yml`](../third_party/robotis_hand/docker/docker-compose.yml)을 참고한다.

## 그리퍼 제거와 HX5 장착: 현장 확인 필수

**[공식]** OMY-F3M은 RH-P12-RN 그리퍼를 갖고 payload 사양이 3 kg이다. HX5-D20 질량은 1,000 g ±2%, 정격 24V, peak current 2.6 A다. 두 수치만으로 장착 가능하다고 결론낼 수 없다. 별도 어댑터의 질량, 손의 무게중심에 따른 손목 모멘트, 카메라·주변 구조와의 간섭을 확인한다. [OMY 사양](https://docs.robotis.com/docs/systems/omy/specifications/hardware/), [HX5 사양](https://docs.robotis.com/docs/systems/hx5_d20/specifications/hardware/).

1. OMY를 안전한 자세에 두고 팔과 HX5 전원을 끈 뒤 기존 그리퍼를 분리한다. 노출된 OMY end-unit 커넥터를 절연·고정한다. LEAP 장착 때 공식 `omy_ai`가 그리퍼 없이 동작한 [현장 기록](field-test/2026-10-09-results.md)은 있으나 HX5의 새 질량·관성에 대한 확인은 아니다.
2. [OMY-F3M STEP/DWG/PDF](https://docs.robotis.com/docs/systems/omy/specifications/hardware/)와 [HX5-D20-MRT/MLT STEP/DWG/PDF](https://docs.robotis.com/docs/systems/hx5_d20/resources/open_source/)에서 손목 플랜지와 HX5 베이스의 홀 패턴, 체결 깊이, 좌우 방향을 비교하고 실제 부품으로 대조한다. **공식 문서에서 OMY↔HX5 직결 어댑터의 규격 또는 호환 장착 절차를 확인하지 못했다.** 맞지 않으면 설계·검증된 어댑터가 필요하다.
3. 손가락 전체 움직임, OMY 관절 전 범위, D405 카메라 시야에서 충돌을 확인한다. 24V/RS-485 케이블은 움직이는 관절과 손가락에서 떨어뜨리고 손목 근처에 스트레인 릴리프를 둔다. 전 범위에서 당김·꼬임·눌림이 없어야 한다. **[미검증]**

## 전원·통신 배선

공식 배선은 **24V SMPS → U2D2 Power Hub → 4핀 RS-485 케이블 → HX5 4핀 포트**, 그리고 **U2D2 USB → 손 제어 PC**다. U2D2 자체는 모터 전원을 공급하지 않는다. 기존 OMY 그리퍼 케이블이나 전원을 규격·핀배열 검증 없이 HX5에 재사용하지 않는다. 케이블 연결·분리는 전원을 끈 상태에서 한다. [HX5 Setup Guide](https://docs.robotis.com/docs/systems/hx5_d20/quick_start_guide/setup_guide/), [U2D2 Power Hub](https://docs.robotis.com/docs/parts/interface/u2d2_power_hub/).

HX5는 기본 4 Mbps RS-485/DYNAMIXEL Protocol 2.0을 쓴다. 공식 bringup의 기본 포트는 `/dev/ttyUSB0`이고 `port_name` launch 인자로 바꿀 수 있다. 실제 연결 시 U2D2의 장치 경로와 권한을 확인하고 OMY·기존 USB 시리얼 장치와 혼동하지 않는다. [HX5 하드웨어 사양](https://docs.robotis.com/docs/systems/hx5_d20/specifications/hardware/), [bringup launch](../third_party/robotis_hand/robotis_hand_bringup/launch/hx5_d20_left.launch.py).

## ROS 2 데이터 경로와 제어 주체

| 출처 → 대상 | 메시지·의미 |
|---|---|
| OMY leader → HX5 텔레옵 | `/leader/joint_trajectory`의 `trajectory_msgs/msg/JointTrajectory`에서 7번째 `rh_r1_joint`를 읽는다. [LEAP 현장 결과](field-test/2026-10-09-results.md)에서 열린 값은 약 **0.197 rad**, 닫힌 끝값은 **미측정**이다. HX5 실물 명령 전 양 끝값을 다시 측정한다. |
| HX5 텔레옵 → HX5 hand controller | 왼손: `/leader/joint_trajectory_command_broadcaster_left_hand/joint_trajectory`; 오른손: 대응하는 `_right_hand/joint_trajectory`. `trajectory_msgs/msg/JointTrajectory`에 해당 손의 `finger_l_joint1`–`20` 또는 `finger_r_joint1`–`20`을 담는다. [ROBOTIS software overview](https://docs.robotis.com/docs/systems/hx5_d20/specifications/software/). |
| HX5 → 텔레옵 | `/joint_states`와 왼손 `/left_hand/finger_pressures` 또는 오른손 `/right_hand/finger_pressures`. 압력 타입은 `robotis_interfaces/msg/HandPressures`: `sensors[]` 안에 `sensor_name`, `pressure_names[9]`, `pressure_values[9]`가 있다. [공식 촉각 문서](https://docs.robotis.com/docs/systems/hx5_d20/resources/technical_story/tactile_feedback_grasping/). |

HX5는 다섯 손가락 각 4관절이며 그룹은 엄지 1–4, 검지 5–8, 중지 9–12, 약지 13–16, 소지 17–20이다. 공식 촉각 데모에서 왼손 엄지의 굽힘은 `joint3/4`를 **음의 방향**으로, 다른 네 손가락의 굽힘은 각 그룹의 `joint2/3/4`를 **양의 방향**으로 움직인다. 엄지 `joint2`와 다른 손가락의 벌림 `joint1`은 이 닫기 단계에서 유지한다. 이는 [데모 구현](../third_party/robotis_hand/robotis_hand_playground/src/tactile_force_controller.cpp)의 방향이며, 우리 손의 실제 장착 방향·관절 움직임은 작은 범위에서 다시 확인한다. 실제 손의 좌우에 맞는 launch를 택해야 하며, 공식 왼손 명령은 `ros2 launch robotis_hand_bringup hx5_d20_left.launch.py`이다. **launch가 초기 자세로 손을 움직인다.** [공식 Operation Guide](https://docs.robotis.com/docs/systems/hx5_d20/quick_start_guide/operation_guide/), [왼손 launch](../third_party/robotis_hand/robotis_hand_bringup/launch/hx5_d20_left.launch.py).

ROBOTIS Hand 1.0.0부터 `rmw_zenoh_cpp`가 기본이다. OMY와 손 제어 PC는 `ROS_DOMAIN_ID=30`, RMW 및 Zenoh 라우터/클라이언트 접속을 맞추고, 두 PC 사이 TCP 7447 통신과 실제 토픽 수신을 확인한다. [Zenoh 공식 문서](https://docs.robotis.com/docs/systems/hx5_d20/quick_start_guide/zenoh_communication/)와 [기존 OMY↔LEAP 현장 연결 기록](field-test/2026-10-09-results.md)을 참고한다. 이전 현장의 OMY 주소 `10.42.0.241`은 고정 주소라고 가정하지 않는다.

우리 ROS bridge는 수신 시각과 압력 메시지의 ROS timestamp를 모두 검사한다. OMY와 손 제어 PC의 시계를 동기화하고, 실제 데이터의 지연·주기(`ros2 topic hz /left_hand/finger_pressures`)를 현장에서 측정한다. 시간 차이가 크거나 압력 토픽이 끊기면 추가 닫힘을 허용하지 않는다. 공식 pressure broadcaster가 매 update마다 새 timestamp를 붙이므로 토픽 timestamp만으로 물리 센서의 정상 갱신까지 증명할 수는 없다.

### 접촉 지표와 단일 명령 발행자

HX5 손끝은 손가락마다 **3×3, 값 0–255**의 압력 배열을 낸다. 공식 `tactile_sensor.cpp`는 무접촉 baseline을 빼고 음수를 0으로 자른 뒤 EMA로 거른 아홉 값을 합쳐 `total_force`라고 부른다. **이 합과 ROS 압력값은 보정된 N 단위 힘이 아니다.** 제품의 `Max Finger Tip Force 14 N`도 이 지표의 변환계수가 아니다. 접촉 문턱값은 실물의 노이즈·물체·손가락별 데이터로 정한다. [HX5 사양](https://docs.robotis.com/docs/systems/hx5_d20/specifications/hardware/), [공식 알고리즘 설명](https://docs.robotis.com/docs/systems/hx5_d20/resources/technical_story/tactile_feedback_grasping/), [파서 코드](../third_party/robotis_hand/robotis_hand_playground/src/tactile_sensor.cpp).

공식 `tactile_force_controller` 데모는 `/grasp_start` Bool로 **IDLE → CLOSE → HOLD**를 수행하고 위 손 명령 토픽에 `JointTrajectory`를 발행한다. 연속 leader 방아쇠 경로는 leader 값을 열림↔닫힘 비율로 매핑해 **하나의 텔레옵 노드가 최종 20관절 명령을 발행**해야 한다. 접촉 피드백은 그 노드 안에서 닫힘 명령을 제한·유지하는 용도로 결합한다. 공식 데모와 우리 텔레옵을 동시에 같은 손 명령 토픽에 발행하지 않는다. `ros2_control`의 자원 중재는 **동일 컨트롤러 입력 토픽의 두 발행자 사이 우선순위를 정해 주지 않는다.** [공식 데모 소스](../third_party/robotis_hand/robotis_hand_playground/src/tactile_force_controller.cpp).

공식 데모 파라미터 파일의 `close_step=0.03 rad`, `contact_threshold=10.0`은 데모 설정값이며 실물의 안전한 보정값으로 간주하지 않는다. 특히 데모의 왼손 초기 엄지 `joint2=+1.792 rad`는 [공식 하드웨어 관절 범위](https://docs.robotis.com/docs/systems/hx5_d20/specifications/hardware/)의 `0°–90°`보다 크고, 소스 내부 관절 범위도 사양과 일부 다르다. 따라서 데모 초기 포즈를 그대로 안전한 목표값으로 재사용하지 않고, 현장 구동 전 좌우 방향과 관절 제한을 대조한다. [데모 파라미터](../third_party/robotis_hand/robotis_hand_playground/config/param.yaml), [초기 포즈 소스](../third_party/robotis_hand/robotis_hand_playground/src/tactile_force_controller.cpp).

## 단계별 현장 검증

1. **기구·전원 OFF 검사:** 실제 HX5 모델의 좌우, 어댑터 체결, 질량·무게중심·손목 모멘트, 카메라/손가락 간섭, 케이블 전 범위와 전원 차단 수단을 확인한다. 고정되지 않거나 간섭이 있으면 구동하지 않는다.
2. **HX5 단독 bringup:** OMY 팔이 움직이지 않도록 분리한 상태에서 U2D2·별도 24V 전원 및 실제 시리얼 포트를 확인한다. `zenohd`와 해당 좌/우 공식 bringup을 실행한다. 시작 시 초기 자세로 손이 움직이므로 손 주변을 비운다. `/joint_states` 20관절과 `/left_hand/finger_pressures` 또는 오른손 토픽의 다섯 센서×아홉 값을 확인한다. 무접촉 baseline과 손가락별 가벼운 접촉 반응을 기록한다.
3. **OMY leader 입력 실측:** 이전 LEAP 실험에서 확인한 `/leader/joint_trajectory`의 7번째 `rh_r1_joint`를 leader를 완전히 편 상태와 쥔 상태에서 여러 번 기록한다. **열림 약 0.197 rad는 과거 측정일 뿐이며 닫힘은 미측정**이다. 두 끝값의 방향·범위·떨림을 확정한다. `ros2 topic echo /leader/joint_trajectory --field points`를 사용할 수 있다.
4. **명령 없는 검증:** leader·HX5 토픽이 Zenoh로 보이는지 확인하고, HX5 텔레옵 CLI의 `--dry-run`에서 leader 양 끝·중간 입력, 입력 상실, 촉각 없는 경우와 접촉 발생 후 제한 동작을 확인한다. 양 끝값은 CLI의 필수 인자로 넣는다. 임시 0/1 범위로 실물에 발행하지 않는다.
5. **실물 무부하 → 부드러운 물체:** 드라이런이 통과한 뒤 손과 팔 주변을 비우고 한 손가락씩 작은 범위에서 시작한다. 이후 연속 방아쇠 개폐와 부드러운 물체 파지를 시험하면서 압력 baseline·접촉 임계값·포화·지연, 손목 케이블을 관찰한다. OMY 텔레옵 중 leader가 갑자기 튄 [기존 현장 기록](field-test/2026-10-09-results.md)이 있으므로 leader를 손으로 잡고 시험한다. 이상 동작 시 입력·모터 전원을 중단한다.

공식 MuJoCo 모델은 관절·형상 검토용이며 **실물 촉각 센서를 제공하지 않는다**. 촉각 제어 로직은 synthetic 입력으로 시험할 수 있지만, 접촉 문턱값·파지 안정성은 실제 HX5에서만 확정할 수 있다. [공식 시뮬레이션 자료](https://docs.robotis.com/docs/systems/hx5_d20/simulation/), [공식 촉각 가이드](https://docs.robotis.com/docs/systems/hx5_d20/resources/technical_story/tactile_feedback_grasping/).

### 텔레옵 실행 파일과 드라이런

이 브랜치의 [`user_pc/run_hx5_docker.sh`](../user_pc/run_hx5_docker.sh)는 공식 Docker image에 이 프로젝트의 Python 소스를 읽기 전용 마운트하고 ROS 2 bridge를 실행한다. 스크립트 자체는 HX5 bringup, U2D2 연결, 호스트 udev 변경을 하지 않는다. **실제 leader의 열린 값과 닫힌 값이 필수 인자**라 기존 LEAP용 임시 0/1을 무심코 사용하지 않는다. `--dry-run`이면 HX5 명령 토픽에 발행하지 않고 계산 결과만 표시한다.

이 PC의 호스트 ROS 2 Jazzy에는 `robotis_interfaces`가 없어 호스트 `python3`로 HX5 bridge를 직접 실행할 수 없다. 공식 Docker image에는 해당 메시지 패키지와 bringup이 포함되어 있어 위 스크립트가 그 환경을 사용한다.

브리지가 멈추거나 입력이 끊기면 새 닫힘 명령을 보내지 않는다. **이 브리지를 종료해도 공식 HX5 컨트롤러의 torque가 자동으로 꺼지지는 않는다.** 실제 비상정지·전원 차단 순서는 손/OMY 현장에서 별도로 확인하고 준비한다.

```bash
# OMY/손 컨테이너가 같은 Zenoh 라우터를 쓰도록 실제 주소를 넣는다.
export ZENOH_CONFIG_OVERRIDE='mode="client";connect/endpoints=["tcp/<OMY_IP>:7447"]'
export ROS_DOMAIN_ID=30 RMW_IMPLEMENTATION=rmw_zenoh_cpp
read -r -p 'leader open rh_r1_joint (measured): ' LEADER_OPEN
read -r -p 'leader closed rh_r1_joint (measured): ' LEADER_CLOSED

bash user_pc/run_hx5_docker.sh --side left \
  --leader-open "$LEADER_OPEN" --leader-closed "$LEADER_CLOSED" --dry-run
# 양 끝/중간/입력 끊김/촉각 값 로그를 확인한 뒤 실물 시험에서만 --dry-run 제거
```

코어의 기본 open은 공식 bringup 초기값인 **20관절 0 rad**이고, 기본 닫힘 범위는 공식 왼손 MuJoCo에서 자기접촉 없이 추종된 보수적인 작은 범위다. 공식 `tactile_force_controller`의 open 자세는 왼손 엄지 j2가 모델 한계를 벗어나 기본값으로 복사하지 않았다. 압력 예시 기본값(`contact_threshold=10`, `pressure_hard_cap=30` 원시 합)은 실물 보정값이 아니므로 접촉 시험 전에 무접촉 노이즈와 물체별 응답을 측정해 `--contact-threshold`, `--pressure-hard-cap`을 조정한다. 무접촉 상태에서 leader를 완전히 열어 30개의 압력 프레임으로 baseline을 만들기 전에는 손 명령을 발행하지 않는다. [코어](../user_pc/src/hx5_teleop/core.py), [ROS bridge](../user_pc/src/hx5_teleop/ros_bridge.py), [CLI](../user_pc/src/hx5_teleop/cli.py).

### 하드웨어 없이 수행한 검증

- 공식 [`scene_left.xml`](../third_party/robotis_hand/robotis_hand_description/mujoco/hx5_d20_rev2/scene_left.xml)을 MuJoCo 3.12.0으로 로드했다. 20개 관절과 position actuator의 이름·순서가 `finger_l_joint1..20`과 일치한다. [`test_hx5_mujoco.py`](../user_pc/tests/test_hx5_mujoco.py)의 방아쇠 0→0.5→1→0 구동은 **자기접촉 0건**, 최대 관절 추종 오차 약 **0.014 rad**, 관절 한계·명령 속도 준수를 확인했다. 이 모델에는 촉각 센서(`nsensor=0`)가 없다.
- 공식 Docker 이미지의 왼손 Gazebo launch를 일회성 컨테이너 내부에서 **서버 전용**으로 실행했다. `hand_l_controller`와 `joint_state_broadcaster`가 active였고 `/joint_states` 20관절을 확인했다. 공식 손 명령 토픽에 20관절 `JointTrajectory`(j6 목표 `+0.2 rad`, 2초)를 발행하자 j6가 `0.000000→0.199957 rad`로 추종했다. 원본 launch는 RViz/Gazebo GUI를 함께 띄워 화면 없는 컨테이너에서 OpenGL 오류로 종료하므로, **컨테이너 `/tmp`의 사본에서만** `gz_args`에 `-s`를 더하고 RViz 항목을 제거했다. 공식 소스와 호스트 설정은 바꾸지 않았다. [공식 Gazebo 절차](https://docs.robotis.com/docs/systems/hx5_d20/simulation/gazebo/), [공식 왼손 launch](../third_party/robotis_hand/robotis_hand_bringup/launch/hx5_d20_left_gazebo.launch.py).
- 공식 `robotis/robotis-hand:1.0.2` 컨테이너의 실제 `robotis_interfaces/msg/HandPressures`와 ROS 2 토픽을 사용한 [`test_hx5_ros_integration.py`](../user_pc/tests/test_hx5_ros_integration.py)는 가짜 leader·관절·압력 발행자로 **드라이런 계산과 20관절 명령 형식**을 검증했다. 컨테이너 내부 통합 시험이며 OMY나 HX5 실물에 연결한 결과가 아니다.
- **공식 Gazebo 컨트롤러와 HX5 ROS bridge의 종단 간 시험:** 같은 일회성 컨테이너에서 합성 leader·압력 메시지를 bridge에 입력하고, 공식 왼손 `hand_l_controller`로 **20관절 명령 112개**를 발행했다. `/joint_states`에서 측정한 검지 `joint6`은 방아쇠 `0 → 0.5 → 1 → 0`에 따라 `0 → 0.097716 → 0.198443 → 0.004957 rad`로 움직였다. 마지막 값은 해제 직후의 측정값이므로 정확히 0으로 수렴했다고 해석하지 않는다. 재현 절차는 [`run_hx5_gazebo_probe.sh`](../user_pc/tools/run_hx5_gazebo_probe.sh)와 [`hx5_gazebo_probe.py`](../user_pc/tools/hx5_gazebo_probe.py)에 둔다. bridge는 `JointTrajectory.header.stamp=0`으로 발행한다. 이는 [ROS 2 control Jazzy의 궤적 규약](https://control.ros.org/jazzy/doc/ros2_controllers/joint_trajectory_controller/doc/trajectory.html)에서 **지금 시작**을 뜻하며, 합성 입력의 wall clock과 Gazebo의 simulation clock을 섞어 미래/과거 시작 시각을 만드는 문제를 피한다.
- [`test_hx5_core.py`](../user_pc/tests/test_hx5_core.py)는 5×9 baseline, 접촉 손가락별 제한, 압력 목표대역 보정, 방아쇠 해제, 센서·leader 소실 및 포화 fault를 합성 입력으로 검사한다. 원시값 기준 임계와 실제 파지력은 현장에서 보정해야 한다.
- Gazebo가 관절 상한 0 rad에서 약 `1e-10 rad`의 수치 오차를 내는 경우가 있어 초기 관절 측정값에만 최대 `1e-6 rad`의 경계 허용 오차를 적용하고 명령 시 실제 모델 한계 안으로 잘라 넣는다. `1e-4 rad`처럼 더 큰 범위 초과는 계속 거부한다. [코어](../user_pc/src/hx5_teleop/core.py), [경계 시험](../user_pc/tests/test_hx5_core.py). **위 시험의 압력은 전부 합성 데이터이며 실물 HX5 촉각, 접촉력, 안정 파지는 검증하지 않았다.**

## 현재 증거와 남은 현장 작업

- **확인됨:** 공식 Jazzy 소스·Docker image tag·ROS 인터페이스·HX5/OMY 제품 사양, OMY→LEAP leader 그리퍼 텔레옵 선례, 합성 leader·압력을 사용한 공식 HX5 Gazebo 컨트롤러와 ROS bridge의 종단 간 명령·관절 추종.
- **미확인:** OMY↔HX5 마운트 호환성, 실제 장착/배선, HX5 시리얼 통신과 토픽 수신, leader 닫힘 끝값, 촉각 임계값과 물체별 파지, 완성 CLI의 실물 작동.
- **실행 전 조건:** 해당 손의 좌우 모델, 독립 24V/U2D2 배선, 하나의 손 명령 발행자, leader 양 끝값 실측, 전원 차단 수단.
