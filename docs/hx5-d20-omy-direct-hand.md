# OMY 끝단 4핀으로 왼손 HX5 20관절 키보드 제어

> **2026-11-03 실물 진행:** 손 컨트롤러 ID 140, 모드 0, watchdog 0,
> 23.77 V, 상태 0과 증가하는 Realtime Tick을 확인했다. 모터 20개 모두
> Torque Enable 1, Hardware Error 0으로 읽혔고 END 설정은 기존 OMY 값으로
> 복원됐다. 첫 Direct 런치에서 간접 상태 `status=32`가 나와 중단됐다.
> 종료 후 손 주소 106의 직접 읽기는 `status=0`이었다. 아래 간접/직접
> 상태 비교 결과를 확인하기 전에는 Direct 런치를 재시도하지 않는다.

이 경로는 OMY의 END ID 210을 통해 손 컨트롤러 ID 140으로 접근한다. 로봇 PC의
별도 손 USB 포트나 외부 전원 제어 코드를 요구하지 않는다. 기존 Preset Mode 런치와
텔레옵 코드는 유지한다. **동시에 실행할 수는 없다.** 손에 연결된 실제 4핀 케이블의
통신 경로에서 END 210→손 140→첫 모터 141은 현장 읽기로 확인되었다. 20관절
Direct Mode의 물리 동작은 아직 검증 전이다.

이 구현은 ROBOTIS 공식 키보드의 20관절 ROS 토픽과 초기 위치 action, 공식 촉각
메시지 형식을 받는 **END 경유 ROS 노드**다. 공식 `hand_l_controller`를
`controller_manager`에 올리는 방식은 아니다. 팔 6관절은 기존
`arm_controller`가 맡고, 손은 이 노드가 `/dev/ttyAMA4`를 독점한다.

## 1. 브랜치 갱신과 빌드

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

## 2. 손 Direct Mode 준비

현재 현장 상태를 읽을 때는 다음 명령을 먼저 실행한다. 손의 설정이나
모터 목표값을 쓰지 않고, END 설정만 임시로 바꿨다가 복구한다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_proxy_probe --port /dev/ttyAMA4 --hand-state
```

`tick_advanced=False` 또는 비정상적인 mode·watchdog·status가 나오면
아래 Direct 준비·런치를 진행하지 않는다. 모터 141만 토크를 켜는 것으로
20관절 초기화가 완료되지는 않는다.

Direct 손 모드가 0이고 20개 모터가 토크 0인 현장 상태에서는 아래 명령으로
토크를 켠다. 실행 전 모든 대상 모터의 ID·모드·영점·간접 주소·오류·watchdog을
검사한다. 하나라도 검사에 실패하면 토크 쓰기를 시작하지 않는다. 각 모터의
목표 위치를 실제 위치로 맞추고 Goal Current를 100으로 낮춘 뒤 Torque Enable을
1로 설정한다. 도중 실패 시 이번 명령에서 켠 모터의 토크를 다시 끈다.
첫 실물 시도는 ID 141 하나로 확인한 뒤 전체 20개를 실행한다.
개별 명령을 실행할 때는 한 줄씩 입력하고, 하나라도 실패하면 다음 모터로
진행하지 않는다. 실패 후 현재 토크 상태는 아래 명령으로 확인한다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --torque-status
```

이 명령은 END 설정을 잠시 바꿨다가 복구하며 손·모터 목표값은 쓰지 않는다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_torque_on --port /dev/ttyAMA4 --motor-id 141
ros2 run omy_hx5_bringup omy_hx5_end_torque_on --port /dev/ttyAMA4
```

토크가 켜지면 손가락이 현재 위치를 잡으므로 손 주변을 비워 둔다. 위 명령은
쥐기 궤적을 보내지 않는다. 실물 결과가 확인될 때까지 아래 Direct 런치는
진행하지 않는다.

먼저 손에 쓰지 않는 진단을 실행하고 `model=261`, `id=140`, 증가한 손
`tick`, `mode`, `watchdog`, `status`, `voltage_centivolts`를 확인한다.
`end_tool_status`는 END가 기록한 도구 통신 상태다. END의 통신 설정은
진단 중 잠시 바뀌고 종료 시 원래 값으로 복구된다. `status`가 0이 아니거나,
`watchdog`가 `0`, `1..127`, `255` 밖이면 다음 명령으로 진행하지 말고
출력 전체를 기록한다. `255`는 오류 상태이며 자동 해제하지 않는다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --diagnose
```

첫 Direct 런치의 간접 상태 읽기에서 `status=32`가 나온 경우, 손 TableSync를
켜지 않은 상태에서 END의 90바이트 간접 읽기와 직접 상태 주소를 비교한다.
모터 목표값은 보내지 않는다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --compare-health-alias
```

기존 `omy_hx5_official_hand.launch.py`, 손 preset 노드, unpack/pack,
다른 `/dev/ttyAMA4` 사용자들을 종료한 상태에서 수행한다. 로봇 팔이
안정된 자세인지 확인한다. 명령은 END 경유로 20개 모터의 ID, 모델,
운용 모드, 방향 설정, 영점, 간접 주소, 토크를 공식 왼손 Xacro와 비교한다.
일치하지 않으면 **어느 모터가 다른지 보고하고 중단한다.** 모터 목표 위치는
보내지 않는다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4
```

이 확인은 손의 높은 주소를 읽기 위해 간접 주소 EEPROM을 잠시 바꾸었다가
복구한다. 반복 실행하지 않는다. 검사 출력에 `HX5 mode=1` 또는 설정이 필요한
TableSync 채널이 표시되면 다음 명령을 실행한다. 이미 `mode=0`이고 설정할
채널이 없으면 건너뛴다.
손 컨트롤러의 5개 TableSync 채널과 170개 간접 주소를 설정하고 손의
Operating Mode를 `0`(Direct Control)으로 바꾼다. 이 설정은 손의 EEPROM에
남는다. 모터 목표값은 보내지 않는다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --apply
```

`All 20 HX5 actuators identified`, `Direct Control Mode 0 ready`가
나와야 한다. 모터 설정 차이가 나오면 여기서 멈추고 실제 출력과 공식 설정을
대조한다. 손 모터 EEPROM은 이 프로그램이 자동으로 덮어쓰지 않는다.
`END 210 write status packets missing ...`이 표시되면 END 설정값은 읽기로
재확인됐더라도 손 동작 런치는 시작하지 말고 해당 출력으로 통신 상태를 검토한다.
나중에 `--restore-preset`으로 모드 1에 되돌렸다면 Direct 모드를 시작하기 전에
이 `--apply` 명령을 다시 실행해야 한다.

END 설정 복원이 중단됐다는 오류가 나오면 손 준비·런치를 멈춘다. 먼저 현재
END 값만 읽고, Tool ID 1·TableSync 0·Write Size 1 = 0 또는 12·Write Size 2 = 0인 중단 상태이거나
Tool ID 140·TableSync 0이고 나머지 설정이 모두 기존 OMY 값인 상태가
출력에 확인될 때만 `--apply`로 기존 OMY 설정을 복구한다. 이 복구 명령은
손이나 모터의 목표값을 쓰지 않는다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_recover --port /dev/ttyAMA4
```

위 출력이 이번 중단 상태와 일치하는지 확인한 뒤에만 별도로 실행한다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_recover --port /dev/ttyAMA4 --apply
```

복구 출력의 `END 210 after`가 `Stock OMY END target`과 같아야 한다.
응답 누락이나 복구 실패가 나오면 다음 손 준비·런치를 실행하지 않는다.
Direct 준비 출력이 END 버퍼 복원 단계에서 중단됐으면 복구 후 다음 명령으로
손 컨트롤러 Mode 0·watchdog·간접 주소를 확인한다. 손 목표 자세를 보내지 않는다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --verify-direct
```

Watchdog가 `255`라면 공식 제어표의 오류 상태 `-1`이다. 손 TableSync가 꺼진
상태인지 확인한 뒤 아래 명령이 주소 8에 `0`을 써서 오류를 해제한다.
손 목표 자세는 보내지 않는다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --clear-watchdog
```

그 뒤 `--verify-direct`를 다시 실행한다. 유휴 Bus Watchdog는 `0`이어야 한다.
Direct 런치가 시작될 때 `100`(2초)으로 설정하고 읽어서 확인한 뒤 손
TableSync를 켠다. Direct 세션이 끝나면 손 TableSync를 끄고 Watchdog를 `0`으로
되돌린다.

## 3. 실물 Direct Mode 런치

Robot PC의 Zenoh 라우터가 실행 중이어야 한다. 이전 OMY 실행에서 계속 켜져
있으면 그대로 사용한다. 꺼져 있다면 별도 컨테이너 터미널에서 같은 ROS 환경을
적용한 뒤 아래 명령을 실행하고 그 터미널을 유지한다.

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
source /workspace/omy_ws/install/setup.bash
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
unset ZENOH_CONFIG_OVERRIDE
ros2 run rmw_zenoh_cpp rmw_zenohd
```

ROS 환경을 적용한 새 Robot PC 컨테이너 터미널에서:

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
source /workspace/omy_ws/install/setup.bash
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
unset ZENOH_CONFIG_OVERRIDE
ros2 launch omy_hx5_bringup omy_hx5_end_direct_hand.launch.py end_port:=/dev/ttyAMA4
```

런치가 팔 컨트롤러와 손 노드를 올리고 손의 첫 상태를 읽는다. **실행만으로 팔이나
손에 목표 자세를 보내지 않는다.** `END 210 -> HX5 140 Direct Mode ready`가
표시되면 키보드 입력을 받을 수 있다. 런치 터미널은 계속 유지한다.

## 4. 공식 키보드로 첫 동작

두 번째 SSH/컨테이너 터미널에서 같은 ROS 환경을 적용한다. Robot PC 안에서
키보드를 실행하면 사용자 PC와 Robot PC 사이의 Zenoh 연결을 별도로
설정하지 않아도 된다. 같은 컨테이너의 ROS 노드끼리는 해당 시스템의
Zenoh 라우터가 켜져 있어야 한다.

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
source /workspace/omy_ws/install/setup.bash
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
unset ZENOH_CONFIG_OVERRIDE
ros2 run robotis_hand_teleop hx5_d20_teleop --hand-side left
```

공식 키보드에서 `q/a`는 검지 닫기/열기, `w/s`는 중지, `e/d`는 약지,
`r/f`는 소지, `v/c`는 엄지다. `x/z`는 전체 쥐기/펴기, `ESC`는 키보드 종료다.
처음에는 물체 없이 작은 손가락 입력부터 확인한다. 공식 키보드는 첫 명령에
엄지의 기준 목표도 함께 넣으므로 엄지가 동시에 움직일 수 있다. 이 브리지는
20관절 전체를 확인하고 제한 범위를 검사하며 최대 1 rad/s로 보간한다.

이 ROS 노드는 공식 키보드 토픽
`/leader/joint_trajectory_command_broadcaster_left_hand/joint_trajectory`,
전류 토픽 `/effort_l_controller/commands`, 초기 자세 action
`/hand_l_controller/follow_joint_trajectory`를 받는다. `JointState`와 공식
`robotis_interfaces/msg/HandPressures` 형식을 발행한다. 기존
`/omy_hx5/preset_percent`는 Direct Mode에 사용하지 않는다.

공식 제공 초기 자세 명령도 같은 bridge의 action으로 전달할 수 있다. **손이
움직이는 명령**이므로 키보드를 종료하고 주변을 비운 뒤 별도 터미널에서 실행한다.
브리지는 20관절 목표를 최대 1 rad/s로 제한한다.
공식 초기 자세 프로그램의 100개 경유점은 모두 범위와 시간 순서를 검사하고,
END 경로에서는 마지막 자세까지 제한 속도로 직선 보간한다. 따라서 공식
손 단독 드라이버의 원래 스플라인 궤적과 시간 경과가 완전히 같지는 않다.

```bash
ros2 run robotis_hand_bringup joint_trajectory_executor --ros-args \
  --params-file /workspace/omy_ws/install/robotis_hand_bringup/share/robotis_hand_bringup/config/hx5_d20/hx5_d20_left_initial_positions.yaml
```

## 5. 상태 확인과 종료

세 번째 컨테이너 터미널에서 ROS 환경을 적용한 뒤:

```bash
ros2 topic echo /joint_states --once
ros2 topic echo /left_hand/finger_pressures --once
ros2 topic hz /left_hand/finger_pressures
```

`finger_l_joint1..20`, 다섯 손가락의 3×3 촉각값, 손의 실제 움직임을 각각
확인한다. 토픽만 보이고 실제 움직임이 없으면 성공으로 간주하지 않는다.
종료는 키보드에서 `ESC`, 런치 터미널에서 `Ctrl+C` 순서다. 정상 종료 시
손의 TableSync를 끄고 END의 기존 설정과 쓰기 버퍼를 복원한다. 강제 전원 차단
또는 프로세스 강제 종료 후에는 다시 손 상태를 확인한다.

Preset 런치로 되돌리려면 Direct 런치를 먼저 종료하고 같은 컨테이너에서
아래 명령으로 손 컨트롤러를 Preset Mode `1`로 돌린다. 손 목표 위치는
보내지 않고 모드만 바꾸며 간접 주소 설정은 유지된다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --restore-preset
```

Direct 런치가 비정상 종료되어 손의 TableSync가 남은 경우에도 위 명령은
TableSync를 끄고 모드 1로 돌린다. `Preset Motion Mode 1 ready` 확인 후 기존
`omy_hx5_official_hand.launch.py`를 실행한다.

## 공식 자료

- [HX5-D20 제어표: 간접 주소와 TableSync](https://docs.robotis.com/docs/systems/hx5_d20/specifications/control_table/)
- [ROBOTIS 왼손 키보드 소스](https://github.com/ROBOTIS-GIT/robotis_hand/blob/jazzy/robotis_hand_teleop/robotis_hand_teleop/hx5_d20_teleop.py)
- [ROBOTIS 촉각 메시지 형식](https://github.com/ROBOTIS-GIT/robotis_interfaces/tree/jazzy/msg)
