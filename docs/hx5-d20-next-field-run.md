# 다음 실물 시험: 왼손 HX5 Direct Mode 명령 순서

2026-11-04 코드 변경 이후 첫 실물 시험에서 **위에서부터 차례대로** 입력할 명령이다.
각 단계의 **확인**이 맞지 않으면 다음 단계로 가지 말고, 그 단계의 출력 전체를
기록한다. 단계별 배경 설명은 [Direct 손 실행 순서](hx5-d20-omy-direct-hand.md)와
[리더 텔레옵](hx5-d20-omy-teleop.md)에 있다.

이번 시험의 목표는 다음 순서의 확인이다.

1. 바뀐 END 읽기(90바이트 단위)와 펌웨어 버전 읽기
2. 토크·공식 Profile/P/D RAM 설정
3. 읽기 전용 런치에서 **손가락 힘이 유지되는지**
4. 단일 관절 jog의 선택성
5. 공식 키보드와 공식 초기 자세(0 자세)
6. 리더 방아쇠 손 텔레옵 드라이런과 첫 동작

**비상 정지:** 손이나 팔이 예상과 다르게 움직이면 런치 터미널에서 `Ctrl+C`를
누른다. 그래도 멈추지 않거나 힘을 즉시 빼야 하면 OMY 전원을 차단한다. 이
코드에는 손 토크를 끄는 별도 명령이 없다.

## 0. User PC — 변경 사항을 원격 브랜치에 올리기

Robot PC는 `git pull`로 코드를 받으므로, 2026-11-04 변경이 커밋·푸시돼 있어야 한다.

```bash
cd /path/to/SHAPE_UP_Tactile   # codex/hx5-d20 체크아웃
git status --short             # 커밋되지 않은 변경이 없어야 한다
git log --oneline -1
git push origin codex/hx5-d20
```

## 1. Robot PC 접속과 빌드

User PC를 OMY와 이더넷으로 연결하고 접속한다. IP가 바뀌었으면 실제 값을 쓴다.

```bash
ssh root@10.42.0.241
```

**Robot PC 호스트:**

```bash
cd /data/docker/open_manipulator/docker/workspace/SHAPE_UP_Tactile || exit 1
git switch codex/hx5-d20
git pull --ff-only
git submodule update --init third_party/robotis_hand
git log --oneline -1
cd /data/docker/open_manipulator || exit 1
if [ "$(docker inspect -f '{{.State.Running}}' open_manipulator 2>/dev/null)" != true ]; then
  ./docker/container.sh start
fi
./docker/container.sh enter
```

확인: `git log`의 커밋이 0절에서 푸시한 커밋과 같다.

**컨테이너 (빌드 터미널):**

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
cd /workspace/omy_ws
MAKEFLAGS=-j2 CMAKE_BUILD_PARALLEL_LEVEL=2 colcon build --symlink-install --parallel-workers 1 --packages-up-to omy_hx5_bringup
source /workspace/omy_ws/install/setup.bash
ros2 pkg prefix omy_hx5_bringup
```

확인: 빌드 실패 없이 설치 경로가 출력된다. 처음 만드는 컨테이너라면
[Direct 손 1절](hx5-d20-omy-direct-hand.md#1-브랜치-갱신과-빌드)의 최초 설치 블록을 먼저 실행한다.

### 이후 모든 컨테이너 터미널의 공통 환경

새 컨테이너 터미널을 열 때마다(`./docker/container.sh enter`) 먼저 입력한다.
아래에서 **[환경]** 이라고 쓴 곳이 이 블록이다.

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
source /workspace/omy_ws/install/setup.bash
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
unset ZENOH_CONFIG_OVERRIDE
```

## 2. Zenoh 라우터 (터미널 A, 계속 유지)

이미 실행 중이면 생략한다. **[환경]** 적용 후:

```bash
ros2 run rmw_zenoh_cpp rmw_zenohd
```

## 3. END·손 상태 읽기 (터미널 B)

`/dev/ttyAMA4`를 쓰는 다른 프로그램(Preset·Direct 런치, 공식 손 런치, 다른 진단)이
없어야 한다. **[환경]** 적용 후 한 줄씩 실행한다. 이 절의 명령은 손·모터 목표값을
쓰지 않는다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_recover --port /dev/ttyAMA4
```

확인: `END 210 before`가 `Stock OMY END target`과 같다. 다르면
[END 복구 절차](hx5-d20-omy-direct-hand.md#2-손-direct-mode-준비)를 따르고 여기서 멈춘다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_proxy_probe --port /dev/ttyAMA4
```

확인: `model 230 OK`, `model 261 OK, firmware N`, 전압 약 23.7 V, `status 0`.
**`firmware` 값을 기록한다**(status 32 문의용).

```bash
ros2 run omy_hx5_bringup omy_hx5_end_proxy_probe --port /dev/ttyAMA4 --hand-state
```

확인: `mode=0`, `table_sync=0`, `watchdog=0`, `tick_advanced=True`, `status=0`.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --diagnose
```

확인: `model=261, id=140`, `mode=0`, `table_sync=0`, `watchdog=0`, `status=0`.
이 명령은 바뀐 90바이트 손 읽기를 처음 실물에서 쓰는 단계다. 여기서
`did not receive a fresh HX5 response`나 이상한 model·ID가 나오면 멈추고 출력을
보낸다.

- `watchdog=255`면 아래를 실행한 뒤 `--diagnose`를 다시 실행한다.

  ```bash
  ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --clear-watchdog
  ```

- `mode=1`이면 [Direct 손 2절](hx5-d20-omy-direct-hand.md#2-손-direct-mode-준비)의
  `omy_hx5_end_direct_prepare`와 `--apply`를 먼저 실행한다. 이 두 명령은 이제
  토크·RAM 상태와 무관하게 모터 구성만 검사한다.

## 4. 모터 토크와 공식 RAM 설정 (터미널 B)

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --torque-status
```

전원을 다시 켰다면 20개 모두 `torque=0`일 것이다. 모두 `hardware_error=0`이어야 한다.

손 주변을 비운다. 토크가 켜지면 손가락이 현재 위치를 잡는다. 먼저 한 모터만:

```bash
ros2 run omy_hx5_bringup omy_hx5_end_torque_on --port /dev/ttyAMA4 --motor-id 141
```

확인: `HX5 motor torque ON verified: 1 selected`. 엄지 첫 관절이 뻣뻣해진다.
성공했을 때만 전체를 실행한다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_torque_on --port /dev/ttyAMA4
```

확인: `Official Profile/P/D RAM settings written to [...]` 목록이 출력된다.
**이미 토크가 켜진 모터도 Profile·Gain 값이 이번에 처음 쓰이므로 목록에 나온다.**

실패하면 같은 명령을 반복하지 말고 `--torque-status`로 상태를 읽은 뒤, 남은
모터를 `--motor-id`로 하나씩 처리한다. 여러 줄을 한꺼번에 붙여 넣지 않는다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --torque-status
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --verify-direct
```

확인: 20개 모두 `torque=1, hardware_error=0`. `Direct Control Mode 0 and
persistent aliases verified; idle Bus Watchdog=0`.

## 5. 읽기 전용 Direct 런치와 힘 유지 확인

**런치 전:** 검지 끝을 손가락으로 살짝 눌러 저항(뻣뻣함)을 기억한다.

**터미널 C** — **[환경]** 적용 후:

```bash
ros2 launch omy_hx5_bringup omy_hx5_end_direct_hand.launch.py \
  end_port:=/dev/ttyAMA4 allow_active_status32:=true read_only:=true
```

확인: `END 210 -> HX5 140 Direct Mode ready ... firmware=N, read_only=True,
active_status=32, held_currents=100..100`. 토크 단계 직후라면 `held_currents`는
100이다. `motor setup does not match official Xacro`가 나오면 4절을 다시 실행한다.

**힘 유지 확인:** 같은 검지를 같은 세기로 다시 누른다. **저항이 사라졌다면 즉시
`Ctrl+C`** 를 누르고 6절 이후를 진행하지 않는다. 결과(유지/사라짐)를 기록한다.

**터미널 B** — 토픽 확인:

```bash
ros2 topic echo /joint_states --once
ros2 topic echo /left_hand/finger_pressures --once
ros2 topic hz /left_hand/finger_pressures
```

확인: 손 메시지에 `finger_l_joint1..20`과 `velocity` 값 20개가 있다(팔 메시지만
나오면 다시 실행). 압력 메시지에 `finger_l_sensor1..5`가 있다. 손끝 하나를 손가락으로
누르고 `--once`를 다시 실행해 **그 손가락 센서 값이 0에서 변하는지** 기록한다.

터미널 C에서 `Ctrl+C`. 확인: 종료 로그에 `restoration` 오류가 없다. 이어서
터미널 B에서:

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --diagnose
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --torque-status
```

확인: `table_sync=0`, `watchdog=0`, `status=0`, 20개 모두 `torque=1`.

## 6. 명령 허용 런치와 단일 관절 jog

**터미널 C:**

```bash
ros2 launch omy_hx5_bringup omy_hx5_end_direct_hand.launch.py \
  end_port:=/dev/ttyAMA4 allow_active_status32:=true read_only:=false goal_current:=100
```

확인: `Direct Mode ready ... read_only=False ... trajectory_current=100`.

**터미널 B** — 검지 관절 6만 +0.03 rad. 한 번만 실행한다.

```bash
ros2 topic echo /joint_states --once
ros2 topic pub --once /omy_hx5/jog std_msgs/msg/Float64MultiArray '{data: [6.0, 0.03]}'
ros2 topic echo /joint_states --once
```

확인: 검지만 조금 움직인다. 두 `joint_states`에서 `finger_l_joint6`만 약 0.03 rad
변하고, 나머지는 측정 잡음 수준이다. **다른 손가락이 움직였는지** 기록한다. 다른
손가락이 움직였으면 여기서 멈춘다.

되돌리기:

```bash
ros2 topic pub --once /omy_hx5/jog std_msgs/msg/Float64MultiArray '{data: [6.0, -0.03]}'
```

## 7. 공식 키보드 (터미널 D)

엄지 주변을 비운다. 첫 키 입력에서 공식 키보드가 엄지 기준 자세를 함께 보내므로,
엄지가 약 0.8초 동안 크게 움직인다. **[환경]** 적용 후:

```bash
ros2 run robotis_hand_teleop hx5_d20_teleop --hand-side left
```

`q`를 한 번 눌러 검지를 조금 닫고, `a`로 편다. 실제 움직임과 `joint_states` 변화를
확인한다. `x`(전체 쥐기)는 이번 시험에서 쓰지 않는다. `ESC`로 키보드를 종료한다.

## 8. 공식 초기 자세 = 텔레옵 시작 자세 (터미널 D)

리더 텔레옵은 손이 공식 초기 자세(20관절 모두 0)에서 0.1 rad 이내일 때만 켜진다.
손 주변을 비우고 실행한다. 손이 약 2초 이상에 걸쳐 0 자세로 움직인다.

```bash
ros2 run robotis_hand_bringup joint_trajectory_executor --ros-args \
  --params-file /workspace/omy_ws/install/robotis_hand_bringup/share/robotis_hand_bringup/config/hx5_d20/hx5_d20_left_initial_positions.yaml
```

확인: `All steps completed!`. 터미널 B에서 `ros2 topic echo /joint_states --once`를
실행해 손 관절 20개가 0에서 ±0.1 rad 이내인지 기록한다. 0.1을 넘는 관절이 있으면
그 관절 번호와 값을 기록한다(리더 텔레옵 활성화가 거부된다).

터미널 C에서 `Ctrl+C`로 Direct 런치를 종료한다. 로그에 복구 오류가 없어야 한다.

## 9. 리더 방아쇠 손 텔레옵 — 팔 추종 없이

**터미널 E** — 리더가 아직 실행 중이 아니고 OMY-L100이 이 Robot PC에 연결돼 있을
때만. **[환경]** 적용 후:

```bash
ros2 launch open_manipulator_bringup omy_l100_leader_ai.launch.py use_mock_hardware:=false
```

**터미널 B** — 방아쇠 양 끝값 측정. 리더를 **완전히 편 상태**에서:

```bash
ros2 topic echo /leader/joint_trajectory --once
```

**완전히 쥔 상태**에서 다시 실행한다. 두 출력에서 `rh_r1_joint` 위치를 읽어
**터미널 C**에 입력한다.

```bash
read -rp '편 상태 rh_r1_joint 값: ' MEASURED_OPEN
read -rp '쥔 상태 rh_r1_joint 값: ' MEASURED_CLOSED
```

**터미널 C** — 손 드라이런 (팔 추종 꺼짐, 손 명령 발행 안 함):

```bash
ros2 launch omy_hx5_bringup omy_hx5_teleop.launch.py \
  mock_arm:=false mock_hand:=false start_leader:=false allow_active_status32:=true \
  goal_current:=100 \
  enable_arm_teleop:=false enable_hand_teleop:=true hand_dry_run:=true \
  leader_open:="$MEASURED_OPEN" leader_closed:="$MEASURED_CLOSED"
```

확인: `Direct Mode ready`와 손 브리지의 `dry-run grasp=...` 로그. 방아쇠를 움직이면
`grasp` 값이 0~1 사이에서 바뀐다. 손은 움직이지 않는다.

8절 뒤 Direct 런치를 껐다 켰으므로 손이 아직 0 자세 근처인지 터미널 B에서
`joint_states`로 확인한다. 벗어났다면 터미널 D에서 8절의 초기 자세 명령을 다시
실행한다(이 런치 안의 Direct 노드가 받는다).

리더 방아쇠를 **완전히 편 상태**로 두고, 손에 아무것도 닿지 않은 채 터미널 B에서:

```bash
ros2 param set /hx5_left_omy_teleop command_enabled true
```

확인: `Set parameter successful`. 거부되면 표시된 이유를 기록한다.
- `hand must be unloaded and near open pose` → 8절의 초기 자세를 다시 실행한다.
- `leader trigger must be fresh and released` → 방아쇠를 완전히 편다.

방아쇠를 **조금만** 당겼다 놓으며 손가락이 따라 굽었다 펴지는지 본다. 멈출 때:

```bash
ros2 param set /hx5_left_omy_teleop command_enabled false
```

방아쇠를 편 상태에서 터미널 C `Ctrl+C`. 팔과 손을 함께 추종하는
[리더 텔레옵 5절](hx5-d20-omy-teleop.md#5-팔과-손을-함께-텔레옵)은 이번 결과를
검토한 뒤 별도로 진행한다.

## 10. 마무리 확인 (터미널 B)

```bash
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --diagnose
ros2 run omy_hx5_bringup omy_hx5_end_direct_prepare --port /dev/ttyAMA4 --torque-status
ros2 run omy_hx5_bringup omy_hx5_end_recover --port /dev/ttyAMA4
```

확인: `table_sync=0`, `watchdog=0`, 20개 `torque=1`, END가 기존 OMY 값과 같다.

## 기록할 항목

| 항목 | 단계 |
| --- | --- |
| 손 `firmware` 값 | 3 |
| `--diagnose` 90바이트 읽기 성공 여부 | 3 |
| 토크 실패한 모터 ID와 오류 문구 | 4 |
| `held_currents` 범위 | 5 |
| 읽기 전용 런치 중 손가락 힘 유지 여부 | 5 |
| 손끝을 눌렀을 때 바뀐 센서와 값 | 5 |
| jog 때 다른 손가락 움직임 여부, joint6 전후값 | 6 |
| 키보드 `q/a` 동작 | 7 |
| 초기 자세 후 0에서 0.1 rad를 넘은 관절 | 8 |
| `command_enabled` 결과와 방아쇠 추종 | 9 |
| 모든 단계의 `END 210 write status packets missing` 출력 | 전체 |
