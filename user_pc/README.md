# leap_teleop (User PC)

LEAP Hand v1을 키보드 또는 OMY leader 그리퍼로 구동한다.
설계: `../docs/superpowers/specs/2026-10-08-leap-omy-teleop-design.md`

## 준비
이 PC(Ubuntu 24.04 + ROS 2 Jazzy)의 시스템 파이썬에 numpy, PyYAML, dynamixel-sdk, pytest가 이미 있다.
`python3-venv`/`pip`가 없으면 설치 없이 `src`를 경로에 추가해서 실행한다.

```bash
cd user_pc
export PYTHONPATH=src            # ROS를 source 한 셸이라면: export PYTHONPATH="src:$PYTHONPATH"
python3 -m pytest -q             # 하드웨어 없이 전부 통과해야 한다
```
`pip`를 쓸 수 있으면 `pip install -e ".[dev]"` 후 `leap-teleop` 명령을 쓸 수 있다. 아래에서는 `python3 -m leap_teleop.cli`로 쓴다.

## 실물 시험 순서 (건너뛰지 않는다)
> 5V 전원을 즉시 차단할 수 있어야 한다. 시험 중 손가락 주변에 손·케이블을 두지 않는다. LEAP Hand v1(16모터) 전용이다.

1. 포트 권한과 지연 설정 (`/dev/ttyUSB0`)
   ```bash
   sudo usermod -aG dialout $USER   # 이후 재로그인, 또는 임시로: sudo chmod 666 /dev/ttyUSB0
   echo 1 | sudo tee /sys/bus/usb-serial/devices/ttyUSB0/latency_timer
   ```
2. Torque OFF 연결 진단 (ID 0~15, 오류 0 확인)
   ```bash
   python3 -m leap_teleop.tools.check_hardware --port /dev/ttyUSB0
   ```
3. 편 손 영점 기록 (손을 편 자세로 고정하고 `RECORD` 입력). 결과는 `--output`으로 지정한다. 아래처럼 `config/hardware_motors.yaml`에 저장한다 (gitignore됨).
   ```bash
   python3 -m leap_teleop.tools.calibrate_motors --port /dev/ttyUSB0 --output config/hardware_motors.yaml
   ```
4. 단일 관절 ±5° 저속 시험. 반대로 움직이는 관절은 `config/hardware_motors.yaml`에서 `sign: -1`로 고친다. 옵션은 `python3 -m leap_teleop.tools.joint_test --help`.
5. 파이프라인만 확인 (하드웨어 없음): `python3 -m leap_teleop.cli --dry-run`
6. 키보드로 실물 구동: `python3 -m leap_teleop.cli` — `space`로 open/fist 토글, `q`로 종료
   - 동작이 너무 작거나 크면 `config/postures.yaml`의 `fist` 값을 조금씩 조정한다.

## leader 그리퍼로 구동
1. Robot PC에서 텔레옵(또는 leader만) 실행. User PC 쪽:
   ```bash
   source /opt/ros/jazzy/setup.bash
   export ROS_DOMAIN_ID=30
   export PYTHONPATH="src:$PYTHONPATH"
   ros2 topic echo /leader/joint_trajectory --field points[0].positions
   ```
2. leader 그리퍼를 편 상태와 쥔 상태에서 7번째 값(`rh_r1_joint`)을 읽어 `config/leader_gripper.yaml`의 `open_value` / `closed_value`에 넣는다. (현재 값은 임시값 0.0 / 1.0이다.)
3. 먼저 `--dry-run`으로 확인한 뒤 실물로 실행
   ```bash
   python3 -m leap_teleop.cli --source leader --dry-run
   python3 -m leap_teleop.cli --source leader
   ```
   토픽이 0.5초 끊기면 마지막 자세를 유지하고, 3초 끊기면 손이 열린다. `Ctrl+C`로 종료하면 Torque OFF 후 종료한다.

## 문제 해결
- `error: ... not found. Run calibrate_motors`: 3단계를 먼저 한다 (공칭 영점으로 움직이지 않는다).
- `Missing or unresponsive DYNAMIXEL IDs`: 5V 전원, USB 케이블, Dynamixel Wizard가 포트를 점유 중인지 확인한다.
- 토픽이 안 보임: 두 PC가 같은 네트워크인지, 양쪽 `ROS_DOMAIN_ID=30`인지 확인한다.
- `No module named rclpy`: `PYTHONPATH=src`가 ROS 경로를 덮어쓴 것이다. `PYTHONPATH="src:$PYTHONPATH"`로 쓴다.
