# leap_teleop (User PC)

LEAP Hand v1을 키보드 또는 OMY leader 그리퍼로 구동한다.
설계: `../docs/superpowers/specs/2026-10-08-leap-omy-teleop-design.md`

## 준비
이 PC(Ubuntu 24.04 + ROS 2 Jazzy)에서 `dynamixel-sdk`는 `ros-jazzy-dynamixel-sdk`라서 **ROS를 source 해야** 시스템 `python3`에서 import 된다.
source 하지 않은 셸에서는 `ModuleNotFoundError: dynamixel_sdk`가 난다. 둘 중 하나로 실행한다.

```bash
cd user_pc
# A) 시스템 파이썬 + ROS (leader 구동에도 필요)
source /opt/ros/jazzy/setup.bash && export PYTHONPATH="src:$PYTHONPATH" && PY=python3
# B) .venv (dynamixel-sdk 포함, 키보드·도구 전용)
export PYTHONPATH=src && PY=.venv/bin/python

$PY -m pytest -q                 # 하드웨어 없이 전부 통과해야 한다
```
`pip`를 쓸 수 있으면 `pip install -e ".[dev,hardware]"` 후 `leap-teleop` 명령을 쓸 수 있다. 아래에서는 `$PY -m leap_teleop.cli`로 쓴다. 명령은 줄이 잘리지 않게 한 줄로 붙여 넣는다.

## 실물 시험 순서 (건너뛰지 않는다)
> 5V 전원을 즉시 차단할 수 있어야 한다. 시험 중 손가락 주변에 손·케이블을 두지 않는다. LEAP Hand v1(16모터) 전용이다.

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
   - LEAP 5V는 항상 손을 편 상태에서 켠다.
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

## leader 그리퍼로 구동
Robot PC는 zenoh를 쓴다. User PC 셸 (A 방식만 가능, rclpy가 필요하다):
```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=30 RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_CONFIG_OVERRIDE='mode="client";connect/endpoints=["tcp/<ROBOT_IP>:7447"]'   # 44B1050: 10.42.0.241
export PYTHONPATH="src:$PYTHONPATH"
```
1. Robot PC에서 `zenohd`를 먼저 띄운다. User PC에서 `ros2 topic list`가 에러 없이 나오면 연결된 것이다.
2. leader 그리퍼 값: 편 상태와 쥔 상태에서 `ros2 topic echo /leader/joint_trajectory --field points`의 7번째 값(`rh_r1_joint`)을 `config/leader_gripper.yaml`의 `open_value` / `closed_value`에 넣는다. (현재 임시값 0.0 / 1.0. 10/09 편 상태 실측 약 0.197)
3. 손을 주먹으로 대기시킨 뒤 Robot PC에서 `omy_ai`를 띄운다.
   ```bash
   python3 -m leap_teleop.cli --source leader --safe-pose fist --dry-run   # 먼저 로그로 확인
   python3 -m leap_teleop.cli --source leader --safe-pose fist             # 실물: 주먹 쥐고 [teleop] waiting
   ```
   토픽이 들어오면 `[teleop] live`가 되고 손이 leader 그리퍼를 따라간다. omy_ai를 켤 때·팔을 크게 옮길 때는 leader 그리퍼를 쥔 채로, 텔레옵 중에는 **leader를 손으로 잡고** 있는다 (10/09에 leader가 갑자기 튄 적이 있다).
4. 종료: Robot PC `omy_ai` `Ctrl+C` (팔 받치기) → User PC `Ctrl+C` → `zenohd` `Ctrl+C`.
   토픽이 0.5초 끊기면 마지막 자세를 유지하고, 3초 끊기면 안전 자세로 간다. 안전 자세는 첫 입력 전(`waiting`)에도 쓰며 기본은 편 손이다. 팔이 움직이는 동안 손을 쥐고 있어야 하면 `--safe-pose fist`를 붙인다. `Ctrl+C`로 종료하면 Torque OFF 후 종료한다.

## 문제 해결
- `error: ... not found. Run calibrate_motors`: 3단계를 먼저 한다 (공칭 영점으로 움직이지 않는다).
- `Missing or unresponsive DYNAMIXEL IDs`: 5V 전원, USB 케이블, Dynamixel Wizard가 포트를 점유 중인지 확인한다.
- `No module named 'dynamixel_sdk'`: ROS를 source 하지 않은 셸이다. 준비의 A 또는 B로 실행한다.
- 토픽이 안 보임 / `[teleop] waiting`에서 안 바뀜: User PC에서 `ros2 topic info /leader/joint_trajectory`의 Publisher count를 본다. 0이면 Robot PC에서 omy_ai를 띄운 셸의 `echo $RMW_IMPLEMENTATION $ROS_DOMAIN_ID`가 `rmw_zenoh_cpp 30`인지 확인한다. 컨테이너 `.bashrc`가 로드되지 않은 셸이면 둘 다 빠져 있다(`zenohd: command not found`도 같은 원인). export 후 다시 띄운다.
- 그 외: 두 PC가 같은 네트워크인지, 포트 7447, `ZENOH_CONFIG_OVERRIDE`, Robot PC `zenohd` 실행 여부 순으로 확인한다.
- `No module named rclpy`: `PYTHONPATH=src`가 ROS 경로를 덮어쓴 것이다. `PYTHONPATH="src:$PYTHONPATH"`로 쓴다.
