# OMY 끝단에 장착한 왼손 HX5-D20: 공식 손 bringup 시험

> **현재 실물 실행 중단:** 아래 명령은 ID 140 직접 접속을 전제로 작성되었다. 실제 OMY 배선에서는 END ID 210을 통해 손에 접근해야 하므로 실물 launch는 시작 시 차단된다. 현재 실행 가능한 읽기 검사는 [END 경유 검사 명령](hx5-d20-run-commands.md)을 따른다. 손 이동 절차는 END 경유 제어를 검증한 뒤 갱신한다.

이 절차는 텔레옵 전에 **Robot PC의 OpenMANIPULATOR 컨테이너**에서 손 자체를
확인한다. `omy_hx5_official_hand.launch.py`는 ROBOTIS의 왼손 관절·촉각 정의,
`hand_l_controller`, `effort_l_controller`, 초기 자세 파일과 키보드 입력 토픽을
사용한다. OMY 팔의 전원 경로와 END 보드(ID 210), 손 컨트롤러(ID 140)는
하나의 `controller_manager`가 담당한다. 기본 실행은 손 초기 자세 궤적과
공식 전류 명령을 **발행하지 않는다**. 일반 OMY 텔레옵도 시작하지 않는다.

공식 손 단독 launch는 `/dev/ttyUSB0`의 손 전용 연결을 전제로 한다. OMY 끝단에서
`port_name:=/dev/ttyAMA4`만 바꿔 실행하면 END 보드가 통합되지 않는다.
이 문서의 OMY용 launch를 사용하고, `omy_ai`, `omy_f3m`,
`omy_3m_unpack`, 기존 HX5 텔레옵 또는 공식 손 단독 launch를 **동시에 실행하지 않는다**.

## 0. 장착·전원 확인

- OMY의 전원을 끄고 HX5를 고정한 뒤 실제 4핀 배선의 전원·RS485 핀과 전원
  공급 경로를 확인한다. 손에 전원이 들어와 뻣뻣해지는 것만으로 통신·전류 용량은
  검증되지 않는다.
- [OMY END 공식 사양](https://ai.robotis.com/omy/hardware_omy)은 툴 출력을
  **24 V / 1 A**로, [HX5 공식 사양](https://ai.robotis.com/hands/hardware_hands.html)은
  최대 전류를 **2.6 A**로 표기한다. 현재 4핀의 전원이 같은 1 A 회로인지
  미확인이다. 이 경로가 확인되기 전에는 초기 자세 이동과 전체 쥐기 명령을
  실행하지 않는다.
- 팔이 포장 자세라면 OMY의 [공식 unpack 안내](https://docs.robotis.com/docs/systems/omy/quick_start_guide/setup_guide/)에
  따라 안전한 장착 구성에서 unpack을 먼저 완료한다. 공식 unpack launch는 팔을
  즉시 움직이고 기존 그리퍼용 END 드라이버를 사용할 수 있으므로, HX5 장착
  상태에서 바로 실행하는 명령으로 취급하지 않는다. 이미 unpack 자세라면 생략한다.

## 1. User PC → Robot PC 호스트 접속

OMY 전원을 켜고 이더넷을 연결한다. `10.42.0.241`은 이전에 확인된 직접 연결
주소이므로 현재 주소가 다르면 바꾼다. 공식 문서의 `omy-<SN>.local`은 mDNS가
동작할 때 사용할 수 있다.

```bash
ssh root@10.42.0.241
```

## 2. Robot PC 호스트: HX5 브랜치 갱신·컨테이너 진입

새 코드가 Git 원격 브랜치에 push된 후 실행한다. 이미 컨테이너가 실행 중이면
재시작하지 않는다. 아래 호스트 경로는 앞서 접속한 OMY에서 확인된 경로다.
공식 컨테이너 설정의 `./workspace:/workspace` 마운트로 컨테이너 안에서
`/workspace/SHAPE_UP_Tactile`로 보인다.

```bash
cd /data/docker/open_manipulator/docker/workspace/SHAPE_UP_Tactile
git fetch origin
git switch codex/hx5-d20
git pull --ff-only
git submodule update --init third_party/robotis_hand
git status -sb
test -f robot_pc/omy_hx5_bringup/launch/omy_hx5_official_hand.launch.py

cd /data/docker/open_manipulator
docker ps
if [ "$(docker inspect -f '{{.State.Running}}' open_manipulator 2>/dev/null)" != true ]; then
  ./docker/container.sh start
fi
./docker/container.sh enter
```

## 3. Robot PC 컨테이너: 처음 한 번 또는 코드 갱신 후 빌드

기존 OMY 패키지는 `/root/ros2_ws`에 있다. 아래 작업 공간은 새 손 bringup과
ROBOTIS 공식 손의 초기 자세 노드·키보드를 설치한다.

```bash
export OMY_HX5_REPO=/workspace/SHAPE_UP_Tactile
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
mkdir -p /workspace/omy_ws/src

[ -e /workspace/omy_ws/src/omy_hx5_bringup ] || ln -s "$OMY_HX5_REPO/robot_pc/omy_hx5_bringup" /workspace/omy_ws/src/omy_hx5_bringup
[ -e /workspace/omy_ws/src/robotis_hand_description ] || ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_description" /workspace/omy_ws/src/robotis_hand_description
[ -e /workspace/omy_ws/src/robotis_hand_bringup ] || ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_bringup" /workspace/omy_ws/src/robotis_hand_bringup
[ -e /workspace/omy_ws/src/robotis_hand_teleop ] || ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_teleop" /workspace/omy_ws/src/robotis_hand_teleop
[ -e /workspace/omy_ws/src/robotis_hand_pressure_broadcaster ] || ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_pressure_broadcaster" /workspace/omy_ws/src/robotis_hand_pressure_broadcaster
[ -e /workspace/omy_ws/src/robotis_hand_playground ] || ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_playground" /workspace/omy_ws/src/robotis_hand_playground

if [ ! -d /workspace/omy_ws/src/robotis_interfaces ]; then
  git clone --depth 1 --branch jazzy https://github.com/ROBOTIS-GIT/robotis_interfaces.git /workspace/omy_ws/src/robotis_interfaces
fi

cd /workspace/omy_ws
apt-get update
rosdep install --from-paths src --ignore-src --rosdistro jazzy -y
MAKEFLAGS=-j2 CMAKE_BUILD_PARALLEL_LEVEL=2 colcon build --symlink-install --parallel-workers 1 --packages-up-to omy_hx5_bringup
source /workspace/omy_ws/install/setup.bash
ros2 pkg prefix omy_hx5_bringup
ros2 pkg prefix robotis_hand_bringup
ros2 pkg prefix robotis_hand_teleop
```

세 `ros2 pkg prefix` 명령이 모두 설치 경로를 출력해야 한다.

## 4. 실행 터미널 공통 환경

아래의 **터미널 A, B, C마다** User PC에서 새 SSH 접속 → Robot PC 호스트에서
컨테이너 진입 → 공통 환경을 반복한다. 공식 OMY 문서도 ROS domain과 Zenoh
RMW를 같은 값으로 맞추도록 안내한다.

```bash
ssh root@10.42.0.241
cd /data/docker/open_manipulator
./docker/container.sh enter
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
source /workspace/omy_ws/install/setup.bash
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
unset ZENOH_CONFIG_OVERRIDE
```

## 5. 터미널 A: Zenoh 라우터

이미 같은 네트워크에서 라우터가 실행 중이면 중복 실행하지 않는다. 터미널을
계속 열어 둔다. [OMY 공식 Zenoh 안내](https://docs.robotis.com/docs/systems/omy/quick_start_guide/zenoh_communication/)
역시 bringup보다 라우터를 먼저 실행하도록 한다.

```bash
ros2 run rmw_zenoh_cpp rmw_zenohd
```

## 6. 터미널 B: OMY 끝단·손 bringup, 초기 동작 없음

앞의 공통 환경을 적용하고 아래를 실행한다. 이 launch는 팔을 unpack으로
이동시키지 않는다. 실제 팔·END·손 하드웨어는 초기화하므로 팔의 작업 공간을
비우고 비상정지 수단을 준비한다. 공식 손 초기 자세와 전류 퍼블리셔는 꺼져 있다.

```bash
ros2 launch omy_hx5_bringup omy_hx5_official_hand.launch.py \
  mock_arm:=false mock_hand:=false \
  init_position:=false apply_official_current:=false
```

## 7. 터미널 C: ID·관절·촉각 확인

앞의 공통 환경을 적용한다. 터미널 B 로그에서 `ID:140`의 `Ping succeeded`와
`ID:210`의 초기화를 확인한다. ID 140이 응답하지 않으면 손 키보드나
초기 자세 명령으로 넘어가지 않는다. 각 `timeout`은 응답이 없을 때 10초
뒤 종료하기 위한 것이다.

```bash
ros2 control list_hardware_components
ros2 control list_controllers
timeout 10s ros2 topic echo /joint_states --once
timeout 10s ros2 topic echo /left_hand/finger_pressures --once
ros2 topic info /leader/joint_trajectory_command_broadcaster_left_hand/joint_trajectory
```

`arm_controller`, `hand_l_controller`, `effort_l_controller`,
`pressure_l_broadcaster`가 `active`이고 관절 상태에 `finger_l_joint1`부터
`finger_l_joint20`이 있어야 한다. 마지막 명령의 subscriber가 손 컨트롤러에
연결돼 있는지도 확인한다. ID 210만 보이는 것은 HX5 통신 확인이 아니다.
터미널 B에 `Waiting for data on 'robot_description'`만 반복되면 ID 검사까지
도달하지 않은 상태다. 라우터와 `ROS_DOMAIN_ID`·`RMW_IMPLEMENTATION`을 먼저
확인한다.

## 8. 확인 후 공식 초기 자세·키보드 시험

전원 용량·손의 자유 공간·ID 140·촉각 상태를 확인한 뒤에만 진행한다.
터미널 B의 bringup을 `Ctrl+C`로 종료하고 같은 터미널에서 아래처럼 **다시
시작**한다. `init_position:=true`는 공식 YAML의 20관절 영점으로 2초 동안
손을 움직인다. `apply_official_current:=true`는 공식 launch의 20관절 전류
명령을 발행한다. 두 인자는 기본값이 `false`다.

```bash
ros2 launch omy_hx5_bringup omy_hx5_official_hand.launch.py \
  mock_arm:=false mock_hand:=false \
  init_position:=true apply_official_current:=true
```

터미널 C에서 아래의 공식 키보드를 실행한다. 프로그램의 `z`는 전체 펴기,
`x`는 전체 쥐기이며 손가락별 키도 지원한다. 처음에는 빈손·낮은 접촉에서
작은 동작을 확인한다. `ESC`로 키보드를 종료한다.

```bash
ros2 run robotis_hand_teleop hx5_d20_teleop --hand-side left
```

## 9. 종료와 이후 텔레옵

키보드 `ESC` → 터미널 B bringup `Ctrl+C` → 다른 텔레옵 launch 순서로
전환한다. 두 launch는 모두 `/dev/ttyAMA4`를 사용하므로 겹쳐 실행하지 않는다.
팔을 unpack 자세로 유지하면서 User PC 키보드로 손을 원격 제어하려면
[기존 OMY + HX5 실행 명령어](hx5-d20-run-commands.md)의
`omy_hx5_hand_live.launch.py` 절차로 넘어간다.

## 공식 문서·코드와의 관계

- [OMY 소개](https://docs.robotis.com/docs/systems/omy/introduction/)와
  [OMY 설정](https://docs.robotis.com/docs/systems/omy/quick_start_guide/setup_guide/): 전원, SSH,
  컨테이너, unpack 순서.
- [OMY Zenoh](https://docs.robotis.com/docs/systems/omy/quick_start_guide/zenoh_communication/):
  라우터를 먼저 실행하고 같은 ROS domain/RMW를 사용.
- [ROBOTIS Hand Operation Guide](https://ai.robotis.com/hands/operation_hands.html):
  왼손 컨트롤러, 초기 자세, 공식 키보드.
- [`robotis_hand` 공식 소스](https://github.com/ROBOTIS-GIT/robotis_hand):
  `hx5_d20_left.joints.xacro`, `hx5_d20_left_initial_positions.yaml`,
  `joint_trajectory_executor`, `hx5_d20_teleop`을 재사용한다.

ROS 패키지 빌드와 모의 Xacro·launch 확인은 실물 END 4핀의 전기적 적합성이나
ID 140 통신 성공을 증명하지 않는다.
