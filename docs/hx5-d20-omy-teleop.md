# HX5-D20 × OMY 촉각 보조 텔레오퍼레이션 준비

> **현재 실물 경로:** OMY 팔은 기존 `arm_controller`, HX5 왼손은 END 210 경유 Direct Mode 노드가 맡는다. 기존 손 직결 드라이버를 쓰는 `omy_hx5_hand_live.launch.py`는 계속 차단한다. [Direct Mode 준비·키보드 절차](hx5-d20-omy-direct-hand.md)를 마친 뒤 이 문서의 텔레옵 런치를 사용한다. 실물 20관절 텔레옵의 동작 검증은 아직 남아 있다.

[실행 명령어 모음](hx5-d20-run-commands.md)

이 문서는 OMY-F3M follower의 RH-P12-RN 그리퍼 대신 장착한 HX5-D20을 OMY-L100 leader의 그리퍼 입력으로 연속 개폐하기 위한 코드와 실행 순서다. 기존 그리퍼 4핀 케이블로 END 210, 손 컨트롤러 140, 첫 모터 141이 응답했고 Preset 명령으로 검지 움직임이 관찰됐다. Direct Mode의 20모터 동작, 촉각 제어, 리더 입력부터 손까지의 실물 텔레옵은 아직 검증하지 않았다. [AI Worker 공식 장착 절차](https://docs.robotis.com/docs/systems/aiworker/quick_start_guide/setup_overview/hardware/#optional-robotis-hand-installation)는 같은 4핀 케이블 재사용 사례다.

표기: **[공식]** ROBOTIS 문서 또는 이 브랜치의 공식 `robotis_hand` 소스, **[실측 LEAP]** [10/09 현장 결과](field-test/2026-10-09-results.md), **[계획]** 이 통합의 설계·검증 항목, **[미검증]** HX5 실물에서 확인해야 할 사항.

## 준비된 소프트웨어와 필요한 부품

| 항목 | 상태와 근거 |
|---|---|
| ROBOTIS Hand ROS 2 Jazzy 소스 | [공식 저장소](https://github.com/ROBOTIS-GIT/robotis_hand)의 `jazzy`를 [`third_party/robotis_hand`](../third_party/robotis_hand)에 서브모듈로 고정했다 (`d8399e606207e5dbf5beda0f433c435bac31ee1f`). bringup, 설명 모델, pressure broadcaster, playground 데모를 포함한다. |
| 실행 환경 | OMY Robot PC의 ROS 2 Jazzy 작업공간에 [이 브랜치의 `omy_hx5_bringup`](../robot_pc/README.md)을 overlay로 빌드한다. 공식 `robotis/robotis-hand:1.0.2` 이미지는 이 PC의 **소프트웨어 검증**에 사용했다. |
| 손과 연결 부품 | 왼손 HX5-D20, 장착 부품, OMY의 기존 RH-P12-RN 4핀 케이블을 확인한다. 이 케이블의 HX5 직접 재사용은 [AI Worker 공식 장착 사례](https://docs.robotis.com/docs/systems/aiworker/quick_start_guide/setup_overview/hardware/#optional-robotis-hand-installation)에 근거한 **OMY 적용 목표**이지 OMY 호환성 확인 결과는 아니다. |
| 진단 도구 | [DYNAMIXEL Wizard 2.0](https://docs.robotis.com/docs/systems/hx5_d20/quick_start_guide/dxl_wizard_guide/)은 장치 진단·설정용이다. 공식 기본 bringup에 별도 펌웨어 갱신 단계는 없다. 펌웨어 변경은 장치 상태 확인 후 필요할 때만 한다. |

서브모듈 복원과 이미지 확인에는 다음 명령을 쓴다. 이미지를 다시 받을 때는 `docker pull`만 수행하면 컨테이너와 호스트 설정을 변경하지 않는다.

```bash
git submodule update --init --recursive
docker image inspect robotis/robotis-hand:1.0.2
docker pull robotis/robotis-hand:1.0.2
```

이 작업의 실행 경로는 [Robot PC용 패키지](../robot_pc/README.md)다. 공식 Hand의 단독 USB bringup 및 이 브랜치에 있던 User PC용 HX5 Docker 실행 스크립트는 사용하지 않는다.

## 그리퍼 제거와 HX5 장착: 현장 확인 필수

**[공식]** OMY-F3M은 RH-P12-RN 그리퍼를 갖고 payload 사양이 3 kg이다. HX5-D20 질량은 1,000 g ±2%, 정격 24V, peak current 2.6 A다. 두 수치만으로 장착 가능하다고 결론낼 수 없다. 별도 어댑터의 질량, 손의 무게중심에 따른 손목 모멘트, 카메라·주변 구조와의 간섭을 확인한다. [OMY 사양](https://docs.robotis.com/docs/systems/omy/specifications/hardware/), [HX5 사양](https://docs.robotis.com/docs/systems/hx5_d20/specifications/hardware/).

1. OMY를 안전한 자세에 두고 팔과 HX5 전원을 끈 뒤 기존 그리퍼를 분리한다. 기존 4핀 케이블은 단자 배열·전원 용량·통신 경로를 확인할 때까지 분리된 상태로 안전하게 보관한다. [AI Worker 공식 절차](https://docs.robotis.com/docs/systems/aiworker/quick_start_guide/setup_overview/hardware/#optional-robotis-hand-installation)는 HX5의 종단저항을 활성화한 뒤 기존 케이블을 연결하지만, 그 브래킷 회전·배선 절차를 OMY에 그대로 적용하지 않는다. LEAP 장착 때 공식 `omy_ai`가 그리퍼 없이 동작한 [현장 기록](field-test/2026-10-09-results.md)은 있으나 HX5의 새 질량·관성에 대한 확인은 아니다.
2. [OMY-F3M STEP/DWG/PDF](https://docs.robotis.com/docs/systems/omy/specifications/hardware/)와 [HX5-D20-MRT/MLT STEP/DWG/PDF](https://docs.robotis.com/docs/systems/hx5_d20/resources/open_source/)에서 손목 플랜지와 HX5 베이스의 홀 패턴, 체결 깊이, 좌우 방향을 비교하고 실제 부품으로 대조한다. **공식 문서에서 OMY↔HX5 직결 어댑터의 규격 또는 호환 장착 절차를 확인하지 못했다.** 맞지 않으면 설계·검증된 어댑터가 필요하다.
3. 손가락 전체 움직임, OMY 관절 전 범위, D405 카메라 시야에서 충돌을 확인한다. 24V/RS-485 케이블은 움직이는 관절과 손가락에서 떨어뜨리고 손목 근처에 스트레인 릴리프를 둔다. 전 범위에서 당김·꼬임·눌림이 없어야 한다. **[미검증]**

## 전원·통신 배선

**AI Worker의 통합 배선:** [공식 장착 절차](https://docs.robotis.com/docs/systems/aiworker/quick_start_guide/setup_overview/hardware/#optional-robotis-hand-installation)는 RH-P12-RN에서 뺀 기존 4핀 JST 케이블을 HX5 포트에 연결하고 손의 종단저항 스위치를 켠다. 별도 U2D2·SMPS는 이 장착 절차에 등장하지 않는다. 반면 [손 단독 Setup Guide](https://docs.robotis.com/docs/systems/hx5_d20/quick_start_guide/setup_guide/)의 **24V SMPS → U2D2 Power Hub → 4핀 케이블 → HX5**, **U2D2 USB → 손 제어 PC**는 독립 구동용이다.

**OMY에 적용한 결과와 남은 확인:** 기존 그리퍼 4핀 케이블로 손을 장착·통전했고 END 210 경유 손 140의 입력 전압 약 23.7 V와 Preset 손가락 동작을 확인했다. [OMY END 유닛 제어표](https://docs.robotis.com/docs/systems/omy/specifications/control_table/#tool-baud-rate--tool-protocol-type--tool-protocol-id-11--12--13)는 Tool ID와 Table Sync 경로를 설명한다. [OMY 하드웨어 사양](https://ai.robotis.com/omy/hardware_omy)의 M8 8핀 툴 출력 24V/1A와 [HX5 사양](https://ai.robotis.com/hands/hardware_hands.html)의 최대 2.6A를 바로 비교해 실제 재사용 4핀 케이블의 전류 한도를 확정할 수는 없다. 최대 부하에서의 전압 강하·전류 여유와 종단 상태는 별도 실측이 필요하다.

HX5는 기본 4 Mbps RS-485/DYNAMIXEL Protocol 2.0을 쓴다. OMY 원래 END 유닛은 `/dev/ttyAMA4`에서 ID 210 컨트롤러와 `rh_r1_joint` 1개를 통해 기존 Tool ID 1 그리퍼를 제어한다. 이 손은 왼손 컨트롤러 ID 140과 내부 모터·센서 ID 141–165를 사용한다. 손 ID 140을 `/dev/ttyAMA4`에 직접 ping했을 때는 무응답이었지만 END 210의 Tool ID와 읽기 창으로 경유하자 손 140과 모터 141이 응답했다. 따라서 손 단독 bringup의 `/dev/ttyUSB0` 인자를 `/dev/ttyAMA4`로 바꾸는 방법은 사용하지 않는다. [오늘 오류·확인 기록](field-test/2026-11-03-omy-hx5-errors.md).

## ROS 2 데이터 경로와 제어 주체

| 출처 → 대상 | 메시지·의미 |
|---|---|
| OMY leader → 팔·손 브리지 | `/leader/joint_trajectory`의 `trajectory_msgs/msg/JointTrajectory`에서 `joint1..6`은 팔 브리지가 꺼내 `/arm_controller/joint_trajectory`에 발행한다. `rh_r1_joint`는 손 브리지가 열림 0–닫힘 1로 정규화한다. 열린 값은 이전 LEAP 시험에서 약 **0.197 rad**, 닫힌 값은 **미측정**이다. |
| 손 브리지 → END Direct 노드 | 실물 모드에서는 `/leader/joint_trajectory_command_broadcaster_left_hand/joint_trajectory`에 `finger_l_joint1..20`을 넣어 발행한다. END Direct 노드가 `/dev/ttyAMA4`에서 END 210의 80바이트 쓰기 창으로 손 140의 TableSync 목표값을 전달한다. 모의 모드의 출력 `/hand_l_controller/joint_trajectory`는 유지한다. |
| HX5 → 손 브리지 | END Direct 노드가 20관절 `/joint_states`와 다섯 손가락의 `/left_hand/finger_pressures`를 발행한다. 압력 타입은 `robotis_interfaces/msg/HandPressures`이며 `sensors[]` 안에 `sensor_name`, `pressure_names[9]`, `pressure_values[9]`가 있다. [공식 촉각 문서](https://docs.robotis.com/docs/systems/hx5_d20/resources/technical_story/tactile_feedback_grasping/). |

HX5는 다섯 손가락 각 4관절이며 그룹은 엄지 1–4, 검지 5–8, 중지 9–12, 약지 13–16, 소지 17–20이다. [ROBOTIS 기본 Hand 키보드 텔레옵](../third_party/robotis_hand/robotis_hand_teleop/robotis_hand_teleop/hx5_d20_teleop.py)은 왼손 엄지의 방향 관절 `joint1/2`를 `-1.57/+1.57 rad`로 대향시키고 `x` 키로 쥘 때 `joint3/4`를 `-1.57/-1.57 rad`로 굽힌다. 다른 네 손가락은 각 그룹의 `joint2/3/4`를 `+2.0/+1.57/+1.57 rad`로 굽힌다. 별도 [공식 촉각 데모](../third_party/robotis_hand/robotis_hand_playground/src/tactile_force_controller.cpp)는 엄지 `joint3/4`의 음방향 굽힘만 이용하므로, 종전 매핑은 엄지를 손가락 쪽으로 대향시키지 못했다. 현재 OMY 연속 방아쇠 매핑은 기본 텔레옵의 대향 방향을 따르되, 공식 `x`의 관절 한계 포즈가 무부하 MuJoCo 장면에서 자기접촉을 일으켜 더 작은 목표를 쓴다. 실제 장착 방향·관절 움직임은 작은 범위에서 다시 확인한다. 손 단독 시험의 공식 왼손 명령은 `ros2 launch robotis_hand_bringup hx5_d20_left.launch.py`이며 **launch가 초기 자세로 손을 움직인다.** 이 명령은 OMY 4핀 결합 bringup이 아니다. [공식 Operation Guide](https://docs.robotis.com/docs/systems/hx5_d20/quick_start_guide/operation_guide/), [왼손 launch](../third_party/robotis_hand/robotis_hand_bringup/launch/hx5_d20_left.launch.py).

AI Worker SH5의 [하드웨어 설정](https://github.com/ROBOTIS-GIT/ai_worker/blob/jazzy/ffw_description/ros2_control/ffw_sh5_rev1_follower/ffw_sh5_follower.ros2_control.xacro)은 손 관절을 `DynamixelHardware`에 등록하고 팔과 분리한다. OMY는 손 컨트롤러 140이 END 210 뒤에 있으므로 실물 런치에서 팔만 `ros2_control`에 등록하고, 손은 [END Direct 노드](../robot_pc/omy_hx5_bringup/omy_hx5_bringup/end_direct_node.py)로 별도 제어한다. 이 노드는 공식 키보드의 ROS 토픽 형식을 받지만 `controller_manager`의 `hand_l_controller`는 아니다. 모의 런치는 기존 손 컨트롤러를 유지한다. 기존 follower 그리퍼 `rh_r1_joint`는 하드웨어 정의에서 제외된다.

리더와 follower를 OMY Robot PC의 동일한 ROS 2 네트워크 설정으로 실행한다. 기존 OMY의 `ROS_DOMAIN_ID=30`, `rmw_zenoh_cpp` 및 라우터 구성을 따른다. 별도 손 제어 PC와 손용 USB 시리얼 경로는 이 구성에 없다. [기존 OMY↔LEAP 현장 연결 기록](field-test/2026-10-09-results.md)을 참고한다.

손 브리지는 수신 시각과 압력 메시지의 ROS timestamp를 검사한다. 같은 Robot PC에서 `ros2 topic hz /left_hand/finger_pressures`와 실제 센서 값 변화를 확인한다. 압력 토픽이 끊기면 추가 닫힘을 허용하지 않는다. 공식 pressure broadcaster가 매 update마다 새 timestamp를 붙이므로 timestamp만으로 물리 센서의 정상 갱신까지 증명할 수는 없다.

### 접촉 지표와 단일 명령 발행자

HX5 손끝은 손가락마다 **3×3, 값 0–255**의 압력 배열을 낸다. 공식 `tactile_sensor.cpp`는 무접촉 baseline을 빼고 음수를 0으로 자른 뒤 EMA로 거른 아홉 값을 합쳐 `total_force`라고 부른다. **이 합과 ROS 압력값은 보정된 N 단위 힘이 아니다.** 제품의 `Max Finger Tip Force 14 N`도 이 지표의 변환계수가 아니다. 접촉 문턱값은 실물의 노이즈·물체·손가락별 데이터로 정한다. [HX5 사양](https://docs.robotis.com/docs/systems/hx5_d20/specifications/hardware/), [공식 알고리즘 설명](https://docs.robotis.com/docs/systems/hx5_d20/resources/technical_story/tactile_feedback_grasping/), [파서 코드](../third_party/robotis_hand/robotis_hand_playground/src/tactile_sensor.cpp).

공식 `tactile_force_controller` 데모는 `/grasp_start` Bool로 **IDLE → CLOSE → HOLD**를 수행한다. 여기서는 연속 leader 방아쇠와 접촉 피드백을 [하나의 손 브리지](../robot_pc/omy_hx5_bringup/hx5_teleop/ros_bridge.py)에서 합쳐 최종 20관절 명령을 발행한다. 공식 데모와 브리지를 동시에 손 컨트롤러에 발행하지 않는다. `ros2_control`은 동일 입력 토픽의 두 발행자 사이 우선순위를 정하지 않는다. [공식 데모 소스](../third_party/robotis_hand/robotis_hand_playground/src/tactile_force_controller.cpp).

공식 데모 파라미터 파일의 `close_step=0.03 rad`, `contact_threshold=10.0`은 데모 설정값이며 실물의 안전한 보정값으로 간주하지 않는다. 특히 데모의 왼손 초기 엄지 `joint2=+1.792 rad`는 [공식 하드웨어 관절 범위](https://docs.robotis.com/docs/systems/hx5_d20/specifications/hardware/)의 `0°–90°`보다 크고, 소스 내부 관절 범위도 사양과 일부 다르다. 따라서 데모 초기 포즈를 그대로 안전한 목표값으로 재사용하지 않고, 현장 구동 전 좌우 방향과 관절 제한을 대조한다. [데모 파라미터](../third_party/robotis_hand/robotis_hand_playground/config/param.yaml), [초기 포즈 소스](../third_party/robotis_hand/robotis_hand_playground/src/tactile_force_controller.cpp).

## 단계별 현장 검증

1. **기구·전원 OFF 검사:** 실제 HX5 모델의 좌우, 어댑터 체결, 질량·무게중심·손목 모멘트, 카메라/손가락 간섭, 케이블 전 범위와 전원 차단 수단을 확인한다. 고정되지 않거나 간섭이 있으면 구동하지 않는다.
2. **END Direct 준비:** 기존 손 직결 드라이버를 실행하지 않는다. [Direct Mode 절차](hx5-d20-omy-direct-hand.md)에 따라 END 210 경유로 20모터 설정을 점검하고 손 컨트롤러 140을 Direct Mode 0으로 준비한다. 이미 확인한 END 210→손 140 읽기 결과와 20모터 준비 결과를 구분한다. `/joint_states`의 손 20관절과 `/left_hand/finger_pressures`의 다섯 센서×아홉 값을 확인하고 무접촉 baseline·가벼운 접촉 반응을 기록한다.
3. **OMY leader 입력 실측:** 이전 LEAP 실험에서 확인한 `/leader/joint_trajectory`의 7번째 `rh_r1_joint`를 leader를 완전히 편 상태와 쥔 상태에서 여러 번 기록한다. **열림 약 0.197 rad는 과거 측정일 뿐이며 닫힘은 미측정**이다. 두 끝값의 방향·범위·떨림을 확정한다. `ros2 topic echo /leader/joint_trajectory --field points`를 사용할 수 있다.
4. **손 궤적을 발행하지 않는 검증:** Robot PC의 [launch](../robot_pc/omy_hx5_bringup/launch/omy_hx5_teleop.launch.py)를 `hand_dry_run:=true`로 실행한다. 이 설정은 손 브리지의 궤적 발행만 막는다. 실물 END Direct 노드는 손 상태를 읽고 Direct TableSync를 활성화하므로, 실행 전 준비 절차가 필요하다. leader 양 끝·중간 입력, 입력 상실, 촉각 없는 경우와 접촉 발생 후 제한 동작을 확인한다. 양 끝값은 launch 인자로 넣는다. 임시 0/1 범위로 실물에 발행하지 않는다.
5. **실물 무부하 → 부드러운 물체:** 드라이런이 통과한 뒤 손과 팔 주변을 비우고 한 손가락씩 작은 범위에서 시작한다. 이후 연속 방아쇠 개폐와 부드러운 물체 파지를 시험하면서 압력 baseline·접촉 임계값·포화·지연, 손목 케이블을 관찰한다. OMY 텔레옵 중 leader가 갑자기 튄 [기존 현장 기록](field-test/2026-10-09-results.md)이 있으므로 leader를 손으로 잡고 시험한다. 이상 동작 시 입력·모터 전원을 중단한다.

공식 MuJoCo 모델은 관절·형상 검토용이며 **실물 촉각 센서를 제공하지 않는다**. 촉각 제어 로직은 synthetic 입력으로 시험할 수 있지만, 접촉 문턱값·파지 안정성은 실제 HX5에서만 확정할 수 있다. [공식 시뮬레이션 자료](https://docs.robotis.com/docs/systems/hx5_d20/simulation/), [공식 촉각 가이드](https://docs.robotis.com/docs/systems/hx5_d20/resources/technical_story/tactile_feedback_grasping/).

### Robot PC bringup과 드라이런

[설치·실행 절차](hx5-d20-omy-direct-hand.md)를 따라 Robot PC의 overlay를 빌드하고 손의 Direct Mode 설정을 완료한 뒤 `omy_hx5_teleop.launch.py`를 실행한다. 기본값은 팔·손 모의 실행이고 텔레옵은 꺼져 있다. 실물 구동 시 `mock_arm:=false mock_hand:=false`, `enable_arm_teleop:=true`, `enable_hand_teleop:=true`, `hand_dry_run:=true`와 **실측한** `leader_open`, `leader_closed`를 넣는다. 드라이런에는 손 브리지가 목표 관절값을 발행하지 않는다. END Direct 노드는 상태를 읽고 TableSync 통신 설정을 활성화하지만 이동 목표는 보내지 않는다. 정상 입력 확인 후 리더 방아쇠를 열고 손을 열린 무접촉 상태로 둔 채 `ros2 param set /hx5_left_omy_teleop command_enabled true`로 전환한다. 손 브리지는 새 baseline을 수집하고 실제 관절값에서 명령을 시작한다. 손 브리지가 멈춰도 손 토크가 자동으로 꺼지지는 않는다.

실행 전에는 Preset 런치, 공식 손 단독 런치, 기존 손 직결 `omy_hx5_hand_live.launch.py`와 END 포트를 사용하는 진단 프로그램을 종료한다. 손의 Direct Mode 준비는 [한 번만 수행하는 명령](hx5-d20-omy-direct-hand.md#2-손-direct-mode-준비-한-번)을 따른다. Robot PC의 Zenoh 라우터와 별도로 실행한 OMY leader가 `/leader/joint_trajectory`를 발행하는지 확인한다. `start_leader:=false`는 leader가 이미 다른 터미널 또는 PC에서 실행 중이라는 뜻이다. 이 런치는 팔을 자동으로 unpack하지 않으므로 시작 자세를 먼저 확인한다.

Robot PC 컨테이너의 Bash 터미널에서:

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
source /workspace/omy_ws/install/setup.bash
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
unset ZENOH_CONFIG_OVERRIDE
ros2 topic echo /leader/joint_trajectory --field points
```

`ros2 topic echo`에서 두 끝값을 기록한 뒤 Ctrl+C로 종료한다. 리더를 편 상태와 완전히 쥔 상태에서 각각 관측한 `rh_r1_joint` 값으로 아래 두 변수를 채운다. 예시 숫자 0/1을 실물 측정값 대신 사용하지 않는다. 먼저 팔 텔레옵을 끄고 손 계산만 확인한다.

```bash
read -rp '리더를 편 상태의 rh_r1_joint: ' MEASURED_OPEN
read -rp '리더를 쥔 상태의 rh_r1_joint: ' MEASURED_CLOSED
ros2 launch omy_hx5_bringup omy_hx5_teleop.launch.py \
  mock_arm:=false mock_hand:=false start_leader:=false \
  enable_arm_teleop:=false enable_hand_teleop:=true hand_dry_run:=true \
  leader_open:="$MEASURED_OPEN" leader_closed:="$MEASURED_CLOSED"
```

다른 컨테이너 터미널에서 `/joint_states`에 손 관절 20개가 들어오는지, `/left_hand/finger_pressures`의 다섯 센서가 갱신되는지, 손 브리지가 `waiting for released leader and tactile baseline`을 지나 계산 로그를 내는지 확인한다. 그다음 런치를 종료하고 팔 텔레옵을 켠 상태로 다시 시작한다. **팔은 leader의 여섯 관절을 즉시 따라갈 수 있으므로** leader를 잡고 안전한 위치에서 시작한다.

```bash
ros2 launch omy_hx5_bringup omy_hx5_teleop.launch.py \
  mock_arm:=false mock_hand:=false start_leader:=false \
  enable_arm_teleop:=true enable_hand_teleop:=true hand_dry_run:=true \
  leader_open:="$MEASURED_OPEN" leader_closed:="$MEASURED_CLOSED"
```

손을 펴고 무접촉 상태에서 손 브리지가 신선한 관절·촉각·리더 입력을 받는 것을 확인한 뒤, 별도 컨테이너 터미널에서 같은 ROS 환경을 적용해 손 발행을 켠다.

```bash
ros2 param set /hx5_left_omy_teleop command_enabled true
```

이후 데이터 흐름은 `leader 7관절 → 팔 6관절 브리지 → arm_controller`와 `leader 방아쇠 → 촉각 보조 손 브리지 → 공식 왼손 JointTrajectory 토픽 → END 210 → HX5 140 → 20모터`로 갈라진다. 실물 모드에서 `ros2 control list_controllers`에는 **팔 컨트롤러만** 표시되는 것이 정상이며 손 제어 노드는 별도 프로세스다. 공식 키보드나 촉각 grasp 데모를 동시에 실행하면 손 명령 발행자가 겹치므로 사용하지 않는다.

### unpack 자세에서 손만 키보드로 원격 제어

기존 `omy_hx5_hand_only.launch.py`와 `omy_hx5_hand_live.launch.py`의 실물 경로는
손 ID 140에 직접 접근하므로 OMY END 210 뒤에 연결된 현재 손에는 사용할 수 없다.
모의 unpack 시험에는 기존 코드를 유지한다. 실물 손만 제어하려면
[END Direct 손 전용 실행 절차](hx5-d20-omy-direct-hand.md)를 따른다. 이
경로에서 공식 왼손 키보드의 손가락별 20관절 명령을 쓸 수 있다. 팔 자세를 먼저
확인하고, END 포트를 쓰는 다른 런치와 동시에 실행하지 않는다.

### 왼손 촉각 신호 가시화

Robot PC가 `/left_hand/finger_pressures`를 발행하면 User PC에서 [`run_hx5_tactile_viz.sh`](../user_pc/run_hx5_tactile_viz.sh)를 실행한다. 이 스크립트는 공식 `robotis_hand_playground`의 `tactile_rviz`와 `matplot_visualize_tactile.py`를 왼손 압력 토픽에 연결한다. RViz에는 손끝별 압력 방향 화살표와 압력 중심(CoP) 마커가, Matplotlib에는 다섯 손가락의 3×3 taxel 히트맵이 표시된다. [공식 촉각 가시화 설명](https://docs.robotis.com/docs/systems/hx5_d20/resources/technical_story/tactile_feedback_grasping/). RViz 설정은 [손 전용 좌표계용 설정](../robot_pc/omy_hx5_bringup/rviz/omy_hx5_left_tactile.rviz)을 사용한다. GUI를 Robot PC에서 직접 띄울 때는 [`omy_hx5_tactile_view.launch.py`](../robot_pc/omy_hx5_bringup/launch/omy_hx5_tactile_view.launch.py)를 사용할 수 있다.

두 가시화 노드는 압력값을 구독하지만 손 관절 명령을 발행하지 않는다. 기존 텔레옵 손 브리지와 동시에 사용할 수 있다. 기본 설정에서는 시작 직후 약 20개의 무접촉 프레임(20 Hz×1초)을 baseline으로 잡으므로 초기화 중에는 손끝을 누르지 않는다. 화살표 길이와 히트맵 색은 baseline 보정된 **상대 압력 지표**이며 보정된 N 단위 힘을 뜻하지 않는다. 모의 하드웨어에서 압력이 0으로만 나오면 실시간 화면도 비어 있는 것이 정상이다.

코어의 기본 open은 **20관절 0 rad**이고, 방아쇠 완전 닫힘 목표는 왼손 엄지 `joint1..4=(-0.864,+0.864,-1.2,-1.2) rad`, 나머지 네 손가락의 각 `joint1..4=(0,+1.3,+0.78,+0.52) rad`다. 공식 기본 Hand 텔레옵의 엄지 대향 방향을 반영하되, 목표 크기는 공식 MuJoCo 모델에서 조정한 **시뮬레이션용 값**이며 실물 안전 포즈나 물체별 파지 포즈로 보정한 값은 아니다. 속도 제한 `0.5 rad/s`를 손가락 관절의 목표 변화량에 같은 비율로 적용해 중간 자세도 대향 형태를 유지한다. 완전히 편 손에서 최대 1.3 rad까지 가려면 **최소 2.6초** 동안 방아쇠를 닫아야 한다. 압력 예시 기본값(`contact_threshold=10`, `pressure_hard_cap=30` 원시 합)은 실물 보정값이 아니다. 무접촉 상태에서 leader를 완전히 열어 30개의 압력 프레임으로 baseline을 만들기 전에는 손 명령을 발행하지 않는다. [코어](../robot_pc/omy_hx5_bringup/hx5_teleop/core.py), [ROS bridge](../robot_pc/omy_hx5_bringup/hx5_teleop/ros_bridge.py), [launch](../robot_pc/omy_hx5_bringup/launch/omy_hx5_teleop.launch.py).

### 하드웨어 없이 수행한 검증

- 공식 [`scene_left.xml`](../third_party/robotis_hand/robotis_hand_description/mujoco/hx5_d20_rev2/scene_left.xml)을 MuJoCo 3.12.0으로 로드했다. 20개 관절과 position actuator의 이름·순서가 `finger_l_joint1..20`과 일치한다. [`test_hx5_mujoco.py`](../robot_pc/omy_hx5_bringup/test/test_hx5_mujoco.py)의 새 대향 포즈 방아쇠 0→0.5→1→0 구동은 **자기접촉 0건**, 관절 한계·명령 속도·추종 오차 0.03 rad 이내를 확인했다. 공식 키보드 `x`의 최대 굽힘 포즈는 같은 무부하 모델에서 자기접촉이 발생했다. 이 모델에는 촉각 센서(`nsensor=0`)가 없다. [포즈 비교 이미지](../robot_pc/preview/hx5_official_teleop_thumb_comparison.png).
- 공식 Docker 이미지의 왼손 Gazebo launch를 일회성 컨테이너 내부에서 **서버 전용**으로 실행했다. `hand_l_controller`와 `joint_state_broadcaster`가 active였고 `/joint_states` 20관절을 확인했다. 공식 손 명령 토픽에 20관절 `JointTrajectory`(j6 목표 `+0.2 rad`, 2초)를 발행하자 j6가 `0.000000→0.199957 rad`로 추종했다. 원본 launch는 RViz/Gazebo GUI를 함께 띄워 화면 없는 컨테이너에서 OpenGL 오류로 종료하므로, **컨테이너 `/tmp`의 사본에서만** `gz_args`에 `-s`를 더하고 RViz 항목을 제거했다. 공식 소스와 호스트 설정은 바꾸지 않았다. [공식 Gazebo 절차](https://docs.robotis.com/docs/systems/hx5_d20/simulation/gazebo/), [공식 왼손 launch](../third_party/robotis_hand/robotis_hand_bringup/launch/hx5_d20_left_gazebo.launch.py).
- 공식 `robotis/robotis-hand:1.0.2` 컨테이너의 실제 `robotis_interfaces/msg/HandPressures`와 ROS 2 토픽을 사용한 [`test_hx5_ros_integration.py`](../robot_pc/omy_hx5_bringup/test/test_hx5_ros_integration.py)는 가짜 leader·관절·압력 발행자로 **드라이런 계산과 20관절 명령 형식**을 검증했다. 컨테이너 내부 통합 시험이며 OMY나 HX5 실물에 연결한 결과가 아니다.
- **OMY+HX5 모의 통합 시험:** 공식 OMY, ROBOTIS Hand, RealSense 설명을 Jazzy 컨테이너에서 빌드하고 합친 Xacro를 전개했다. 4개 컨트롤러(`joint_state_broadcaster`, `arm_controller`, `hand_l_controller`, `pressure_l_broadcaster`)가 활성화됐다. [`mock_teleop_probe.py`](../robot_pc/omy_hx5_bringup/test/mock_teleop_probe.py)가 합성 leader 7관절을 넣자 팔 6관절과 왼손 20관절 명령이 각각 나왔고, 새 대향 포즈에서 검지 `joint6`의 모의 관절상태는 방아쇠 0→0.5→1→0에서 **0→0.650→1.300→0 rad**였다. 엄지 `joint1/2`도 닫힘에 따라 **-0.864/+0.864 rad**까지 움직였다. [측정 기록](../robot_pc/preview/omy_hx5_thumb_opposition_teleop_states.json). 이 결과는 END 전기 연결을 검증하지 않는다.
- **이전 손 전용 키보드 모의 통합 시험(팔 유지 기능 추가 전):** Xacro를 `enable_arm_hardware:=false`로 전개하면 손용 `OMYHX5EndSystem` 1개와 왼손 20관절만 하드웨어 정의에 남는다. 실물 설정 전개 결과도 팔 시스템 없이 손 드라이버가 `/dev/ttyAMA4`로 설정되는 것을 확인했다. 모의 launch에서는 손·압력·관절상태 컨트롤러 3개만 활성화됐고, 실제 키보드 프로그램에 `]`(50% 시험 설정), `x`, `z`를 입력한 [측정 상태](../robot_pc/preview/omy_hx5_hand_only_keyboard_mock_states.json)는 검지 `joint6` **0→0.650→1.300→0 rad**, 엄지 `joint1/2` 최대 **-0.864/+0.864 rad**였다. 이 시험은 원격 키보드 명령부터 모의 손 관절까지 확인하지만 실제 User PC↔Robot PC 네트워크, END 시리얼 패킷, HX5 모터 동작은 검증하지 않는다.
- **unpack → 팔 유지 → 손 키보드 통합 시험:** 공식 포장 자세에서 출발한 모의 팔이 영점까지 이동하는 동안 손 명령이 차단됐고, 완료 후 동일한 controller manager를 유지한 채 `command_enabled`를 false→true로 전환했다. 실제 키보드 프로그램의 열기→50%→닫기→열기에서 검지 `joint6`은 **0→0.650→1.300→0 rad**, 팔 여섯 관절은 영점을 유지했다. 별도로 실행한 7관절 leader 입력은 팔에 영향을 주지 않았다. 손 명령 재차 중지도 확인했다. [포장 자세 출발 측정](../robot_pc/preview/omy_hx5_unpack_hold_packed_mock_states.json), [실제 launch 측정](../robot_pc/preview/omy_hx5_unpack_hold_launch_mock_states.json). 팔·손 mock 설정 혼용은 노드 시작 전에 거부된다. 이 검증은 ROS 모의 하드웨어 결과이며 실물 토크·시리얼 통신을 검증하지 않는다.
- **촉각 화면 합성 시험:** 공식 `tactile_rviz`에 엄지 중앙 100, 검지 모서리 80의 합성 `HandPressures`를 넣었다. 왼손 손끝 좌표계에서 해당 두 손가락의 화살표·CoP 마커만 표시됐고, 화살표 길이는 각각 약 0.050 m·0.040 m였다. 중앙 taxel의 엄지 화살표는 법선 방향이었으며 모서리 taxel의 검지 화살표는 옆으로 기울었다. [ROS 마커 측정값](../robot_pc/preview/omy_hx5_tactile_markers_mock.json). 공식 Matplotlib 가시화 코드에도 같은 3×3 입력을 넣어 [합성 히트맵](../robot_pc/preview/omy_hx5_official_heatmap_synthetic.png)을 렌더링했다. 화살표의 크기·방향은 압력 합과 CoP로 만든 **시각적 추정치**이며 실측 3D 힘 벡터가 아니다. 이 시험은 소프트웨어 데이터 처리와 이미지 생성만 검증하며 실물 센서, ROS 네트워크 분리, 실제 GUI 표시 품질을 검증하지 않는다.
- [`test_hx5_core.py`](../robot_pc/omy_hx5_bringup/test/test_hx5_core.py)는 5×9 baseline, 접촉 손가락별 제한, 압력 목표대역 보정, 방아쇠 해제, 센서·leader 소실 및 포화 fault를 합성 입력으로 검사한다. 원시값 기준 임계와 실제 파지력은 현장에서 보정해야 한다.
- Gazebo가 관절 상한 0 rad에서 약 `1e-10 rad`의 수치 오차를 내는 경우가 있어 초기 관절 측정값에만 최대 `1e-6 rad`의 경계 허용 오차를 적용하고 명령 시 실제 모델 한계 안으로 잘라 넣는다. `1e-4 rad`처럼 더 큰 범위 초과는 계속 거부한다. [코어](../robot_pc/omy_hx5_bringup/hx5_teleop/core.py), [경계 시험](../robot_pc/omy_hx5_bringup/test/test_hx5_core.py). **위 시험의 압력은 전부 합성 또는 모의 데이터이며 실물 HX5 촉각, 접촉력, 안정 파지는 검증하지 않았다.**
- **바닥 물체 집기 동작 시험(모의, 2026-10-13):** [`mock_floor_pick_probe.py`](../robot_pc/omy_hx5_bringup/test/mock_floor_pick_probe.py)가 합성 leader 7관절을 통해 home→pregrasp→하강→방아쇠 닫기→상승을 실행했다. 새 엄지 대향 포즈로 재실행한 128개 [측정 상태](../robot_pc/preview/omy_hx5_thumb_opposition_floor_pick_states.json)에서는 검지 `joint6`이 **1.300 rad**, 엄지 방향 관절 `joint1/2`가 **-0.864/+0.864 rad**까지 움직였다. 같은 8 cm 정육면체는 여전히 들리지 않았다. 통합 MuJoCo [재생 영상](../robot_pc/preview/omy_hx5_thumb_opposition_floor_pick.gif)에서 시각 메시 접촉은 손을 닫는 동안 사라졌고, [자유 물체 근사 동역학 검사](../robot_pc/preview/omy_hx5_thumb_opposition_floor_pick_dynamics.json)의 물체 중심 높이는 초기 0.040 m에서 최종 약 0.0399 m였다. 따라서 이 물체 위치·손목 자세의 접근 경로와 접촉 위치는 추가 조정이 필요하다. 이 검사는 기록된 로봇 자세를 강제로 적용하고 시각 메시를 충돌 형상으로 사용한 진단이며, 실제 접촉력이나 실물 파지 성능을 입증하지 않는다. [검사 코드](../robot_pc/preview/check_mock_floor_pick_dynamics.py), [접촉 기록](../robot_pc/preview/omy_hx5_thumb_opposition_floor_pick_contacts.json).

## 현재 증거와 남은 현장 작업

- **확인됨:** OMY 기존 4핀 장착·통전, END 210→손 140→모터 141 읽기, Preset 검지 움직임, 이전 ROS 2 모의 leader 7관절→팔 6관절·손 20관절 분리.
- **아직 미검증:** 새 END Direct 20관절 실물 동작, 촉각 토픽과 접촉 임계값, leader 닫힘 끝값, 리더→END→20모터 전체 실물 텔레옵, 최대 부하 전류 여유.
- **실행 전 조건:** 하나의 END 포트 소유자와 손 명령 발행자, Direct Mode 준비와 20모터 설정 점검, leader 양 끝값 실측, 주변 간섭 확인.
