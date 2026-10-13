# HX5-D20 × OMY 촉각 보조 텔레오퍼레이션 준비

[실행 명령어 모음](hx5-d20-run-commands.md)

이 문서는 OMY-F3M follower의 RH-P12-RN 그리퍼를 제거하고 HX5-D20을 장착해, OMY-L100 leader의 그리퍼 입력으로 손을 연속 개폐하기 위한 준비 및 현장 검증 순서다. 목표 배선은 **기존 그리퍼 케이블을 HX5에 재사용**하는 것이다. [AI Worker 공식 장착 절차](https://docs.robotis.com/docs/systems/aiworker/quick_start_guide/setup_overview/hardware/#optional-robotis-hand-installation)는 같은 RH-P12-RN 제거 후 기존 4핀 JST 케이블을 HX5에 연결하는 사례이지만, OMY에서도 그 케이블의 전원·통신 경로가 HX5에 적합한지는 아직 확인되지 않았다. **HX5 장착·통전·실물 구동은 아직 검증하지 않았다.** 2026-10-09의 LEAP Hand 실물 성공은 leader 입력과 OMY 팔의 선행 근거이며, HX5의 기구·전기 호환성을 입증하지 않는다.

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

**OMY에 적용할 때 미확인 사항:** [OMY END 유닛 제어표](https://docs.robotis.com/docs/systems/omy/specifications/control_table/#tool-baud-rate--tool-protocol-type--tool-protocol-id-11--12--13)는 툴 포트의 통신 속도·프로토콜·단일 Tool ID와 Table Sync 경로를 설명한다. [OMY 하드웨어 사양](https://ai.robotis.com/omy/hardware_omy)은 END 유닛의 M8 8핀 툴 출력을 24V/1A로 표기하고, [HX5 사양](https://ai.robotis.com/hands/hardware_hands.html)은 24V/최대 2.6A를 표기한다. 현물 그리퍼의 4핀 케이블이 이 M8 정격 출력과 동일한 경로인지 공개 도면만으로 확인하지 못했다. **24V/1A 정격이 실제 재사용 케이블에 적용된다면 HX5 최대 전류를 만족하지 못하므로 그 경로로 통전하지 않는다.** 핀 배열·전원 공급 능력·커넥터 변환·종단 위치를 확인한 뒤 전원을 끈 상태에서 결선한다.

HX5는 기본 4 Mbps RS-485/DYNAMIXEL Protocol 2.0을 쓴다. OMY 원래 END 유닛은 `/dev/ttyAMA4`에서 ID 210 컨트롤러와 `rh_r1_joint` 1개를 통해 기존 Tool ID 1 그리퍼를 제어한다. HX5는 왼손 ID 140 및 20관절(모터 ID 141–165)을 쓰므로, 같은 4핀에 꽂는 것만으로 기존 제어 설정이 손을 제어하지는 못한다. 손 단독 bringup의 기본 `/dev/ttyUSB0`를 `/dev/ttyAMA4`로 바꾸는 것만으로 END 유닛 뒤 툴 버스에 직접 접근된다고 가정하지 않는다. 또한 공식 왼손 root xacro는 현재 `port_name` launch 인자를 손 시스템 매크로에 전달하지 않아, 인자만 바꿔도 생성된 하드웨어 설정은 `/dev/ttyUSB0`다. [OMY 설정](../third_party/open_manipulator/open_manipulator_description/ros2_control/omy_f3m_end_unit.ros2_control.xacro), [HX5 왼손 xacro](../third_party/robotis_hand/robotis_hand_description/urdf/hx5_d20_rev2/hx5_d20_left.xacro).

## ROS 2 데이터 경로와 제어 주체

| 출처 → 대상 | 메시지·의미 |
|---|---|
| OMY leader → 팔·손 브리지 | `/leader/joint_trajectory`의 `trajectory_msgs/msg/JointTrajectory`에서 `joint1..6`은 팔 브리지가 꺼내 `/arm_controller/joint_trajectory`에 발행한다. `rh_r1_joint`는 손 브리지가 열림 0–닫힘 1로 정규화한다. 열린 값은 이전 LEAP 시험에서 약 **0.197 rad**, 닫힌 값은 **미측정**이다. |
| 손 브리지 → HX5 컨트롤러 | `/hand_l_controller/joint_trajectory`에 `finger_l_joint1..20`을 넣은 `JointTrajectory`를 발행한다. `hand_l_controller`는 OMY END의 `/dev/ttyAMA4`를 소유하는 하드웨어 인터페이스의 HX5 관절을 명령한다. 기존 그리퍼 `rh_r1_joint`는 follower 하드웨어 정의에서 제거했다. |
| HX5 → 손 브리지 | `/joint_states`와 `/left_hand/finger_pressures`. 압력 타입은 `robotis_interfaces/msg/HandPressures`이며 `sensors[]` 안에 `sensor_name`, `pressure_names[9]`, `pressure_values[9]`가 있다. [공식 촉각 문서](https://docs.robotis.com/docs/systems/hx5_d20/resources/technical_story/tactile_feedback_grasping/). |

HX5는 다섯 손가락 각 4관절이며 그룹은 엄지 1–4, 검지 5–8, 중지 9–12, 약지 13–16, 소지 17–20이다. [ROBOTIS 기본 Hand 키보드 텔레옵](../third_party/robotis_hand/robotis_hand_teleop/robotis_hand_teleop/hx5_d20_teleop.py)은 왼손 엄지의 방향 관절 `joint1/2`를 `-1.57/+1.57 rad`로 대향시키고 `x` 키로 쥘 때 `joint3/4`를 `-1.57/-1.57 rad`로 굽힌다. 다른 네 손가락은 각 그룹의 `joint2/3/4`를 `+2.0/+1.57/+1.57 rad`로 굽힌다. 별도 [공식 촉각 데모](../third_party/robotis_hand/robotis_hand_playground/src/tactile_force_controller.cpp)는 엄지 `joint3/4`의 음방향 굽힘만 이용하므로, 종전 매핑은 엄지를 손가락 쪽으로 대향시키지 못했다. 현재 OMY 연속 방아쇠 매핑은 기본 텔레옵의 대향 방향을 따르되, 공식 `x`의 관절 한계 포즈가 무부하 MuJoCo 장면에서 자기접촉을 일으켜 더 작은 목표를 쓴다. 실제 장착 방향·관절 움직임은 작은 범위에서 다시 확인한다. 손 단독 시험의 공식 왼손 명령은 `ros2 launch robotis_hand_bringup hx5_d20_left.launch.py`이며 **launch가 초기 자세로 손을 움직인다.** 이 명령은 OMY 4핀 결합 bringup이 아니다. [공식 Operation Guide](https://docs.robotis.com/docs/systems/hx5_d20/quick_start_guide/operation_guide/), [왼손 launch](../third_party/robotis_hand/robotis_hand_bringup/launch/hx5_d20_left.launch.py).

AI Worker SH5의 [하드웨어 설정](https://github.com/ROBOTIS-GIT/ai_worker/blob/jazzy/ffw_description/ros2_control/ffw_sh5_rev1_follower/ffw_sh5_follower.ros2_control.xacro)은 손 관절을 `DynamixelHardware`에 등록하고 [손 컨트롤러](https://github.com/ROBOTIS-GIT/ai_worker/blob/jazzy/ffw_bringup/config/ffw_sh5_rev1_follower/ffw_sh5_follower_ai_hardware_controller.yaml)를 팔과 분리한다. 이 브랜치의 [OMY 통합 Xacro](../robot_pc/omy_hx5_bringup/urdf/omy_f3m_hx5_left.urdf.xacro)도 같은 제어 분리를 적용했다. 팔은 `/dev/ttyAMA2`, END 보드 ID 210과 HX5 컨트롤러 ID 140은 **하나의** `/dev/ttyAMA4` 인터페이스에 등록한다. 공식 HX5 `hx5_left_joints` 정의를 포함하므로 `virtual_dxl`은 실제 손 컨트롤러를 통한 모터 프록시이고, LEAP용 모의 `rh_r1_joint`가 아니다. OMY END Tool ID 1 설정은 기존 값을 유지했다. **ID 140 패킷이 OMY END를 통과하는지와 4핀 전원 적합성은 하드웨어 없이 검증할 수 없다.**

리더와 follower를 OMY Robot PC의 동일한 ROS 2 네트워크 설정으로 실행한다. 기존 OMY의 `ROS_DOMAIN_ID=30`, `rmw_zenoh_cpp` 및 라우터 구성을 따른다. 별도 손 제어 PC와 손용 USB 시리얼 경로는 이 구성에 없다. [기존 OMY↔LEAP 현장 연결 기록](field-test/2026-10-09-results.md)을 참고한다.

손 브리지는 수신 시각과 압력 메시지의 ROS timestamp를 검사한다. 같은 Robot PC에서 `ros2 topic hz /left_hand/finger_pressures`와 실제 센서 값 변화를 확인한다. 압력 토픽이 끊기면 추가 닫힘을 허용하지 않는다. 공식 pressure broadcaster가 매 update마다 새 timestamp를 붙이므로 timestamp만으로 물리 센서의 정상 갱신까지 증명할 수는 없다.

### 접촉 지표와 단일 명령 발행자

HX5 손끝은 손가락마다 **3×3, 값 0–255**의 압력 배열을 낸다. 공식 `tactile_sensor.cpp`는 무접촉 baseline을 빼고 음수를 0으로 자른 뒤 EMA로 거른 아홉 값을 합쳐 `total_force`라고 부른다. **이 합과 ROS 압력값은 보정된 N 단위 힘이 아니다.** 제품의 `Max Finger Tip Force 14 N`도 이 지표의 변환계수가 아니다. 접촉 문턱값은 실물의 노이즈·물체·손가락별 데이터로 정한다. [HX5 사양](https://docs.robotis.com/docs/systems/hx5_d20/specifications/hardware/), [공식 알고리즘 설명](https://docs.robotis.com/docs/systems/hx5_d20/resources/technical_story/tactile_feedback_grasping/), [파서 코드](../third_party/robotis_hand/robotis_hand_playground/src/tactile_sensor.cpp).

공식 `tactile_force_controller` 데모는 `/grasp_start` Bool로 **IDLE → CLOSE → HOLD**를 수행한다. 여기서는 연속 leader 방아쇠와 접촉 피드백을 [하나의 손 브리지](../robot_pc/omy_hx5_bringup/hx5_teleop/ros_bridge.py)에서 합쳐 최종 20관절 명령을 발행한다. 공식 데모와 브리지를 동시에 손 컨트롤러에 발행하지 않는다. `ros2_control`은 동일 입력 토픽의 두 발행자 사이 우선순위를 정하지 않는다. [공식 데모 소스](../third_party/robotis_hand/robotis_hand_playground/src/tactile_force_controller.cpp).

공식 데모 파라미터 파일의 `close_step=0.03 rad`, `contact_threshold=10.0`은 데모 설정값이며 실물의 안전한 보정값으로 간주하지 않는다. 특히 데모의 왼손 초기 엄지 `joint2=+1.792 rad`는 [공식 하드웨어 관절 범위](https://docs.robotis.com/docs/systems/hx5_d20/specifications/hardware/)의 `0°–90°`보다 크고, 소스 내부 관절 범위도 사양과 일부 다르다. 따라서 데모 초기 포즈를 그대로 안전한 목표값으로 재사용하지 않고, 현장 구동 전 좌우 방향과 관절 제한을 대조한다. [데모 파라미터](../third_party/robotis_hand/robotis_hand_playground/config/param.yaml), [초기 포즈 소스](../third_party/robotis_hand/robotis_hand_playground/src/tactile_force_controller.cpp).

## 단계별 현장 검증

1. **기구·전원 OFF 검사:** 실제 HX5 모델의 좌우, 어댑터 체결, 질량·무게중심·손목 모멘트, 카메라/손가락 간섭, 케이블 전 범위와 전원 차단 수단을 확인한다. 고정되지 않거나 간섭이 있으면 구동하지 않는다.
2. **OMY 툴 배선·드라이버 확인:** 기존 RH-P12-RN의 4핀 케이블이 OMY END의 어느 포트에서 나오는지, 전압·극성·전류 공급 능력이 HX5 요구 사양을 만족하는지 확인한다. 적합성이 입증되지 않은 배선으로 HX5에 전원을 인가하지 않는다. 전기 조건이 확인된 다음, 다른 bringup을 중지한 상태에서 [Robot PC의 읽기 전용 ID 140 ping 명령](../robot_pc/README.md#read-only-id-140-ping-on-the-robot-pc)으로 END ID 210과 HX5 ID 140의 응답을 구분해 확인한다. ID 140이 응답해도 Tool ID 1 설정과 20관절 제어·전원 용량까지 검증된 것은 아니다. 이 브랜치는 `/dev/ttyAMA4`를 한 하드웨어 인터페이스만 열도록 구성했지만, 실제 패킷 통과는 미검증이다. 이후 `/joint_states` 20관절과 `/left_hand/finger_pressures`의 다섯 센서×아홉 값을 확인하고 무접촉 baseline·가벼운 접촉 반응을 기록한다.
3. **OMY leader 입력 실측:** 이전 LEAP 실험에서 확인한 `/leader/joint_trajectory`의 7번째 `rh_r1_joint`를 leader를 완전히 편 상태와 쥔 상태에서 여러 번 기록한다. **열림 약 0.197 rad는 과거 측정일 뿐이며 닫힘은 미측정**이다. 두 끝값의 방향·범위·떨림을 확정한다. `ros2 topic echo /leader/joint_trajectory --field points`를 사용할 수 있다.
4. **손 궤적을 발행하지 않는 검증:** Robot PC의 [launch](../robot_pc/omy_hx5_bringup/launch/omy_hx5_teleop.launch.py)를 `hand_dry_run:=true`로 실행한다. 이 설정은 Python 손 브리지의 궤적 발행만 막으며, `mock_hand:=false`인 하드웨어 플러그인의 초기화 쓰기·재시작·토크 활성화는 막지 않는다. leader 양 끝·중간 입력, 입력 상실, 촉각 없는 경우와 접촉 발생 후 제한 동작을 확인한다. 양 끝값은 launch 인자로 넣는다. 임시 0/1 범위로 실물에 발행하지 않는다.
5. **실물 무부하 → 부드러운 물체:** 드라이런이 통과한 뒤 손과 팔 주변을 비우고 한 손가락씩 작은 범위에서 시작한다. 이후 연속 방아쇠 개폐와 부드러운 물체 파지를 시험하면서 압력 baseline·접촉 임계값·포화·지연, 손목 케이블을 관찰한다. OMY 텔레옵 중 leader가 갑자기 튄 [기존 현장 기록](field-test/2026-10-09-results.md)이 있으므로 leader를 손으로 잡고 시험한다. 이상 동작 시 입력·모터 전원을 중단한다.

공식 MuJoCo 모델은 관절·형상 검토용이며 **실물 촉각 센서를 제공하지 않는다**. 촉각 제어 로직은 synthetic 입력으로 시험할 수 있지만, 접촉 문턱값·파지 안정성은 실제 HX5에서만 확정할 수 있다. [공식 시뮬레이션 자료](https://docs.robotis.com/docs/systems/hx5_d20/simulation/), [공식 촉각 가이드](https://docs.robotis.com/docs/systems/hx5_d20/resources/technical_story/tactile_feedback_grasping/).

### Robot PC bringup과 드라이런

[설치·실행 절차](../robot_pc/README.md)는 Robot PC의 ROS 2 overlay를 빌드한 뒤 `omy_hx5_teleop.launch.py`를 실행한다. launch의 기본값은 팔·손 모두 mock이고 텔레옵이 꺼져 있다. 실물 구동 시에는 `mock_arm:=false mock_hand:=false`를 명시하며, 먼저 `hand_dry_run:=true`와 **실측한** `leader_open`, `leader_closed`를 넣는다. 드라이런에서는 손 브리지의 궤적을 발행하지 않지만 하드웨어 초기화는 진행된다. 정상 입력과 안전 정지를 확인한 다음에만 `hand_dry_run:=false`로 재시작한다. 손 브리지가 멈춰도 컨트롤러의 torque가 자동으로 꺼지지는 않으므로 Robot PC의 비상정지·전원 차단 절차가 필요하다.

### unpack 자세에서 손만 키보드로 원격 제어

팔이 **이미 unpack 자세**에 있다면 [`omy_hx5_hand_only.launch.py`](../robot_pc/omy_hx5_bringup/launch/omy_hx5_hand_only.launch.py)를 사용한다. 이 launch의 Xacro는 팔 형상은 유지하지만 팔 `ros2_control` 시스템·팔 컨트롤러·팔 브리지를 생성하지 않으며 `/dev/ttyAMA2`를 열지 않는다. 따라서 팔을 unpack 자세로 이동시키거나 그 자세를 모터로 유지하는 기능도 없다. 기본값은 `mock_hand:=true hand_dry_run:=true`다. 실물 손 연결 시 배선·전원·END 경로를 검증한 뒤 `mock_hand:=false hand_dry_run:=true`로 상태와 압력만 먼저 읽고, 이후 낮은 쥐기 비율부터 `hand_dry_run:=false`로 시험한다. 전체 팔·손 launch와 동시에 실행하지 않는다.

원격 PC의 [`omy_hx5_keyboard.py`](../user_pc/omy_hx5_keyboard.py)는 공식 Hand 키보드의 `x`(전체 쥐기), `z`(전체 펴기)를 참고한다. `[`/`]`로 쥐기 요청을 10%씩 바꿀 수 있다. 클라이언트는 전용 `/hx5/keyboard_grasp_trajectory`에 `rh_r1_joint` **한 값**을 20 Hz로 발행한다. Robot PC의 기존 HX5 손 브리지는 이를 0–1로 해석해 촉각·관절상태 안전 게이트를 적용한 왼손 20관절 명령을 발행한다. 7관절 leader 토픽과 팔 경로는 쓰지 않는다. 키보드 종료 전 `z`를 누르고 실제 손 상태가 펴졌는지 확인한다. [실행 명령](../robot_pc/README.md#hand-only-remote-keyboard-at-the-unpack-pose).

### 왼손 촉각 신호 가시화

Robot PC가 `/left_hand/finger_pressures`를 발행하면 User PC에서 [`run_hx5_tactile_viz.sh`](../user_pc/run_hx5_tactile_viz.sh)를 실행한다. 이 스크립트는 공식 `robotis_hand_playground`의 `tactile_rviz`와 `matplot_visualize_tactile.py`를 왼손 압력 토픽에 연결한다. RViz에는 손끝별 압력 방향 화살표와 압력 중심(CoP) 마커가, Matplotlib에는 다섯 손가락의 3×3 taxel 히트맵이 표시된다. [공식 촉각 가시화 설명](https://docs.robotis.com/docs/systems/hx5_d20/resources/technical_story/tactile_feedback_grasping/). RViz 설정은 [손 전용 좌표계용 설정](../robot_pc/omy_hx5_bringup/rviz/omy_hx5_left_tactile.rviz)을 사용한다. GUI를 Robot PC에서 직접 띄울 때는 [`omy_hx5_tactile_view.launch.py`](../robot_pc/omy_hx5_bringup/launch/omy_hx5_tactile_view.launch.py)를 사용할 수 있다.

두 가시화 노드는 압력값을 구독하지만 손 관절 명령을 발행하지 않는다. 기존 텔레옵 손 브리지와 동시에 사용할 수 있다. 기본 설정에서는 시작 직후 약 20개의 무접촉 프레임(20 Hz×1초)을 baseline으로 잡으므로 초기화 중에는 손끝을 누르지 않는다. 화살표 길이와 히트맵 색은 baseline 보정된 **상대 압력 지표**이며 보정된 N 단위 힘을 뜻하지 않는다. 모의 하드웨어에서 압력이 0으로만 나오면 실시간 화면도 비어 있는 것이 정상이다.

코어의 기본 open은 **20관절 0 rad**이고, 방아쇠 완전 닫힘 목표는 왼손 엄지 `joint1..4=(-0.864,+0.864,-1.2,-1.2) rad`, 나머지 네 손가락의 각 `joint1..4=(0,+1.3,+0.78,+0.52) rad`다. 공식 기본 Hand 텔레옵의 엄지 대향 방향을 반영하되, 목표 크기는 공식 MuJoCo 모델에서 조정한 **시뮬레이션용 값**이며 실물 안전 포즈나 물체별 파지 포즈로 보정한 값은 아니다. 속도 제한 `0.5 rad/s`를 손가락 관절의 목표 변화량에 같은 비율로 적용해 중간 자세도 대향 형태를 유지한다. 완전히 편 손에서 최대 1.3 rad까지 가려면 **최소 2.6초** 동안 방아쇠를 닫아야 한다. 압력 예시 기본값(`contact_threshold=10`, `pressure_hard_cap=30` 원시 합)은 실물 보정값이 아니다. 무접촉 상태에서 leader를 완전히 열어 30개의 압력 프레임으로 baseline을 만들기 전에는 손 명령을 발행하지 않는다. [코어](../robot_pc/omy_hx5_bringup/hx5_teleop/core.py), [ROS bridge](../robot_pc/omy_hx5_bringup/hx5_teleop/ros_bridge.py), [launch](../robot_pc/omy_hx5_bringup/launch/omy_hx5_teleop.launch.py).

### 하드웨어 없이 수행한 검증

- 공식 [`scene_left.xml`](../third_party/robotis_hand/robotis_hand_description/mujoco/hx5_d20_rev2/scene_left.xml)을 MuJoCo 3.12.0으로 로드했다. 20개 관절과 position actuator의 이름·순서가 `finger_l_joint1..20`과 일치한다. [`test_hx5_mujoco.py`](../robot_pc/omy_hx5_bringup/test/test_hx5_mujoco.py)의 새 대향 포즈 방아쇠 0→0.5→1→0 구동은 **자기접촉 0건**, 관절 한계·명령 속도·추종 오차 0.03 rad 이내를 확인했다. 공식 키보드 `x`의 최대 굽힘 포즈는 같은 무부하 모델에서 자기접촉이 발생했다. 이 모델에는 촉각 센서(`nsensor=0`)가 없다. [포즈 비교 이미지](../robot_pc/preview/hx5_official_teleop_thumb_comparison.png).
- 공식 Docker 이미지의 왼손 Gazebo launch를 일회성 컨테이너 내부에서 **서버 전용**으로 실행했다. `hand_l_controller`와 `joint_state_broadcaster`가 active였고 `/joint_states` 20관절을 확인했다. 공식 손 명령 토픽에 20관절 `JointTrajectory`(j6 목표 `+0.2 rad`, 2초)를 발행하자 j6가 `0.000000→0.199957 rad`로 추종했다. 원본 launch는 RViz/Gazebo GUI를 함께 띄워 화면 없는 컨테이너에서 OpenGL 오류로 종료하므로, **컨테이너 `/tmp`의 사본에서만** `gz_args`에 `-s`를 더하고 RViz 항목을 제거했다. 공식 소스와 호스트 설정은 바꾸지 않았다. [공식 Gazebo 절차](https://docs.robotis.com/docs/systems/hx5_d20/simulation/gazebo/), [공식 왼손 launch](../third_party/robotis_hand/robotis_hand_bringup/launch/hx5_d20_left_gazebo.launch.py).
- 공식 `robotis/robotis-hand:1.0.2` 컨테이너의 실제 `robotis_interfaces/msg/HandPressures`와 ROS 2 토픽을 사용한 [`test_hx5_ros_integration.py`](../robot_pc/omy_hx5_bringup/test/test_hx5_ros_integration.py)는 가짜 leader·관절·압력 발행자로 **드라이런 계산과 20관절 명령 형식**을 검증했다. 컨테이너 내부 통합 시험이며 OMY나 HX5 실물에 연결한 결과가 아니다.
- **OMY+HX5 모의 통합 시험:** 공식 OMY, ROBOTIS Hand, RealSense 설명을 Jazzy 컨테이너에서 빌드하고 합친 Xacro를 전개했다. 4개 컨트롤러(`joint_state_broadcaster`, `arm_controller`, `hand_l_controller`, `pressure_l_broadcaster`)가 활성화됐다. [`mock_teleop_probe.py`](../robot_pc/omy_hx5_bringup/test/mock_teleop_probe.py)가 합성 leader 7관절을 넣자 팔 6관절과 왼손 20관절 명령이 각각 나왔고, 새 대향 포즈에서 검지 `joint6`의 모의 관절상태는 방아쇠 0→0.5→1→0에서 **0→0.650→1.300→0 rad**였다. 엄지 `joint1/2`도 닫힘에 따라 **-0.864/+0.864 rad**까지 움직였다. [측정 기록](../robot_pc/preview/omy_hx5_thumb_opposition_teleop_states.json). 이 결과는 END 전기 연결을 검증하지 않는다.
- **손 전용 키보드 모의 통합 시험:** Xacro를 `enable_arm_hardware:=false`로 전개하면 손용 `OMYHX5EndSystem` 1개와 왼손 20관절만 하드웨어 정의에 남는다. 실물 설정 전개 결과도 팔 시스템 없이 손 드라이버가 `/dev/ttyAMA4`로 설정되는 것을 확인했다. 모의 launch에서는 손·압력·관절상태 컨트롤러 3개만 활성화됐고, 실제 키보드 프로그램에 `]`(50% 시험 설정), `x`, `z`를 입력한 [측정 상태](../robot_pc/preview/omy_hx5_hand_only_keyboard_mock_states.json)는 검지 `joint6` **0→0.650→1.300→0 rad**, 엄지 `joint1/2` 최대 **-0.864/+0.864 rad**였다. 이 시험은 원격 키보드 명령부터 모의 손 관절까지 확인하지만 실제 User PC↔Robot PC 네트워크, END 시리얼 패킷, HX5 모터 동작은 검증하지 않는다.
- **촉각 화면 합성 시험:** 공식 `tactile_rviz`에 엄지 중앙 100, 검지 모서리 80의 합성 `HandPressures`를 넣었다. 왼손 손끝 좌표계에서 해당 두 손가락의 화살표·CoP 마커만 표시됐고, 화살표 길이는 각각 약 0.050 m·0.040 m였다. 중앙 taxel의 엄지 화살표는 법선 방향이었으며 모서리 taxel의 검지 화살표는 옆으로 기울었다. [ROS 마커 측정값](../robot_pc/preview/omy_hx5_tactile_markers_mock.json). 공식 Matplotlib 가시화 코드에도 같은 3×3 입력을 넣어 [합성 히트맵](../robot_pc/preview/omy_hx5_official_heatmap_synthetic.png)을 렌더링했다. 화살표의 크기·방향은 압력 합과 CoP로 만든 **시각적 추정치**이며 실측 3D 힘 벡터가 아니다. 이 시험은 소프트웨어 데이터 처리와 이미지 생성만 검증하며 실물 센서, ROS 네트워크 분리, 실제 GUI 표시 품질을 검증하지 않는다.
- [`test_hx5_core.py`](../robot_pc/omy_hx5_bringup/test/test_hx5_core.py)는 5×9 baseline, 접촉 손가락별 제한, 압력 목표대역 보정, 방아쇠 해제, 센서·leader 소실 및 포화 fault를 합성 입력으로 검사한다. 원시값 기준 임계와 실제 파지력은 현장에서 보정해야 한다.
- Gazebo가 관절 상한 0 rad에서 약 `1e-10 rad`의 수치 오차를 내는 경우가 있어 초기 관절 측정값에만 최대 `1e-6 rad`의 경계 허용 오차를 적용하고 명령 시 실제 모델 한계 안으로 잘라 넣는다. `1e-4 rad`처럼 더 큰 범위 초과는 계속 거부한다. [코어](../robot_pc/omy_hx5_bringup/hx5_teleop/core.py), [경계 시험](../robot_pc/omy_hx5_bringup/test/test_hx5_core.py). **위 시험의 압력은 전부 합성 또는 모의 데이터이며 실물 HX5 촉각, 접촉력, 안정 파지는 검증하지 않았다.**
- **바닥 물체 집기 동작 시험(모의, 2026-10-13):** [`mock_floor_pick_probe.py`](../robot_pc/omy_hx5_bringup/test/mock_floor_pick_probe.py)가 합성 leader 7관절을 통해 home→pregrasp→하강→방아쇠 닫기→상승을 실행했다. 새 엄지 대향 포즈로 재실행한 128개 [측정 상태](../robot_pc/preview/omy_hx5_thumb_opposition_floor_pick_states.json)에서는 검지 `joint6`이 **1.300 rad**, 엄지 방향 관절 `joint1/2`가 **-0.864/+0.864 rad**까지 움직였다. 같은 8 cm 정육면체는 여전히 들리지 않았다. 통합 MuJoCo [재생 영상](../robot_pc/preview/omy_hx5_thumb_opposition_floor_pick.gif)에서 시각 메시 접촉은 손을 닫는 동안 사라졌고, [자유 물체 근사 동역학 검사](../robot_pc/preview/omy_hx5_thumb_opposition_floor_pick_dynamics.json)의 물체 중심 높이는 초기 0.040 m에서 최종 약 0.0399 m였다. 따라서 이 물체 위치·손목 자세의 접근 경로와 접촉 위치는 추가 조정이 필요하다. 이 검사는 기록된 로봇 자세를 강제로 적용하고 시각 메시를 충돌 형상으로 사용한 진단이며, 실제 접촉력이나 실물 파지 성능을 입증하지 않는다. [검사 코드](../robot_pc/preview/check_mock_floor_pick_dynamics.py), [접촉 기록](../robot_pc/preview/omy_hx5_thumb_opposition_floor_pick_contacts.json).

## 현재 증거와 남은 현장 작업

- **확인됨:** AI Worker의 기존 4핀 케이블 재사용 절차와 SH5 통합 제어 방식, OMY+HX5 통합 Xacro 전개, ROS 2 모의 컨트롤러 기동, 합성 leader 7관절 → 팔 6관절·손 20관절 분리와 손 모의 관절 추종.
- **미확인:** OMY↔HX5 마운트 호환성, 기존 4핀 케이블의 핀 배열·정격·END 툴 버스 접근 경로, 실제 장착/배선, HX5 시리얼 통신과 토픽 수신, leader 닫힘 끝값, 촉각 임계값과 물체별 파지, Robot PC 패키지의 실물 작동.
- **실행 전 조건:** 왼손 모델과 기구 결합, 검증된 24V/RS-485 배선과 단일 버스 소유자, 하나의 손 명령 발행자, leader 양 끝값 실측, 전원 차단 수단.
