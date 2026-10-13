# OMY + 왼손 HX5-D20 실행 명령어

## Robot PC — 최초 빌드

```bash
# Bash 터미널. 두 경로를 Robot PC의 실제 경로로 수정.
export OMY_HX5_REPO="/path/to/SHAPE_UP_Tactile"
export OMY_WS="/path/to/omy_ws"

git -C "$OMY_HX5_REPO" submodule update --init third_party/robotis_hand
mkdir -p ~/omy_hx5_ws/src
ln -s "$OMY_HX5_REPO/robot_pc/omy_hx5_bringup" ~/omy_hx5_ws/src/omy_hx5_bringup
ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_description" ~/omy_hx5_ws/src/robotis_hand_description
ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_pressure_broadcaster" ~/omy_hx5_ws/src/robotis_hand_pressure_broadcaster
ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_playground" ~/omy_hx5_ws/src/robotis_hand_playground

source /opt/ros/jazzy/setup.bash
source "$OMY_WS/install/setup.bash"
cd ~/omy_hx5_ws
colcon build --packages-up-to omy_hx5_bringup
source ~/omy_hx5_ws/install/setup.bash
```

## Robot PC — 실행 터미널 환경

```bash
# 새 Bash 터미널마다 실행. OMY_WS는 실제 경로로 수정.
export OMY_WS="/path/to/omy_ws"
source /opt/ros/jazzy/setup.bash
source "$OMY_WS/install/setup.bash"
source ~/omy_hx5_ws/install/setup.bash
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
```

## Robot PC / User PC — Zenoh 라우터

```bash
# 기존 OMY 네트워크 설정을 로드한 별도 터미널. 실행 중이면 생략.
source /opt/ros/jazzy/setup.bash
zenohd
```

## Robot PC — ID 140 ping 준비

```bash
# 최초 한 번. Ubuntu 호스트에서 venv가 없을 때만 설치.
sudo apt-get install python3-venv
python3 -m venv ~/omy-hx5-ping-venv
~/omy-hx5-ping-venv/bin/python -m pip install 'dynamixel-sdk==4.1.0'
```

## Robot PC — END ID 210 / 손 ID 140 확인

```bash
# 4핀 핀 배열·극성·전압·전류 용량 확인 후 통전한 상태에서 실행.
# /dev/ttyAMA4를 사용하는 모든 OMY/HX5 bringup을 먼저 중지.
# ping만 전송하며 토크 활성화·재시작·관절 목표 쓰기를 하지 않음.
~/omy-hx5-ping-venv/bin/python - <<'PY'
from dynamixel_sdk import COMM_SUCCESS, PacketHandler, PortHandler

port = PortHandler('/dev/ttyAMA4')
packet = PacketHandler(2.0)
try:
    if not port.openPort():
        raise SystemExit('Cannot open /dev/ttyAMA4; check path, permissions, and other owners')
except OSError as exc:
    raise SystemExit(f'Cannot open /dev/ttyAMA4: {exc}') from None

hand_replied = False
try:
    if not port.setBaudRate(4_000_000):
        raise SystemExit('Cannot set /dev/ttyAMA4 to 4 Mbps')
    for device_id in (210, 140):
        model, result, error = packet.ping(port, device_id)
        if result != COMM_SUCCESS:
            print(f'ID {device_id}: no reply: {packet.getTxRxResult(result)}')
        elif error:
            print(f'ID {device_id}: device error: {packet.getRxPacketError(error)}')
        else:
            print(f'ID {device_id}: ping OK, model number {model}')
            if device_id == 140:
                hand_replied = True
except OSError as exc:
    raise SystemExit(f'Serial communication failed: {exc}') from None
finally:
    port.closePort()

if not hand_replied:
    raise SystemExit('HX5 ID 140 did not reply; do not start real hand bringup')
PY
```

## Robot PC — 손 전용 모의 제어

```bash
# 아래 launch 중 하나만 실행. 다른 launch는 Ctrl+C로 종료 후 전환.
ros2 launch omy_hx5_bringup omy_hx5_hand_only.launch.py \
  mock_hand:=true hand_dry_run:=false
```

## Robot PC — 실물 손 드라이런

```bash
# 전기 조건·ID 140 통신 확인 후 실행. 팔은 이미 unpack 자세로 지지되어 있어야 함.
# 손 브리지의 궤적만 발행하지 않으며, 드라이버 초기화·토크 활성화는 진행됨.
ros2 launch omy_hx5_bringup omy_hx5_hand_only.launch.py \
  mock_hand:=false hand_dry_run:=true end_port:=/dev/ttyAMA4
```

## Robot PC — 실물 손 개폐

```bash
# 앞 단계의 드라이런 launch를 Ctrl+C로 종료한 뒤 실행.
# 팔을 이동하거나 unpack 자세로 유지하는 명령은 포함하지 않음.
ros2 launch omy_hx5_bringup omy_hx5_hand_only.launch.py \
  mock_hand:=false hand_dry_run:=false end_port:=/dev/ttyAMA4
```

## Robot PC — 상태 확인용 별도 터미널

```bash
ros2 control list_hardware_components
ros2 control list_controllers
ros2 topic echo /omy_hx5_end/dxl_state --once
ros2 topic echo /joint_states --once
ros2 topic echo /left_hand/finger_pressures --once
ros2 topic hz /left_hand/finger_pressures
```

## User PC — 키보드 원격 제어

```bash
# Bash 터미널. 현재 개발 PC의 HX5 작업 폴더.
export OMY_HX5_REPO="/home/jiwoo/.codex/worktrees/hx5-d20/SHAPE_UP_Tactile"
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp

# ]: 5% 닫기, [: 5% 열기, z: 모두 열기, x: 모두 닫기, ESC: 종료.
# 실물 첫 동작은 [ 또는 ]로 작은 범위부터 확인.
python3 "$OMY_HX5_REPO/user_pc/omy_hx5_keyboard.py" --step 0.05
```

## User PC — 촉각 히트맵 / RViz

```bash
# 키보드와 별도 Bash 터미널.
export OMY_HX5_REPO="/home/jiwoo/.codex/worktrees/hx5-d20/SHAPE_UP_Tactile"
source /opt/ros/jazzy/setup.bash
source /home/jiwoo/Projects/hx5_tactile_viz_ws/install/setup.bash
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
bash "$OMY_HX5_REPO/user_pc/run_hx5_tactile_viz.sh"
```

## Robot PC — 팔·손 리더 텔레옵 드라이런

```bash
# 손 전용 launch를 종료한 뒤, 팔까지 시험할 때만 실행.
# 팔은 리더를 따라 움직이며 손 궤적만 드라이런.
# leader 열린 값·닫힌 값 및 장착 좌표는 실측값을 입력.
read -r -p 'leader open rh_r1_joint: ' MEASURED_OPEN
read -r -p 'leader closed rh_r1_joint: ' MEASURED_CLOSED
read -r -p 'hand mount xyz (X Y Z): ' MEASURED_MOUNT_XYZ
read -r -p 'hand mount rpy (ROLL PITCH YAW): ' MEASURED_MOUNT_RPY

ros2 launch omy_hx5_bringup omy_hx5_teleop.launch.py \
  mock_arm:=false mock_hand:=false start_leader:=true mock_leader:=false \
  enable_arm_teleop:=true enable_hand_teleop:=true hand_dry_run:=true \
  leader_open:="$MEASURED_OPEN" leader_closed:="$MEASURED_CLOSED" \
  hand_mount_xyz:="$MEASURED_MOUNT_XYZ" hand_mount_rpy:="$MEASURED_MOUNT_RPY"
```

## Robot PC — 팔·손 리더 텔레옵 실행

```bash
# 앞 단계 launch를 종료한 뒤 같은 터미널에서 실행. 팔과 손 모두 움직임.
ros2 launch omy_hx5_bringup omy_hx5_teleop.launch.py \
  mock_arm:=false mock_hand:=false start_leader:=true mock_leader:=false \
  enable_arm_teleop:=true enable_hand_teleop:=true hand_dry_run:=false \
  leader_open:="$MEASURED_OPEN" leader_closed:="$MEASURED_CLOSED" \
  hand_mount_xyz:="$MEASURED_MOUNT_XYZ" hand_mount_rpy:="$MEASURED_MOUNT_RPY"
```
