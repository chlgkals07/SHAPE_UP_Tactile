# OMY + 왼손 HX5-D20 실행 명령어

현재 단계는 **END ID 210을 통한 손 ID 140 읽기 검사**다. 기존 실물 손/텔레옵 런치는 손 ID 140에 직접 접속하려 하므로 실행이 차단된다. 손을 움직이는 명령은 아직 제공하지 않는다. 이 문서의 검사 결과로 다음 설정을 결정한다.

END 210의 Tool ID와 Table Sync 읽기 창을 임시로 바꾸고, 손 모델·전압·상태를 읽은 뒤 원래 값으로 복원한다. 손 목표 위치, 토크, 촉각 명령은 쓰지 않는다. END 설정은 EEPROM이므로 검사를 반복해서 실행하지 않는다.

## User PC 호스트 — Robot PC SSH 접속

```bash
# User PC와 OMY를 이더넷으로 연결한 뒤 실행.
# SNPR44B1050에서 마지막으로 확인된 직접 연결 IP. 재부팅 후 바뀌면 실제 IP 사용.
export OMY_ROBOT_HOST="10.42.0.241"
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
[ -e /workspace/omy_ws/src/robotis_hand_bringup ] || ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_bringup" /workspace/omy_ws/src/robotis_hand_bringup
[ -e /workspace/omy_ws/src/robotis_hand_teleop ] || ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_teleop" /workspace/omy_ws/src/robotis_hand_teleop
[ -e /workspace/omy_ws/src/robotis_hand_pressure_broadcaster ] || ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_pressure_broadcaster" /workspace/omy_ws/src/robotis_hand_pressure_broadcaster
[ -e /workspace/omy_ws/src/robotis_hand_playground ] || ln -s "$OMY_HX5_REPO/third_party/robotis_hand/robotis_hand_playground" /workspace/omy_ws/src/robotis_hand_playground

# 기존 OMY 이미지에 없는 HandPressures/TactileSensor 메시지 소스 추가.
if [ ! -d /workspace/omy_ws/src/robotis_interfaces ]; then
  git clone --depth 1 --branch jazzy https://github.com/ROBOTIS-GIT/robotis_interfaces.git /workspace/omy_ws/src/robotis_interfaces
fi

cd /workspace/omy_ws
apt-get update
rosdep install --from-paths src --ignore-src --rosdistro jazzy -y
# Robot PC 메모리 사용을 제한하기 위해 패키지 1개, 컴파일 작업 2개씩 실행.
MAKEFLAGS=-j2 CMAKE_BUILD_PARALLEL_LEVEL=2 colcon build --symlink-install --parallel-workers 1 --packages-up-to omy_hx5_bringup
source /workspace/omy_ws/install/setup.bash
```

## Robot PC 컨테이너 — END 210 경유 손 통신 확인

다른 bringup/unpack/손 프로그램이 `/dev/ttyAMA4`를 사용 중이면 먼저 해당 터미널에서 Ctrl+C로 종료한다. 아래 명령은 **Robot PC 컨테이너 안**에서, 빌드 후 실행한다. 손의 4핀 전원 용량과 핀 배열 확인 전에는 이 읽기 검사까지만 진행한다.

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
source /workspace/omy_ws/install/setup.bash
ros2 run omy_hx5_bringup omy_hx5_end_proxy_probe --port /dev/ttyAMA4
```

정상이면 `END 210: model 230 OK; left HX5 via END: ID 140, model 261 OK; voltage ...; status ...; No hand command sent.`가 출력된다. 오류가 나거나 END 설정 복원이 실패했다고 표시되면 **런치를 진행하지 말고 전체 출력**을 보내준다. 이후 손의 높은 주소에 있는 TableSync 데이터에 END를 통해 접근할 수 있는지 확인한 뒤 실제 손 제어 코드를 활성화한다.

현재 `omy_hx5_hand_live.launch.py`, `omy_hx5_official_hand.launch.py`, 실물 `omy_hx5_teleop.launch.py`는 직접 ID 140에 접근하는 이전 드라이버 경로를 사용하므로 시작 시 명시적으로 중단된다. 이 상태에서 키보드 원격 제어를 실행해도 손은 제어되지 않는다.
