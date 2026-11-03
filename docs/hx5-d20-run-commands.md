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
# dynamixel_sdk의 Python 포트 모듈. 이전 빌드 환경에는 없을 수 있음.
apt-get install -y python3-serial
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

손 컨트롤러 ID 140이 위처럼 확인된 다음, 공식 문서의 Direct Control Mode에서 내부 모터가 END를 통해 보이는지 **왼손 엄지 첫 모터 ID 141 하나만** 읽을 수 있다. 이 명령도 손에 동작 명령은 보내지 않는다. 다만 END의 EEPROM에 있는 Tool ID를 141로 잠시 바꿨다가 복원하므로 반복 실행하지 않는다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_proxy_probe --port /dev/ttyAMA4 --motor-id 141
```

이 검사에서 `motor ID 141`과 모델 번호가 나오면 END 경유 내부 모터의 주소 지정 가능성을 확인한 것이다. 실패해도 ID 140 경유 통신 성공 결과는 유지된다. 출력 전체를 기록하고 손 동작 launch는 실행하지 않는다.

최신 검사 코드는 모터 모델과 함께 Drive Mode, Operating Mode, Torque Enable, Indirect Address 1/2를 읽는다. 공식 왼손 Xacro의 첫 모터 설정과 비교하되, 한 모터만 정상이라고 20개 전체가 준비됐다고 판단하지 않는다.

모터 ID 141이 공식 XM335-T323-T 모델 1710으로 응답했다면, 다음 단계는 손 컨트롤러의 **높은 TableSync 설정 주소**를 END를 통해 읽을 수 있는지 검사하는 것이다. 아래 명령은 손의 `Indirect Address 1..5` EEPROM 값을 먼저 저장하고, 잠시 `1024..1028`로 바꿔 TableSync1의 5개 ID를 읽은 다음 원래 값으로 복원·검증한다. END의 읽기·쓰기 창과 쓰기 버퍼도 복원한다. 손가락 목표·토크 명령은 보내지 않지만 **손과 END 양쪽 EEPROM을 일시적으로 쓴다**. 검사 중 전원을 끄거나 케이블을 빼지 말고, 반복 실행하지 않는다. 복원 오류가 나면 그대로 멈추고 전체 출력을 보낸다.

손의 `Operating Mode`가 `1`(Preset Motion Mode)이어도 이 읽기 검사는 진행한다. 모드는 변경하지 않는다. 다만 손의 `TableSync Enable`이 `0`이어야 한다. 텔레옵용 직접 제어에는 나중에 별도의 모드 전환과 설정 확인이 필요하다.

```bash
ros2 run omy_hx5_bringup omy_hx5_end_proxy_probe --port /dev/ttyAMA4 --inspect-sync-ids
```

`[141, 142, 143, 144, 145]`는 공식 왼손 Xacro의 첫 손가락 TableSync 설정과 일치한다. `[255, 255, 255, 255, 255]` 등 다른 값은 아직 해당 설정이 준비되지 않았다는 뜻일 수 있다. 이 결과만으로 손 동작을 실행하지 않는다.

실측한 손 컨트롤러 `mode=1`은 Preset Motion Mode다. 이번 검사는 이 모드를 바꾸지 않았다. 직접 관절 텔레옵에는 `mode=0`과 모터·TableSync 설정이 필요하다. 또한 OMY END 출력 24 V / 1 A와 HX5 피크 전류 2.6 A의 차이가 해소되기 전에는 모드 변경·토크 활성화·손 이동 명령을 실행하지 않는다.

## 2026-11-03 현장 읽기 결과

다음 결과는 실제 손을 움직이지 않은 읽기 검사다. 추가 검사 때 기준으로 사용한다.

| 대상 | END 210을 통한 실측 |
| --- | --- |
| END 보드 | ID 210, 모델 230 |
| 왼손 컨트롤러 | ID 140, 모델 261, 입력 23.68 V, 상태 0, Operating Mode 1(Preset), TableSync Enable 0 |
| 첫 TableSync 채널 | ID 141, 142, 143, 144, 145. 간접 주소 임시 변경 후 복원 확인 |
| 엄지 첫 모터 | ID 141, 모델 1710(XM335-T323-T), Drive Mode 5, Operating Mode 5, Torque Enable 1, Indirect Address 1/2 = 126/127 |

모터 Drive Mode 5는 공식 왼손 Xacro의 ID 141 설정값 13과 다르다. [XM335 제어표](https://emanual.robotis.com/docs/en/dxl/x/xm335-t323/)에 따르면 차이인 bit 3은 **Goal Update 시 자동 토크 활성화**다. 현재 토크는 이미 켜져 있어 이 차이만으로 통신 실패를 설명할 수 없다. 다만 손 컨트롤러가 Preset Mode이고 실제 팔·손 구동 및 전원 용량은 아직 검증하지 않았다.

현재 `omy_hx5_hand_live.launch.py`, `omy_hx5_official_hand.launch.py`, 실물 `omy_hx5_teleop.launch.py`는 직접 ID 140에 접근하는 이전 드라이버 경로를 사용하므로 시작 시 명시적으로 중단된다. 이 상태에서 키보드 원격 제어를 실행해도 손은 제어되지 않는다.
