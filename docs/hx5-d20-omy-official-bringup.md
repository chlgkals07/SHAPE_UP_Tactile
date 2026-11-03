# OMY 끝단에 장착한 왼손 HX5-D20: END 경유 Preset bringup

실물 모드에서는 OMY 팔을 기존 ros2_control로, 왼손 HX5를 END 210을 경유하는
Preset Mode 노드로 구동한다. 런치만 실행하면 손가락 이동 명령은 보내지 않는다.
END 210→손 140 통신과 Preset Mode(1)는 이전 현장 읽기 검사에서 확인했다.

이 절차는 텔레옵 전에 **Robot PC의 OpenMANIPULATOR 컨테이너**에서 손 자체를
확인한다. `omy_hx5_official_hand.launch.py`는 공식 왼손 URDF를 쓰지만, **실물
Preset Mode에서는 공식 20관절 컨트롤러를 실행하지 않는다.** 팔 컨트롤러와
END 경유 손 노드가 각각 포트를 소유한다. `init_position:=false`와
`apply_official_current:=false`에서는 공식 초기 궤적과 전류 명령을 보내지 않는다.
일반 OMY 텔레옵도 시작하지 않는다.

공식 손 단독 launch는 `/dev/ttyUSB0`의 손 전용 연결을 전제로 한다. OMY 끝단에서
`port_name:=/dev/ttyAMA4`만 바꿔 실행하면 END 보드가 통합되지 않는다.
이 문서의 OMY용 launch를 사용하고, `omy_ai`, `omy_f3m`,
`omy_3m_unpack`, 기존 HX5 텔레옵 또는 공식 손 단독 launch를 **동시에 실행하지 않는다**.

## 0. 실행 조건

- 장착 및 전원 경로는 사용자가 확인했다. 앞선 읽기 검사에서 END 210,
  왼손 140(모델 261), Preset Mode 1, 상태 0이 확인됐다.
- `/dev/ttyAMA4`를 쓰는 다른 손·END 프로그램을 종료한다. 이 런치의
  END 노드가 포트를 독점해야 한다.
- 팔이 포장 자세라면 OMY의 [공식 unpack 안내](https://docs.robotis.com/docs/systems/omy/quick_start_guide/setup_guide/)에
  따라 unpack을 먼저 완료한다. 공식 unpack launch는 팔을 즉시 움직이고
  기존 그리퍼용 END 드라이버를 사용할 수 있으므로, HX5 장착 상태에서
  바로 실행하는 명령으로 취급하지 않는다. 이미 unpack 자세라면 생략한다.

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

## 6. 터미널 B: OMY 팔 + END 경유 손 bringup

앞의 공통 환경을 적용하고 아래를 실행한다. 팔은 현재 자세에서 시작하며
unpack 동작을 실행하지 않는다. 손 ID 140은 END ID 210 경유로 확인한다.
손의 Preset Mode(1), 상태값, 전압을 읽지만 **손을 움직이는 Preset 명령이나
손의 간접 주소 설정은 보내지 않는다.** 첫 Preset 명령을 받을 때 간접 주소를
임시로 설정하며, 종료 시 END 설정과 손의 간접 주소를 복원한다.

```bash
ros2 launch omy_hx5_bringup omy_hx5_official_hand.launch.py \
  mock_arm:=false mock_hand:=false \
  init_position:=false apply_official_current:=false
```

터미널 B에 `END 210 -> left HX5 140 ready`와 `No motion command sent`가
나오고, 프로세스가 계속 실행 중이어야 한다. 실패하면 출력 전체를 확인한다.
이 런치가 실행 중일 때는 별도의 `omy_hx5_end_proxy_probe`를 실행하지 않는다.

## 7. 터미널 C: 준비 상태와 첫 작은 Preset 동작

새 SSH/컨테이너 터미널에서 4절의 공통 환경을 다시 적용한다. 현재 실물 모드의
`joint_state_broadcaster`와 `arm_controller`는 팔 전용이다. 손의 20개 관절·촉각
토픽과 공식 `hand_l_controller`는 아직 제공하지 않는다.

```bash
ros2 control list_controllers
ros2 topic info /omy_hx5/preset_percent
timeout 10s ros2 topic echo /joint_states --once
```

`arm_controller`가 `active`이고 Preset 토픽 구독자가 1개인지 확인한다.
손 주위 공간을 비운 뒤 아래 명령을 실행하면 **첫 손 이동 명령**이 전달된다.
공식 Preset Index 0의 시작·끝 동작은 손에 저장된 프리셋 설정에 따른다.
처음에는 5%만 시험하고 터미널 B의 레지스터 확인 로그와 실제 손 움직임을
같이 확인한다. 명령 수신과 레지스터 echo만으로 물리적 이동은 증명되지 않는다.

```bash
ros2 topic pub --once /omy_hx5/preset_percent std_msgs/msg/Int32 '{data: 5}'
```

기본값은 Preset Index 0, 이동 시간 1000 ms다. 0~100% 값을 받으며,
이 값은 공식 손 제어표의 Preset Motion Index(2017)에 대응한다.
0%는 저장된 시작 자세, 100%는 끝 자세다. 다른 프리셋을 사용하려면 런치의
`omy_hx5_end_preset` 노드 인자를 코드에서 조정해야 한다. 이 경로는
공식 키보드의 20관절 명령과 호환되지 않는다.

## 8. 종료

터미널 B에서 `Ctrl+C`로 종료한다. 정상 종료 시 END와 HX5 간접 주소가
이전 값으로 복원된다. 강제 종료나 전원 차단으로 복원이 중단되었다면
다음 명령 전 상태를 다시 검사한다. 현재 [리더 텔레옵](hx5-d20-omy-teleop.md)은
END 210을 경유하는 Direct Mode(0)를 사용한다. 이 Preset Mode(1) bringup과
손 모드·END 포트가 겹치므로 동시에 실행할 수 없다.

## 공식 자료

- [HX5 제어표](https://docs.robotis.com/docs/systems/hx5_d20/specifications/control_table/):
  Preset Mode 1, Preset Index 2016, Motion Index 2017, Time 2018,
  Indirect Address/Data의 의미.
- [ROBOTIS 공식 손 소스](https://github.com/ROBOTIS-GIT/robotis_hand):
  왼손 URDF와 직접 20관절 제어 구현. 이 런치의 실물 경로는 END 경유 Preset
  노드로 대체되며, 공식 손 단독 런치를 그대로 실행하는 것은 아니다.
- [OMY 설정](https://docs.robotis.com/docs/systems/omy/quick_start_guide/setup_guide/):
  컨테이너와 unpack 절차.
