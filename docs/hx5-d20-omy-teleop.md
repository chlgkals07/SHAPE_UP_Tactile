# OMY + 왼손 HX5-D20 리더 텔레옵 실행

> **2026-11-03 실물 Direct 런치 대기:** 손 ID 140의 정상 상태와
> 20개 모터의 토크 1·하드웨어 오류 0을 확인했다. Direct 런치와 키보드
> 손가락 동작은 아직 실물 검증 전이다.
>
> **2026-11-04 코드 변경 — 실물 재검증 전:** 실물 텔레옵 런치가
> `allow_active_status32`·`read_only`·`goal_current`를 Direct 손 런치에
> 전달한다. 손 TableSync를 켤 때마다 `status=32`가 재현되므로 아래 실물 런치
> 명령은 모두 `allow_active_status32:=true`를 넣는다. 손 브리지는 실측 시작
> 자세가 URDF 한계를 0.1 rad 이내로 넘으면(2026-11-03 joint17 −0.649 rad)
> 한계값에서 시작한다. Direct 노드는 마지막 명령값에서 보간한다. 변경 내용은
> [Direct 손 실행 순서](hx5-d20-omy-direct-hand.md)의 첫 안내를 따른다.

실물 손은 OMY의 END ID 210을 경유해 제어한다. **Direct Mode의 20관절 리더 텔레옵은 아직 실물 검증 전**이다. 아래 0절에서 브랜치 갱신·빌드·Direct Mode 준비를 완료한다. 처음 연결한다면 1절의 공식 키보드 시험으로 작은 손가락 동작을 먼저 확인한다.

시작 전에는 Preset 런치, 공식 손 키보드, 기존 `omy_hx5_hand_live.launch.py`, END 진단 프로그램을 종료한다. `/dev/ttyAMA4`는 한 프로세스만 사용해야 한다. 팔과 손의 시작 자세, 케이블 간섭, 즉시 전원 차단 방법을 확인한다.

## 0. Robot PC 접속·빌드·Direct Mode 준비

User PC에서 OMY 호스트에 SSH 접속한다. IP는 현재 실제 값으로 바꾼다.

```bash
ssh root@10.42.0.241
```

Robot PC **호스트**에서:

```bash
cd /data/docker/open_manipulator/docker/workspace/SHAPE_UP_Tactile || exit 1
git switch codex/hx5-d20
git pull --ff-only
git submodule update --init third_party/robotis_hand
cd /data/docker/open_manipulator || exit 1
if [ "$(docker inspect -f '{{.State.Running}}' open_manipulator 2>/dev/null)" != true ]; then
  ./docker/container.sh start
fi
./docker/container.sh enter
```

Robot PC **컨테이너**에서 최초 한 번 소스 패키지를 연결하고 의존성을 설치한다.
이미 준비한 작업공간이라면 아래 블록을 건너뛰고 다음 빌드 블록부터 실행한다.

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

apt-get update
apt-get install -y python3-serial
rosdep install --from-paths /workspace/omy_ws/src --ignore-src --rosdistro jazzy -y
```

최초 설치 후와 HX5 브랜치를 갱신한 뒤에는 같은 컨테이너에서 빌드한다.

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
cd /workspace/omy_ws
MAKEFLAGS=-j2 CMAKE_BUILD_PARALLEL_LEVEL=2 colcon build --symlink-install --parallel-workers 1 --packages-up-to omy_hx5_bringup
source /workspace/omy_ws/install/setup.bash
ros2 pkg prefix omy_hx5_bringup
ros2 pkg prefix robotis_hand_teleop
ros2 pkg prefix robotis_interfaces
```

다른 손 런치와 END 진단 프로그램을 종료하고, 팔이 안정된 자세인지 확인한다.
OMY나 손 전원을 다시 켠 뒤라면 먼저 손 모터 토크와 공식 Profile·P/D Gain
RAM 값을 설정한다. 손가락이 현재 위치를 잡으므로 주변을 비운다. 자세한 확인
순서는 [Direct 손 준비](hx5-d20-omy-direct-hand.md#2-손-direct-mode-준비)를 따른다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_torque_on --port /dev/ttyAMA4
```

손 모터 20개의 모델·설정을 검사한다. 결과가 다르면 여기서 중단한다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4
```

검사가 성공한 뒤 출력에 `HX5 mode=1` 또는 설정이 필요한 TableSync 채널이
표시되면 실행한다. 손 컨트롤러의 TableSync 설정과 Operating Mode `0`을
손 EEPROM에 기록한다. `Direct Control Mode 0 ready`를 확인한다. 이미
`mode=0`이고 설정할 채널이 없으면 건너뛴다. 나중에 Preset Mode로 되돌린
경우에는 이 명령으로 다시 Direct Mode로 전환한다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --apply
```

## 1. Robot PC 컨테이너: 공통 ROS 환경

아래 설정은 **새 컨테이너 터미널마다** 적용한다.

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
source /workspace/omy_ws/install/setup.bash
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
unset ZENOH_CONFIG_OVERRIDE
```

Robot PC의 Zenoh 라우터가 꺼져 있다면, 별도 터미널에서 위 환경을 적용하고 실행한 채 둔다.

```bash
ros2 run rmw_zenoh_cpp rmw_zenohd
```

### 처음 연결할 때: 공식 키보드로 작은 손 동작 확인

**첫 번째 컨테이너 터미널**에서 1절의 ROS 환경을 적용하고 실행한다.

```bash
ros2 launch omy_hx5_bringup omy_hx5_end_direct_hand.launch.py \
  end_port:=/dev/ttyAMA4 allow_active_status32:=true goal_current:=100
```

`END 210 -> HX5 140 Direct Mode ready`가 나온 뒤 **두 번째 컨테이너
터미널**에서 같은 ROS 환경을 적용하고 공식 왼손 키보드를 실행한다.

```bash
ros2 run robotis_hand_teleop hx5_d20_teleop --hand-side left
```

주변을 비우고 `q/a`로 검지를 조금 닫고 편다. 첫 명령은 엄지 기준 자세도
포함하므로 엄지가 약 0.8초 동안 크게 움직일 수 있다. 손의 실제 동작과 `/joint_states`의 손 관절 변화를 확인한다.
키보드에서 `ESC`, 손 런치에서 `Ctrl+C`로 종료한 뒤 리더 텔레옵으로 넘어간다.
이미 이 실물 확인을 마쳤다면 이 단계를 반복하지 않는다.

## 2. 리더 실행과 방아쇠 양 끝값 측정

리더가 아직 실행되지 않았고 OMY-L100이 이 Robot PC에 연결돼 있다면, 별도 터미널에서 실행한다. 이미 실행 중이면 중복 실행하지 않는다.

```bash
ros2 launch open_manipulator_bringup omy_l100_leader_ai.launch.py use_mock_hardware:=false
```

리더를 **완전히 편 상태**로 잡고 실행한다.

```bash
ros2 topic echo /leader/joint_trajectory --once
```

리더를 **완전히 쥔 상태**로 잡고 다시 실행한다. 두 출력에서 `joint_names`의 `rh_r1_joint`에 대응하는 `positions` 값을 기록한다.

```bash
ros2 topic echo /leader/joint_trajectory --once
```

```bash
read -rp '편 상태 rh_r1_joint 값: ' MEASURED_OPEN
read -rp '쥔 상태 rh_r1_joint 값: ' MEASURED_CLOSED
```

이후 런치 명령은 **두 변수를 입력한 같은 터미널**에서 실행한다. 예전 LEAP 측정값이나 임의의 0/1을 넣지 않는다.

## 3. 팔 추종 없이 손 드라이런

```bash
ros2 launch omy_hx5_bringup omy_hx5_teleop.launch.py \
  mock_arm:=false mock_hand:=false start_leader:=false allow_active_status32:=true \
  enable_arm_teleop:=false enable_hand_teleop:=true hand_dry_run:=true \
  leader_open:="$MEASURED_OPEN" leader_closed:="$MEASURED_CLOSED"
```

런치 터미널을 유지한다. 이 설정은 손 목표 관절값을 발행하지 않지만 END Direct 노드가 손 상태를 읽고 TableSync 통신을 활성화한다. TableSync를 켜기 전에 각 모터가 잡고 있는 목표값을 손에 복사하므로 손가락의 힘이 빠지지 않아야 한다. 전체 손 궤적 전류는 공식 기본값 300이며, 처음에는 `goal_current:=100`을 덧붙여 낮출 수 있다. **다른 컨테이너 터미널**에서 1절의 ROS 환경을 적용한 후 확인한다.

```bash
ros2 control list_controllers
ros2 topic echo /joint_states --once
ros2 topic echo /left_hand/finger_pressures --once
```

`joint_states`는 팔과 손이 각각 발행하므로 팔 관절만 보이면 명령을 반복한다. 팔 컨트롤러가 활성이고 손 메시지에 `finger_l_joint1..20`, 촉각 메시지에 다섯 손가락 센서가 있어야 한다. 리더 방아쇠를 움직여 손 브리지의 `dry-run grasp=...` 로그도 확인한다. 값이 갱신되지 않거나 손 노드가 종료되면 여기서 중단한다.

## 4. 팔 추종 없이 리더로 손만 첫 동작

손 명령은 손 관절이 공식 초기 자세(20관절 모두 0)에서 0.1 rad 이내일 때만 켜진다. 실물 손의 정지 자세는 이 범위를 벗어나므로(2026-11-03 실측 joint6 약 1.50 rad), 런치를 유지한 채 다른 터미널에서 공식 초기 자세 명령으로 손을 먼저 편다. 손이 약 2초 이상에 걸쳐 움직인다.

```bash
ros2 run robotis_hand_bringup joint_trajectory_executor --ros-args \
  --params-file /workspace/omy_ws/install/robotis_hand_bringup/share/robotis_hand_bringup/config/hx5_d20/hx5_d20_left_initial_positions.yaml
```

손과 주변 물체가 떨어져 있고 리더 방아쇠가 열린 상태에서, **확인용 터미널**에서 손 명령을 켠다.

```bash
ros2 param set /hx5_left_omy_teleop command_enabled true
```

손가락을 조금만 굽혔다 펴면서 실제 20관절 상태와 촉각값을 본다. 손 명령을 다시 멈추려면:

```bash
ros2 param set /hx5_left_omy_teleop command_enabled false
```

손을 편 뒤 런치 터미널에서 `Ctrl+C`로 종료한다. `command_enabled=false`는 손의 새 명령만 멈추며 토크를 끄지 않는다.

## 5. 팔과 손을 함께 텔레옵

리더의 팔 자세와 follower의 현재 자세를 맞추고 작업 공간을 비운 뒤, **2절의 변수가 남아 있는 터미널**에서 실행한다. 팔은 리더 관절을 즉시 따라갈 수 있다.

```bash
ros2 launch omy_hx5_bringup omy_hx5_teleop.launch.py \
  mock_arm:=false mock_hand:=false start_leader:=false allow_active_status32:=true \
  enable_arm_teleop:=true enable_hand_teleop:=true hand_dry_run:=true \
  leader_open:="$MEASURED_OPEN" leader_closed:="$MEASURED_CLOSED"
```

상태를 다시 확인하고, 손이 열린 무접촉 상태에서 별도 터미널로 손 명령을 켠다.

```bash
ros2 param set /hx5_left_omy_teleop command_enabled true
```

종료할 때는 리더 방아쇠를 열어 손이 펴진 것을 확인한 뒤, 손 명령을 끄고 런치 터미널에서 `Ctrl+C`를 누른다. 손 토크는 명령 중지와 별개다.

실물 촉각 히트맵과 RViz는 [User PC 실행 안내](../user_pc/README.md#hx5-촉각-신호-보기)를 따른다. 오늘의 빌드·통신 오류는 [현장 오류 기록](field-test/2026-11-03-omy-hx5-errors.md)에 정리돼 있다.
