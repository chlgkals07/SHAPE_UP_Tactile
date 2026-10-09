# 10/09 실물 검증 계획: OMY 텔레옵 → LEAP Hand

**성공 기준:** 아래 5단계가 모두 통과하면 성공.

| # | 단계 | 통과 조건 |
|---|---|---|
| 1 | 공식 방식 텔레옵 (그리퍼 장착) | leader를 움직이면 follower가 따라온다 |
| 2 | 그리퍼 → LEAP Hand 교체 | 마운트·배선 완료, 전원 OFF 상태로 정리 |
| 3 | LEAP 장착 상태 텔레옵 | 1번과 같은 동작. leader 그리퍼 값 측정 |
| 4 | LEAP 단독 구동 (User PC) | 키보드 space로 쥐기/펴기 |
| 5 | 통합 | (a) leader+키보드 동시 (b) leader 그리퍼로 손 조작 |

표기: **[공식]** ROBOTIS 문서·저장소에서 확인 / **[우리]** 우리 코드·판단 / **[미검증]** 실물에서 처음 확인 / **[실측 10/09]** 현장에서 해 보고 고친 내용.
결과 요약: [`2026-10-09-results.md`](2026-10-09-results.md)
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
# dynamixel_sdk는 ros-jazzy 패키지라 ROS를 source 해야 import 된다 [실측 10/09]
source /opt/ros/jazzy/setup.bash
python3 -c "import numpy, yaml, dynamixel_sdk, pytest" || \
  sudo apt install python3-numpy python3-yaml python3-pytest ros-jazzy-dynamixel-sdk

# zenoh RMW 설치 (apt에서 설치 가능 확인함: 0.2.11)
sudo apt install ros-jazzy-rmw-zenoh-cpp

# LEAP(FTDI) 시리얼 권한·지연. container.sh가 U2D2에 쓰는 규칙과 같은 것 [공식 규칙, LEAP 적용은 우리]
echo 'KERNEL=="ttyUSB*", DRIVERS=="ftdi_sio", MODE="0666", ATTR{device/latency_timer}="1"' | sudo tee /etc/udev/rules.d/99-u2d2.rules
sudo udevadm control --reload-rules && sudo udevadm trigger

# 코드 상태 확인 (하드웨어 없이 통과해야 함)
cd ~/Projects/SHAPE_UP_Tactile/user_pc && PYTHONPATH="src:$PYTHONPATH" python3 -m pytest -q    # 96 passed
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

   > [실측 10/09] 44B1050은 `10.42.0.241` / `omy-snpr44b1050.local` (User PC USB 랜을 NetworkManager 공유 모드 `10.42.0.1`로 둔 경우).
   > ping·TCP 22는 되는데 `Connection timed out during banner exchange`로 SSH가 안 되는 증상이 있었다. 로봇 재부팅·USB-A 직결로는 그대로였고, **더 좋은 USB 허브로 바꾸자 해결**됐다. 같은 증상이면 랜 어댑터 허브부터 바꾼다.

**1-2. 컨테이너** [공식]
```bash
cd /data/docker/open_manipulator
docker ps                          # open_manipulator 가 보이면 이미 실행 중 (compose: restart: always)
./docker/container.sh start        # 없을 때만. image pull을 하므로 인터넷 필요
./docker/container.sh enter        # 컨테이너 진입 (터미널마다 반복)
```
컨테이너 `.bashrc`에 `ROS_DOMAIN_ID=30`, `RMW_IMPLEMENTATION=rmw_zenoh_cpp`, alias `zenohd`·`omy_ai`가 이미 있다 [공식 Dockerfile].

> [실측 10/09] `.bashrc`가 로드되지 않은 셸에서는 `zenohd: command not found`가 나고, **환경변수도 같이 빠진다.** 이 상태로 `omy_ai`를 띄우면 팔은 정상으로 움직이지만 zenoh에 안 붙어서 User PC에서 `/leader/joint_trajectory` 발행자가 0개가 된다(LEAP 무반응). 그럴 때는 터미널마다:
> ```bash
> source /opt/ros/jazzy/setup.bash
> export ROS_DOMAIN_ID=30 RMW_IMPLEMENTATION=rmw_zenoh_cpp
> ros2 run rmw_zenoh_cpp rmw_zenohd                                  # A: zenohd 대신
> ros2 launch open_manipulator_bringup omy_ai.launch.py              # B: omy_ai 대신
> ```

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
- [실측 10/09] **공식 `omy_ai`가 그리퍼 없이도 정상 동작**했다(follower가 leader를 따라감). 3-2는 필요 없었다.
  leader 쪽에서 `FastBulkRead Rx Fail [Dxl Size : 7]` / `BULK_READ_FAIL`(-3001, -3002)이 몇 초마다 찍혔지만 10ms/500ms 허용 안이라 동작은 계속됐다. 이건 follower가 아니라 **leader** 버스(모터 7개) 로그다.

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

> [실측 10/09] ROS를 source 하지 않은 셸의 `python3`에는 `dynamixel_sdk`가 없어 1)부터 `ModuleNotFoundError`가 난다. 아래처럼 **ROS를 source 한 `python3`** 또는 **`.venv/bin/python`** 을 `$PY`로 쓴다.
> 명령은 **한 줄로** 붙여 넣는다. 줄이 잘려 `--output`의 값이 빠지면 `expected one argument`로 아무것도 안 하고 끝난다.

```bash
cd ~/Projects/SHAPE_UP_Tactile/user_pc
source /opt/ros/jazzy/setup.bash && export PYTHONPATH="src:$PYTHONPATH" && PY=python3   # 또는: export PYTHONPATH=src; PY=.venv/bin/python
ls /dev/ttyUSB*                                                       # FTDI FT232H → /dev/ttyUSB0

# 1) 토크 OFF 진단: ID 0~15 응답, hardware error 전부 0
$PY -m leap_teleop.tools.check_hardware --port /dev/ttyUSB0

# 2) 편 손 영점 기록: 손을 편 자세로 두고 LEAP 5V를 껐다 켠 다음 → 편 자세로 고정 → RECORD 입력
$PY -m leap_teleop.tools.calibrate_motors --port /dev/ttyUSB0 --output config/hardware_motors.yaml   # 다시 잡을 때 --force

# 3) 현재 자세 유지 토크 시험 (움직임 없음)
$PY -m leap_teleop.tools.check_hardware --port /dev/ttyUSB0 --torque-test --motor-calibration-file config/hardware_motors.yaml

# 4) 관절별 +5° 시험. 쥐기에 쓰는 12개 flex 관절 전부, 관절마다 MOVE 입력. 펴지는 방향이면 yaml의 sign을 -1로
for j in index_mcp_flex index_pip_flex index_dip_flex middle_mcp_flex middle_pip_flex middle_dip_flex \
         ring_mcp_flex ring_pip_flex ring_dip_flex thumb_cmc_flex thumb_mcp_flex thumb_ip_flex; do
  echo "=== $j ==="; $PY -m leap_teleop.tools.joint_test --port /dev/ttyUSB0 --joint $j --delta 5 --motor-calibration-file config/hardware_motors.yaml || break
done

# 5) 파이프라인만 (하드웨어 안 건드림)
$PY -m leap_teleop.cli --dry-run

# 6) 키보드로 실물: space = 쥐기/펴기 토글, q = 종료
$PY -m leap_teleop.cli
```
동작이 작거나 크면 `config/postures.yaml`의 `fist` 값을 조금씩 조정. 영점 파일이 없으면 CLI가 실행을 거부한다.

> [실측 10/09] **영점은 한 바퀴(0~360°) 안이어야 한다.** XC330은 모드 5에서 회전수를 누적하므로, 엄지 CMC(ID 13)가 629°(= 269° + 360°)로 기록된 적이 있다. 이대로면 다음 전원 투입 때 영점이 360° 어긋난다. 2)를 하기 전에 **손을 편 채 5V를 껐다 켜고**, 기록 후 `config/hardware_motors.yaml`의 `open_motor_radians`가 0~6.283 범위인지 본다. LEAP 5V는 **항상 손을 편 상태에서** 켠다.
> [실측 10/09] `fist`를 완전히 쥐는 값(손가락 MCP/PIP/DIP 90/100/80°, 엄지 CMC/MCP/IP 60/75/70°, 출처 `leap-hand@ddfabaa` `neutral_calibration.py`)으로 바꿨다.

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
python3 -m leap_teleop.cli --source leader --safe-pose fist --dry-run   # leader 그리퍼를 쥐면 'cmd max'가 커진다
python3 -m leap_teleop.cli --source leader --safe-pose fist             # 실물
```

**실행 순서** [실측 10/09, 이 순서로 성공]
1. Robot PC A: `zenohd` (팔 안 움직임). User PC에서 `ros2 topic list`가 에러 없이 나오면 연결됨.
2. User PC: 위 `--source leader --safe-pose fist` 실행 → 손이 **주먹을 쥐고** `[teleop] waiting`.
   zenohd가 없으면 ROS 초기화에서 멈춰 손을 쥐기 전에 대기할 수 있으므로 1을 먼저 한다.
3. Robot PC B: `omy_ai`. 팔이 초기자세로 움직이는 동안 손은 주먹. leader 토픽이 들어오면 `[teleop] live`.
4. 종료는 반대로: B `Ctrl+C`(팔 받치기, 손은 3초 뒤 주먹) → User PC `Ctrl+C`(토크 OFF, 손 힘 빠짐) → A `Ctrl+C`.

`--safe-pose fist`: 첫 입력 전(`waiting`)과 3초 이상 끊긴 뒤(`release`)에 주먹을 유지한다. 없으면 편 손이다.

> ⚠ [실측 10/09] `live`가 되면 손은 leader 그리퍼를 그대로 따라간다. omy_ai를 켤 때와 팔을 크게 옮길 때는 **leader 그리퍼를 쥔 채로** 한다.
> ⚠ [실측 10/09] 텔레옵 중 **leader가 갑자기 크게 튄** 적이 있다. 텔레옵하는 동안은 **leader를 반드시 손으로 잡고** 있는다(놓은 채로 두지 않는다).
확인 항목:
- leader 그리퍼를 쥐면 손이 닫히고 펴면 열린다 (방향이 반대면 yaml의 open/closed를 바꾸면 된다).
- `Ctrl+C`로 종료하면 손이 힘을 뺀다.
- (선택) `--dry-run` 중 이더넷을 잠깐 뽑으면 0.5초 뒤 `hold`, 3초 뒤 `release`가 로그에 찍힌다.

> [검증됨, 시뮬레이션] docker 컨테이너 2개(`zenohd`+가짜 leader / client 모드 User PC)로 재현: `ros2 topic list`·`echo`에서 토픽이 보이고, `leap_teleop --source leader --dry-run`이 `waiting → live`(손 목표 30° = 0.5)로 동작하며 Ctrl+C로 정상 종료. 실제 Robot PC와의 연결은 [미검증].
> 토픽이 안 보이면: IP, 포트 7447, `RMW_IMPLEMENTATION`, `ZENOH_CONFIG_OVERRIDE`, Robot PC `zenohd` 실행 여부 순으로 확인 [공식 체크리스트].

✅ 통과: (a)와 (b) 모두 동작 → **전체 성공.**

---

## 부록 A. OMY 멀티턴 오류(0xC) 복구 [실측 10/09]

bringup 로그에 `Error code 0xc (Multi-turn Error)`가 뜰 때. ROBOTIS 트러블슈팅 문서의 **방법 2**(Debug USB + Dynamixel Wizard 2.0, SSH 불필요)로 해결했다.
https://docs.robotis.com/docs/systems/omy/support/troubleshooting_guide

**준비 (User PC)**
1. Dynamixel Wizard 2.0 설치: `chmod +x DynamixelWizard2Setup-linux-x64.run` 후
   `./DynamixelWizard2Setup-linux-x64.run --root ~/ROBOTIS/DynamixelWizard2 --accept-licenses --default-answer --confirm-command install`
   설치 후 실행 권한이 빠져 있으면 `chmod +x ~/ROBOTIS/DynamixelWizard2/DynamixelWizard2.sh ~/ROBOTIS/DynamixelWizard2/DynamixelWizard2`.
2. 시리얼 권한: `sudo usermod -aG dialout $USER` 후 재로그인 (급하면 `sudo chmod 666 /dev/ttyACM0`). `!` 프롬프트에서는 sudo 비밀번호를 못 받으니 별도 터미널에서 한다.
3. OMY 본체 패널의 **Debug USB-C** → User PC. `ROBOTIS STM32 Virtual ComPort` = `/dev/ttyACM0`.

**절차 (Wizard)**
1. Protocol 2.0, `/dev/ttyACM0`로 Scan → OMY-HAT(ID 200). `DXL Power Enable (512)` ON.
2. Search 설정에서 6 Mbps, ID 1~10 → 액추에이터 1~6 확인. 각 ID의 Error Code로 알람 난 축을 찾는다.
3. **메인 창에서 Disconnect** → Tools → **Packet** 창에서 `/dev/ttyACM0`, 6 Mbps, Protocol 2.0으로 Open → 알람 ID에 **Clear** 전송.
   메인 창이 포트를 잡고 있으면 Packet 창이 포트를 못 연다. 알람이 남아 있으면 **토크가 켜지지 않는다**(Clear가 먼저).
4. 메인 창 다시 Connect → 각 관절 `Operating Mode (33)` = Current, 팔을 받치고 토크 ON → **홈 슬릿에 정확히** 맞춤 → 토크 OFF.
5. 6축 모두 홈에 맞춘 상태에서 다시 Disconnect → Packet에서 **ID 1~6에 Clear**.
6. Connect → 각 관절 Present Position이 홈 ±1° 안인지 확인. 벗어나면 4~5 반복.

**주의**
- Clear는 **보내는 순간의 자세를 기준으로** 회전수를 정리한다. 홈이 아닌 자세에서 보내면 원점이 틀어진다(10/09에 한 번 틀어져 4~6으로 다시 맞췄다).
- **Factory Reset 금지** (ID·통신 속도·Homing Offset 등 OMY 설정이 초기화된다). Reboot은 설정을 지우지 않지만 멀티턴 오류는 대개 안 풀린다.
- Homing Offset 등 Control Table 값을 직접 고쳐서 맞추지 않는다.

## 결과 기록
결과는 [`2026-10-09-results.md`](2026-10-09-results.md)에 정리했다.

## 출처
- Setup Guide: https://docs.robotis.com/docs/systems/omy/quick_start_guide/setup_guide
- Teleoperation: https://docs.robotis.com/docs/systems/omy/quick_start_guide/operation_guide/teleoperation
- Zenoh Communication: https://docs.robotis.com/docs/systems/omy/quick_start_guide/zenoh_communication
- Robot Control: https://docs.robotis.com/docs/systems/omy/quick_start_guide/operation_guide/robot_control
- 컨테이너 설정: `third_party/open_manipulator/docker/` (`docker-compose.yml`, `Dockerfile`, `container.sh`, `s6-services/`) @ 5.1.3
- rmw_zenoh: https://github.com/ros2/rmw_zenoh (branch `jazzy`, README)
