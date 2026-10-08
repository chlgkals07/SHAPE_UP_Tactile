# 10/09 실물 검증 계획: OMY 텔레옵 → LEAP Hand

**성공 기준:** 아래 5단계가 모두 통과하면 성공.

| # | 단계 | 통과 조건 |
|---|---|---|
| 1 | 공식 방식 텔레옵 (그리퍼 장착) | leader를 움직이면 follower가 따라온다 |
| 2 | 그리퍼 → LEAP Hand 교체 | 마운트·배선 완료, 전원 OFF 상태로 정리 |
| 3 | LEAP 장착 상태 텔레옵 | 1번과 같은 동작. leader 그리퍼 값 측정 |
| 4 | LEAP 단독 구동 (User PC) | 키보드 space로 쥐기/펴기 |
| 5 | 통합 | (a) leader+키보드 동시 (b) leader 그리퍼로 손 조작 |

표기: **[공식]** ROBOTIS 문서·저장소에서 확인 / **[우리]** 우리 코드·판단 / **[미검증]** 실물에서 처음 확인.
용어: **Robot PC** = OMY 내부 PC(컨테이너 `open_manipulator`), **User PC** = 이 노트북.

## 안전 (매 단계 공통)
- 로봇이 **launch 즉시 움직인다** [공식]. 작업 공간을 비운다.
- LEAP 5V 전원을 즉시 끊을 수단을 손 닿는 곳에 둔다 [우리].
- 비상 중지는 launch 터미널 `Ctrl+C`. 로봇 쪽 별도 비상정지 절차는 문서에 없다 → 시작 전 로보티즈 안내 확인.

---

## 0. 사전 준비 (User PC, 시작 전)

```bash
# 코드 받기 (브랜치 feat/leap-teleop). 서브모듈은 참고용이라 받지 않아도 된다
git clone -b feat/leap-teleop https://github.com/chlgkals07/SHAPE_UP_Tactile.git
git clone https://github.com/chlgkals07/OMY_Tactile_Robot_PC.git      # 3-2에서 복사할 때만 필요 (private)

# 의존성 (Ubuntu 24.04 + ROS 2 Jazzy 가정). 이미 있으면 건너뛴다
python3 -c "import numpy, yaml, dynamixel_sdk, pytest" || \
  sudo apt install python3-numpy python3-yaml python3-pytest ros-jazzy-dynamixel-sdk

# zenoh RMW 설치 (apt에서 설치 가능 확인함: 0.2.11)
sudo apt install ros-jazzy-rmw-zenoh-cpp

# LEAP(FTDI) 시리얼 권한·지연. container.sh가 U2D2에 쓰는 규칙과 같은 것 [공식 규칙, LEAP 적용은 우리]
echo 'KERNEL=="ttyUSB*", DRIVERS=="ftdi_sio", MODE="0666", ATTR{device/latency_timer}="1"' | sudo tee /etc/udev/rules.d/99-u2d2.rules
sudo udevadm control --reload-rules && sudo udevadm trigger

# 코드 상태 확인 (하드웨어 없이 통과해야 함)
cd ~/Projects/SHAPE_UP_Tactile/user_pc && PYTHONPATH=src python3 -m pytest -q    # 92 passed
```
준비물: 로봇 시리얼 번호(SN, 본체 라벨), 이더넷 케이블, LEAP 5V 전원과 Micro-USB, 마운트 부품.

---

## 1. 공식 방식 텔레옵 (그리퍼 장착, Robot PC)

**1-1. 연결** [공식 Setup Guide]
1. 전원 버튼을 눌렀다 떼서 LED가 **흰색**이 될 때까지.
2. 이더넷으로 Robot PC ↔ User PC 연결 (같은 네트워크).
3. 접속 (mDNS 호스트명은 SN 기반):
   ```bash
   ssh root@omy-<SN>.local          # 비밀번호 없음 [Setup Guide]
   ```
   > ⚠ 문서 불일치: Zenoh 페이지는 `ssh robotis@omy-<sn>.local`로 적혀 있다. `root`가 안 되면 `robotis`로 시도.

**1-2. 컨테이너** [공식]
```bash
cd /data/docker/open_manipulator
docker ps                          # open_manipulator 가 보이면 이미 실행 중 (compose: restart: always)
./docker/container.sh start        # 없을 때만. image pull을 하므로 인터넷 필요
./docker/container.sh enter        # 컨테이너 진입 (터미널마다 반복)
```
컨테이너 `.bashrc`에 `ROS_DOMAIN_ID=30`, `RMW_IMPLEMENTATION=rmw_zenoh_cpp`, alias `zenohd`·`omy_ai`가 이미 있다 [공식 Dockerfile].

**1-3. 실행** (터미널 3개: ssh → `container.sh enter` 각각)
| 터미널 | 명령 | 설명 |
|---|---|---|
| A | `zenohd` | zenoh 라우터. 네트워크에 최소 1개 필요 [공식] |
| B | `ros2 launch open_manipulator_bringup omy_ai.launch.py` (alias `omy_ai`) | follower 초기자세 → leader 중력보상 → 동기화 [공식] |
| C | 확인용 | 아래 |

> **B 실행 전 충돌 확인** [우리]: 컨테이너에는 follower/leader를 자동 실행하는 s6 서비스가 있다. 이미 떠 있으면 중복 실행된다.
> `ros2 node list` 와 `pgrep -a zenohd` 가 **비어 있는지** 먼저 본다. 이미 떠 있으면 그것을 그대로 쓰고 B는 실행하지 않는다.

**1-4. 확인 (터미널 C)**
```bash
ros2 control list_controllers                           # arm_controller, joint_state_broadcaster 가 active
ros2 topic echo /leader/joint_trajectory --field points # 값 7개 (마지막이 rh_r1_joint, 그리퍼)
```
leader 팔을 천천히 움직여 follower가 따라오는지, leader 그리퍼를 쥐면 7번째 값이 변하는지 본다.

**1-5. 종료:** B에서 `Ctrl+C`. 팔이 처질 수 있으니 손으로 받칠 준비. 접으려면 `ros2 launch open_manipulator_bringup omy_3m_pack.launch.py` [공식, 이미 확인함]. 문서에 로봇 종료 절차는 없다.

✅ 통과: follower가 leader를 따라가고 이상 소음·진동 없음.

---

## 2. 그리퍼 → LEAP Hand 교체

1. 1-5대로 팔을 접고(pack) launch를 종료, **OMY 전원 OFF** [우리].
2. 그리퍼 분리. end unit 커넥터는 단자가 노출되지 않게 절연 [우리].
3. LEAP 마운트. 케이블이 모든 관절 범위에서 당겨지지 않는지 확인. 하중은 OMY 허용 하중 사양과 비교 [미검증, 사양 확인 필요].
4. LEAP의 **5V 전원은 아직 연결하지 않는다** (3단계에서 손이 힘 없이 매달려 있게). Micro-USB는 User PC로 배선만.
5. OMY 전원 ON (LED 흰색).

✅ 통과: 기구·배선 정리 완료.

---

## 3. LEAP 장착 상태 텔레옵 (Robot PC)

**3-1. 공식 launch 먼저** (1-2, 1-3과 동일: A=`zenohd`, B=`omy_ai`)
- 그리퍼가 없으므로 end unit(Dynamixel ID 7)을 못 찾아 **실패할 수 있다** [추정, 미검증]. 실패하면 로그를 그대로 저장.
- 정상 동작하면 4단계로.

**3-2. 실패 시: 우리 패키지** [우리, mock으로 검증됨 / 실제 팔은 미검증]
User PC에서 Robot PC로 복사 (ssh만 사용, git 계정 불필요):
```bash
cd ~/Projects/OMY_Tactile_Robot_PC
tar c omy_leap_bringup | ssh root@omy-<SN>.local \
  'mkdir -p /data/docker/open_manipulator/docker/workspace/omy_ws/src && tar x -C /data/docker/open_manipulator/docker/workspace/omy_ws/src'
```
컨테이너 안 (호스트 `.../docker/workspace` = 컨테이너 `/workspace` [공식 compose]):
```bash
cd /workspace/omy_ws
colcon build --packages-select omy_leap_bringup
source install/setup.bash
ros2 launch omy_leap_bringup omy_ai_no_gripper.launch.py
```
1-4와 같은 확인을 한다. 정상이면 팔 하드웨어에서 **처음으로** 이 패키지가 검증된다.

**3-3. leader 그리퍼 값 측정** (터미널 C, 값 적어두기 → 5단계에서 `config/leader_gripper.yaml`에 입력)
```bash
ros2 topic echo /leader/joint_trajectory --field points   # leader 그리퍼를 편 상태, 쥔 상태에서 각각 7번째 값
```
✅ 통과: LEAP 달린 팔이 leader를 따라가고, 펴짐/쥠 값 2개를 기록.

---

## 4. LEAP 단독 구동 (User PC)

LEAP 5V 연결, Micro-USB를 User PC에 연결. 손 주변을 비우고 **5V 차단 수단 확보**. 아래는 순서대로, 건너뛰지 않는다.

```bash
cd ~/Projects/SHAPE_UP_Tactile/user_pc && export PYTHONPATH=src
ls /dev/ttyUSB*

# 1) 토크 OFF 진단: ID 0~15 응답, hardware error 전부 0
python3 -m leap_teleop.tools.check_hardware --port /dev/ttyUSB0

# 2) 편 손 영점 기록: 손을 편 자세로 고정 → 프롬프트에 RECORD 입력
python3 -m leap_teleop.tools.calibrate_motors --port /dev/ttyUSB0 --output config/hardware_motors.yaml

# 3) 현재 자세 유지 토크 시험 (움직임 없음)
python3 -m leap_teleop.tools.check_hardware --port /dev/ttyUSB0 --torque-test --motor-calibration-file config/hardware_motors.yaml

# 4) 관절별 ±5° 시험. 쥐기에 쓰는 12개 flex 관절을 각각, 방향이 반대면 yaml의 sign을 -1로
python3 -m leap_teleop.tools.joint_test --port /dev/ttyUSB0 --joint index_mcp_flex --delta 5 --motor-calibration-file config/hardware_motors.yaml

# 5) 파이프라인만 (하드웨어 안 건드림)
python3 -m leap_teleop.cli --dry-run

# 6) 키보드로 실물: space = 쥐기/펴기 토글, q = 종료
python3 -m leap_teleop.cli
```
동작이 작거나 크면 `config/postures.yaml`의 `fist` 값을 조금씩 조정. 영점 파일이 없으면 CLI가 실행을 거부한다.

✅ 통과: space로 손이 열리고 닫히며, `q`/`Ctrl+C`로 종료하면 손이 힘을 뺀다.

---

## 5. 통합 테스트

### 5-a. leader + 키보드 (네트워크 불필요, 두 프로세스가 독립)
- Robot PC: 3단계 launch 유지 (텔레옵 중).
- User PC: `python3 -m leap_teleop.cli` (키보드).
- leader로 팔을 움직이는 동안 space로 손을 쥐고 펴본다. 팔과 손이 서로 영향 없이 동작하는지, 케이블 간섭이 없는지 본다.

### 5-b. leader 그리퍼로 손 조작 (User PC가 Robot PC 토픽을 받아야 함)
Robot PC는 zenoh이므로 User PC도 같은 RMW로 맞춘다 [공식 Zenoh Communication]:
```bash
ping -c1 omy-<SN>.local                  # Robot PC IP 확인
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_CONFIG_OVERRIDE='mode="client";connect/endpoints=["tcp/<ROBOT_IP>:7447"]'
ros2 daemon stop                         # 공식 트러블슈팅: 오래된 daemon 정리
ros2 topic list                          # /leader/joint_trajectory, /joint_states 가 보여야 함
ros2 topic echo /leader/joint_trajectory --field points
```
> 공식 예시는 `transport/shared_memory/enabled=true;`도 포함한다. 다른 PC 사이에서는 필요 없어 뺐다. docker 시험에서는 shm을 켜면 `Failed to create POSIX SHM provider`로 초기화가 실패했다 [우리].

측정값을 입력 (3-3에서 적은 값):
```bash
cd ~/Projects/SHAPE_UP_Tactile/user_pc
# config/leader_gripper.yaml 의 open_value / closed_value 수정
export PYTHONPATH="src:$PYTHONPATH"      # ROS를 source 한 셸이므로 덮어쓰지 않는다
python3 -m leap_teleop.cli --source leader --dry-run   # leader 그리퍼를 쥐면 'cmd max'가 0 → 60 근처로
python3 -m leap_teleop.cli --source leader             # 실물
```
확인 항목:
- leader 그리퍼를 쥐면 손이 닫히고 펴면 열린다 (방향이 반대면 yaml의 open/closed를 바꾸면 된다).
- `Ctrl+C`로 종료하면 손이 힘을 뺀다.
- (선택) `--dry-run` 중 이더넷을 잠깐 뽑으면 0.5초 뒤 `hold`, 3초 뒤 `release`가 로그에 찍힌다.

> [검증됨, 시뮬레이션] docker 컨테이너 2개(`zenohd`+가짜 leader / client 모드 User PC)로 재현: `ros2 topic list`·`echo`에서 토픽이 보이고, `leap_teleop --source leader --dry-run`이 `waiting → live`(손 목표 30° = 0.5)로 동작하며 Ctrl+C로 정상 종료. 실제 Robot PC와의 연결은 [미검증].
> 토픽이 안 보이면: IP, 포트 7447, `RMW_IMPLEMENTATION`, `ZENOH_CONFIG_OVERRIDE`, Robot PC `zenohd` 실행 여부 순으로 확인 [공식 체크리스트].

✅ 통과: (a)와 (b) 모두 동작 → **전체 성공.**

---

## 결과 기록
- 1단계: 공식 launch 동작 여부 / SSH 계정(`root` 또는 `robotis`)
- 3단계: 공식 launch가 그리퍼 제거 상태에서 실패했는가 (로그), 우리 패키지가 필요했는가
- 3-3: `rh_r1_joint` 펴짐 ___ / 쥠 ___
- 4단계: 방향이 반대였던 관절 (`sign: -1`), 조정한 fist 값
- 5단계: zenoh 연결 방식, 문제점

## 출처
- Setup Guide: https://docs.robotis.com/docs/systems/omy/quick_start_guide/setup_guide
- Teleoperation: https://docs.robotis.com/docs/systems/omy/quick_start_guide/operation_guide/teleoperation
- Zenoh Communication: https://docs.robotis.com/docs/systems/omy/quick_start_guide/zenoh_communication
- Robot Control: https://docs.robotis.com/docs/systems/omy/quick_start_guide/operation_guide/robot_control
- 컨테이너 설정: `third_party/open_manipulator/docker/` (`docker-compose.yml`, `Dockerfile`, `container.sh`, `s6-services/`) @ 5.1.3
- rmw_zenoh: https://github.com/ros2/rmw_zenoh (branch `jazzy`, README)
