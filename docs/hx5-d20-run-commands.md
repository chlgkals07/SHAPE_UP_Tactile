# OMY + 왼손 HX5-D20 실행 명령어

## User PC 호스트 — Robot PC SSH 접속

```bash
# Bash 터미널. 10/09에 사용한 호스트 이름: omy-snpr44b1050.local.
read -rp 'OMY 호스트 이름(omy-...local): ' OMY_ROBOT_HOST
ssh root@"$OMY_ROBOT_HOST"
```

## Robot PC 호스트 — HX5 브랜치 받기 / 갱신

```bash
# User PC에서 codex/hx5-d20 브랜치 commit/push 완료 후 실행.
# 이 경로는 Docker의 /workspace에 공유되어 컨테이너 재생성 후에도 보존됨.
hostname -I
mkdir -p /data/docker/open_manipulator/docker/workspace
cd /data/docker/open_manipulator/docker/workspace
if [ ! -d SHAPE_UP_Tactile ]; then
  git clone --branch codex/hx5-d20 --single-branch https://github.com/chlgkals07/SHAPE_UP_Tactile.git SHAPE_UP_Tactile || exit 1
fi
cd SHAPE_UP_Tactile || exit 1
git fetch origin || exit 1
git switch codex/hx5-d20 || exit 1
git pull --ff-only || exit 1
git submodule update --init third_party/robotis_hand
```

## Robot PC 호스트 — OpenMANIPULATOR 컨테이너 진입

```bash
cd /data/docker/open_manipulator
docker ps
# 이미 실행 중인 컨테이너는 재시작하지 않음.
if [ "$(docker inspect -f '{{.State.Running}}' open_manipulator 2>/dev/null)" != true ]; then
  ./docker/container.sh start
fi
./docker/container.sh enter
```

## Robot PC 컨테이너 — 최초 빌드

```bash
# 원래 OMY 패키지는 /root/ros2_ws, 추가 패키지는 main 현장 문서의 /workspace/omy_ws 사용.
export OMY_HX5_REPO="/workspace/SHAPE_UP_Tactile"
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash

mkdir -p /workspace/omy_ws/src
# 최초 한 번. 이미 연결한 링크는 다시 만들지 않음.
[ -e /workspace/omy_ws/src/omy_hx5_bringup ] || ln -s "$OMY_HX5_REPO/robot_pc/omy_hx5_bringup" /workspace/omy_ws/src/omy_hx5_bringup
[ -e /workspace/omy_ws/src/robotis_hand_description ] || ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_description" /workspace/omy_ws/src/robotis_hand_description
[ -e /workspace/omy_ws/src/robotis_hand_pressure_broadcaster ] || ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_pressure_broadcaster" /workspace/omy_ws/src/robotis_hand_pressure_broadcaster
[ -e /workspace/omy_ws/src/robotis_hand_playground ] || ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_playground" /workspace/omy_ws/src/robotis_hand_playground

cd /workspace/omy_ws
colcon build --symlink-install --packages-up-to omy_hx5_bringup
source /workspace/omy_ws/install/setup.bash
```

## User PC 호스트 — 터미널 A / B / C마다 새 SSH 접속

```bash
read -rp 'OMY 호스트 이름(omy-...local): ' OMY_ROBOT_HOST
ssh root@"$OMY_ROBOT_HOST"
```

## Robot PC 호스트 — 터미널마다 컨테이너 진입

```bash
cd /data/docker/open_manipulator
./docker/container.sh enter
```

## Robot PC 컨테이너 — 터미널마다 공통 환경

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
source /workspace/omy_ws/install/setup.bash
export OMY_HX5_REPO="/workspace/SHAPE_UP_Tactile"
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
```

## Robot PC 컨테이너 — 기존 자동 실행 / 포트 점유 확인

```bash
# 기존 follower/leader bringup이 실행 중이면 원래 실행 절차로 중지한 뒤 HX5 launch 실행.
# 기존 omy_ai와 HX5 launch를 동시에 실행하지 않음.
ros2 node list
pgrep -af 'ros2_control_node|omy_ai|rmw_zenohd|zenohd'
```

## Robot PC 컨테이너 · 터미널 A — Zenoh 라우터

```bash
# 이미 라우터가 실행 중이면 생략. 이 터미널은 계속 유지.
# main의 zenohd alias 대신 .bashrc 의존성이 없는 명령 사용.
ros2 run rmw_zenoh_cpp rmw_zenohd
```

## Robot PC 컨테이너 — ID 140 ping 준비

```bash
# 컨테이너 root 셸에서 최초 한 번.
apt-get update
apt-get install -y python3-venv
python3 -m venv /workspace/hx5_ping_venv
/workspace/hx5_ping_venv/bin/python -m pip install 'dynamixel-sdk==4.1.0'
```

## Robot PC 컨테이너 — END ID 210 / 손 ID 140 확인

```bash
# 4핀 핀 배열·극성·전압·전류 용량 확인 후 통전한 상태에서 실행.
# /dev/ttyAMA4를 사용하는 모든 OMY/HX5 bringup을 먼저 중지.
# ping만 전송하며 토크 활성화·재시작·관절 목표 쓰기를 하지 않음.
/workspace/hx5_ping_venv/bin/python - <<'PY'
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

## Robot PC 컨테이너 · 터미널 B — 손 전용 모의 제어

```bash
# 아래 launch 중 하나만 실행. 다른 launch는 Ctrl+C로 종료 후 전환.
ros2 launch omy_hx5_bringup omy_hx5_hand_only.launch.py \
  mock_hand:=true hand_dry_run:=false
```

## Robot PC 컨테이너 · 터미널 B — 실물 손 드라이런

```bash
# 전기 조건·ID 140 통신 확인 후 실행. 팔은 이미 unpack 자세로 지지되어 있어야 함.
# 손 브리지의 궤적만 발행하지 않으며, 드라이버 초기화·토크 활성화는 진행됨.
ros2 launch omy_hx5_bringup omy_hx5_hand_only.launch.py \
  mock_hand:=false hand_dry_run:=true end_port:=/dev/ttyAMA4
```

## Robot PC 컨테이너 · 터미널 B — 실물 손 개폐

```bash
# 앞 단계의 드라이런 launch를 Ctrl+C로 종료한 뒤 실행.
# 팔을 이동하거나 unpack 자세로 유지하는 명령은 포함하지 않음.
ros2 launch omy_hx5_bringup omy_hx5_hand_only.launch.py \
  mock_hand:=false hand_dry_run:=false end_port:=/dev/ttyAMA4
```

## Robot PC 컨테이너 · 터미널 C — 상태 확인

```bash
# 새 SSH 세션 → 컨테이너 진입 → 아래 공통 환경 source 후 실행.
ros2 control list_hardware_components
ros2 control list_controllers
# dxl_state는 실물 드라이버만 발행. mock 모드에서는 다음 한 줄 생략.
ros2 topic echo /omy_hx5_end/dxl_state --once
ros2 topic echo /joint_states --once
ros2 topic echo /left_hand/finger_pressures --once
ros2 topic hz /left_hand/finger_pressures
```

## User PC — 키보드 원격 제어

```bash
# User PC 호스트의 Bash 터미널. 현재 HX5 브랜치 작업 폴더.
export OMY_HX5_REPO="/home/jiwoo/.codex/worktrees/hx5-d20/SHAPE_UP_Tactile"
source /opt/ros/jazzy/setup.bash
read -rp '현재 Robot PC IP: ' OMY_ROBOT_IP
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_CONFIG_OVERRIDE="mode=\"client\";connect/endpoints=[\"tcp/${OMY_ROBOT_IP}:7447\"]"
ros2 daemon stop

# ]: 5% 닫기, [: 5% 열기, z: 모두 열기, x: 모두 닫기, ESC: 종료.
# 실물 첫 동작은 [ 또는 ]로 작은 범위부터 확인.
python3 "$OMY_HX5_REPO/user_pc/omy_hx5_keyboard.py" --step 0.05
```

## User PC — 촉각 히트맵 / RViz

```bash
# User PC 호스트의 별도 Bash 터미널. Robot PC SSH 셸 밖에서 실행.
export OMY_HX5_REPO="/home/jiwoo/.codex/worktrees/hx5-d20/SHAPE_UP_Tactile"
source /opt/ros/jazzy/setup.bash
source /home/jiwoo/Projects/hx5_tactile_viz_ws/install/setup.bash
read -rp '현재 Robot PC IP: ' OMY_ROBOT_IP
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_CONFIG_OVERRIDE="mode=\"client\";connect/endpoints=[\"tcp/${OMY_ROBOT_IP}:7447\"]"
ros2 daemon stop
bash "$OMY_HX5_REPO/user_pc/run_hx5_tactile_viz.sh"
```

## Robot PC 컨테이너 · 터미널 B — 팔·손 리더 텔레옵 드라이런

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

## Robot PC 컨테이너 · 터미널 B — 팔·손 리더 텔레옵 실행

```bash
# 앞 단계 launch를 종료한 뒤 같은 터미널에서 실행. 팔과 손 모두 움직임.
ros2 launch omy_hx5_bringup omy_hx5_teleop.launch.py \
  mock_arm:=false mock_hand:=false start_leader:=true mock_leader:=false \
  enable_arm_teleop:=true enable_hand_teleop:=true hand_dry_run:=false \
  leader_open:="$MEASURED_OPEN" leader_closed:="$MEASURED_CLOSED" \
  hand_mount_xyz:="$MEASURED_MOUNT_XYZ" hand_mount_rpy:="$MEASURED_MOUNT_RPY"
```

## 참고한 main 실행 순서

[최신 main의 OMY 실행표](https://github.com/chlgkals07/SHAPE_UP_Tactile/blob/254084dbff5e0b1bfc85020403ec88999a7159e3/docs/data_preparation/omy_demonstration_runbook.md) · [10/09 SSH·컨테이너·Zenoh 현장 기록](field-test/2026-10-09-omy-leap-field-test.md)
