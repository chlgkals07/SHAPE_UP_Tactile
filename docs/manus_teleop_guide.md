# Manus 텔레옵 시험 가이드

목표: **팔은 팔대로, 손은 Manus로, 그리고 팔·손·촉각·카메라를 같은 시간축으로 기록.**

> **현재 상태 (11/13)**
> - LEAP은 플랜지에서 **오른쪽 90° 돌려 단 것이 최종 장착**이다. 팔은 `omy_ai` 대신 `omy_ai_wrist_flip`으로 띄운다 (6절).
> - Manus → LEAP 텔레옵은 약 80% 완성. 남은 것: 잡기 위한 리타겟팅/IK 보정, 글러브 SDK 캘리브레이션을 다시 한 뒤 엄지 IK 확인.
> - 손목 카메라 D405 **[실측 11/12]**, Paxini 촉각 센서 연동 **[실측 11/12]** 확인 (6-1절).
> - Cyclo 기록(14·15절)은 **보류**. Humble↔Jazzy `rmw_zenoh` 불통으로 막혔고, 촉각도 같이 모아야 해서 자체 녹화 프로그램(LeRobot 형식)을 만든다.

같은 내용을 단계별로 눌러 넘기는 페이지로 보려면 [`manus_teleop_guide.html`](manus_teleop_guide.html)을 브라우저로 연다 (체크 상태가 브라우저에 저장된다).

| 표기 | 뜻 |
|---|---|
| **[실측 10/09]** | 10/09 현장에서 해 본 결과 |
| **[미검증]** | 아직 해 보지 않음. 실물에서 처음 확인 |
| `leap_*` | `user_pc/scripts/leap_aliases.sh`의 단축 함수 |

## 목차
1. [전체 구조](#1-전체-구조)
2. [단계별로 켜져 있어야 하는 것](#2-단계별로-켜져-있어야-하는-것)
3. [처음 한 번 설정](#3-처음-한-번-설정)
4. [안전 수칙](#4-안전-수칙)
5. [로봇 전원, 네트워크, SSH, 컨테이너](#5-로봇-전원-네트워크-ssh-컨테이너)
6. [zenohd와 omy_ai](#6-zenohd와-omy_ai) (90° 장착: `omy_ai_wrist_flip`)
   - [6-1. 손목 카메라와 Paxini 촉각](#6-1-손목-카메라와-paxini-촉각)
7. [단계 2: leader 트리거로 LEAP 열고 닫기](#7-단계-2-leader-트리거로-leap-열고-닫기)
8. [2단계 정리, 3단계 준비](#8-2단계-정리-3단계-준비)
9. [단계 3-1: Manus 노드와 토픽 확인](#9-단계-3-1-manus-노드와-토픽-확인)
10. [단계 3-2: 글러브 캘리브레이션](#10-단계-3-2-글러브-캘리브레이션)
11. [단계 3-3: dry-run](#11-단계-3-3-dry-run)
12. [단계 3-4: LEAP 실물](#12-단계-3-4-leap-실물)
13. [단계 4: Manus + 팔](#13-단계-4-manus--팔)
14. [단계 5-1: Cyclo 준비](#14-단계-5-1-cyclo-준비)
15. [단계 5-2: 기록하기](#15-단계-5-2-기록하기)
16. [종료 순서](#16-종료-순서)
17. [pack / unpack](#17-pack--unpack)
18. [문제 해결](#18-문제-해결)
19. [아직 모르는 것](#19-아직-모르는-것)

---

## 1. 전체 구조

팔은 Robot PC 안에서, 손은 User PC에서 따로 돈다. 두 PC는 zenoh로 토픽을 주고받는다.

```
[ROBOT PC · OMY 본체, 컨테이너]                    [USER PC]
 zenohd (:7447) ◄──── zenoh client ───────────── Manus 노드 ─► /manus_glove_0
 omy_ai_wrist_flip     (ROS_DOMAIN_ID=30)         leap_teleop ─► LEAP Hand (USB, 5V, 90° 장착)
  ├ ① follower(OMY-F3M)                           D405 손목 카메라 (OMY Camera 포트 → USB)
  ├ ② home → ready 이동                           Paxini 촉각 (통신 보드 USB)
  └ ③ leader(OMY-L100) 동기화                     /leap/* 기록용 발행
 /leader/joint_trajectory, /joint_states
```

- **팔의 텔레옵 루프**는 Robot PC 안에서 닫힌다. leader를 움직이면 follower가 따라간다. User PC는 관여하지 않는다.
- **손의 루프**는 `leap_teleop` 한 프로세스에서 닫힌다. Manus(또는 leader 트리거) 입력 → 리타겟팅 → LEAP.
- 팔과 손은 **서로 독립 프로세스**다. 그래서 팔 없이도 Manus → LEAP만 먼저 시험할 수 있다.
- Cyclo용 `/leap/*` 발행은 **기록 전용**이다. 실패해도 손은 멈추지 않는다.

| 장치 | 역할 |
|---|---|
| OMY-F3M (follower) | 실제 움직이는 팔. 6축 + 끝단(원래 그리퍼, 우리는 LEAP으로 교체) |
| OMY-L100 (leader) | 사람이 잡는 팔. 7모터(6축 + 트리거 `rh_r1_joint`) |
| LEAP Hand v1 | 16모터 손. 5V 전원 + FTDI USB(`/dev/ttyUSB0`). ROS 밖에서 직접 구동. 플랜지에서 오른쪽 90° 돌려 장착 |
| Manus 글러브 | 사람 손 입력. 동글 USB, SDK ROS 2 노드 |
| RealSense D405 | 손목 카메라. `link6`에 붙어 있어 90° 장착에서는 손 옆에 온다 |
| Paxini GEN3 | 촉각 센서. SDK는 `third_party/paxini` |

## 2. 단계별로 켜져 있어야 하는 것

| 단계 | 하는 일 | Robot PC<br>(zenohd, omy_ai) | Manus 노드 | LEAP 5V | zenoh 환경 |
|---|---|---|---|---|---|
| **2** | leader 트리거 → LEAP (검증 끝) | 필요 | 불필요 | 필요 | 켠다 |
| **3** | Manus → LEAP, **팔 없음** | 불필요 | 필요 | 필요 (dry-run은 불필요) | **끈다** (`LEAP_NO_ZENOH=1`) |
| **4** | Manus + 팔 | 필요 | 필요 | 필요 | 끈다 |
| **5** | Cyclo 기록 (**보류**) | 필요 | 필요 | 필요 | 켠다 |

> **같은 RMW 규칙.** Manus 노드와 `leap_teleop`은 같은 RMW를 써야 서로 토픽이 보인다. 3·4단계는 둘 다 기본 RMW(zenoh 끔), 5단계는 둘 다 zenoh(켬). 한쪽만 zenoh이면 `[teleop] waiting`에서 멈춘다.

- 3·4단계의 `leap_teleop`은 `/manus_glove_*`만 읽고 팔 토픽은 읽지 않는다.
- 5단계에서 zenoh를 켜는 이유: `/leap/*`를 Cyclo(컨테이너)가 받아야 한다.
- Manus 노드와 LEAP이 **다른 PC**면 두 PC가 같은 토픽을 볼 수 있어야 한다. 같은 PC가 가장 단순하다.

## 3. 처음 한 번 설정

**USER PC**

```bash
# ~/.bashrc 끝에 넣는다 (이 User PC에는 11/03에 넣었다). 새 터미널부터는 leap_env만 치면 된다.
# --- SHAPE_UP_Tactile LEAP/Manus teleop ---
source ~/SHAPE_UP_Tactile/user_pc/scripts/leap_aliases.sh
export LEAP_ROS_DISTRO=humble       # 이 User PC는 Ubuntu 22.04 + ROS 2 Humble
export OMY_ROBOT_IP=10.42.0.241     # ROBOT PC IP (44B1050)
export LEAP_MANUS_WS="$HOME/SHAPE_UP_Tactile/third_party/manus/ROS2 package"
export LEAP_NO_ZENOH=1              # 기본은 손만(3·4단계). 2·5단계 셸에서는 unset LEAP_NO_ZENOH
export PYTEST_ADDOPTS="-p no:anyio" # ~/.local anyio 플러그인과 apt pytest(6.x) 충돌 회피

# Humble용 패키지 (python3-serial이 없으면 dynamixel_sdk import 실패. pytest는 하드웨어 없이 통과해 버린다)
sudo apt install ros-humble-rmw-zenoh-cpp ros-humble-dynamixel-sdk python3-serial

# 영점 파일: leap_env가 user_pc/로 이동하므로 user_pc/config/에 둔다.
# 같은 LEAP 실물의 최신 파일인지 확인한 뒤 복사
cp ~/Documents/antigravity/charming-pascal/leap-hand/calibration/hardware_motors.yaml \
   ~/SHAPE_UP_Tactile/user_pc/config/hardware_motors.yaml

# 테스트: 하드웨어 없이 전부 통과해야 한다
leap_env && python3 -m pytest -q -p no:anyio   # ~/.local anyio 플러그인이 apt pytest(6.x)와 충돌

# Manus 노드 빌드 (Manus PC에서 한 번)
source /opt/ros/$LEAP_ROS_DISTRO/setup.bash
sudo apt install libncurses-dev      # 없으면 ncursesw/ncurses.h 에러
cd "$LEAP_MANUS_WS" && colcon build

# LEAP 포트 권한 (한 번)
sudo usermod -aG dialout $USER      # 이후 재로그인. 또는 임시로: sudo chmod 666 /dev/ttyUSB0
echo 1 | sudo tee /sys/bus/usb-serial/devices/ttyUSB0/latency_timer
```

- 동글용 udev 규칙 `third_party/manus/70-manus-hid.rules`를 `/etc/udev/rules.d/`에 넣고 다시 꽂는다.
- MANUS Core Dashboard(213 MB)는 git에 없다. integrated 모드에는 필요 없고, 글러브 펌웨어·캘리브레이션 등에 쓸 때만 MANUS 배포본을 받아 `third_party/manus/MANUS Core Dashboard (Linux build)/`에 둔다 (gitignore).
- 노드가 "SDK license" 에러를 내면 라이선스에 해당 기능이 없는 것이다.
- **노드는 integrated 모드(기본)로 동글을 직접 연다. 실행 전에 MANUS Core Dashboard를 반드시 끈다.** 켜져 있으면 `Error claiming interface 0: Resource busy`와 `No license found ... Integrated`가 같이 뜬다 (라이선스가 동글에 있어서 동글을 못 열면 라이선스도 못 읽음).

| 단축 명령 | 하는 일 |
|---|---|
| `leap_env` | ROS + Manus msgs + PYTHONPATH, `user_pc/`로 이동. `LEAP_NO_ZENOH`가 있으면 남은 zenoh 변수도 지운다 |
| `leap_manus` | Manus → LEAP (엄지 IK, 주먹 safe-pose). `--dry-run`, `--thumb affine`, `--kp`/`--kd` (기본 공식값 P 600 / D 200 / 350 mA), `--log-csv logs/run.csv` (틱마다 기록 → `python3 -m leap_teleop.tools.analyze_log`) |
| `leap_glovecal --force` | 글러브 캘리브레이션 (편 손 → 주먹) |
| `leap_check` | LEAP 모터 ID 0~15 응답 확인 |
| `leap_leader` / `leap_record` / `leap_topics` | 2단계 leader 트리거 / 5단계 기록용 발행 / 토픽 목록 |

- [ ] pytest 전부 통과
- Robot PC 컨테이너는 Jazzy다. Humble `rmw_zenoh_cpp`(0.1.11)로 붙으면 **토픽 목록은 보이지만 Robot PC 토픽의 메시지는 0개**다 **[실측 11/12]**. 타입 해시 차이로 추정. 팔·손 텔레옵(2~4단계)은 영향 없다. User PC에서 팔 토픽을 받아야 하는 기록에서만 문제다 (`docs/field-test/2026-11-12-results.md` 8절).
- 손목 카메라: `sudo apt install ros-humble-realsense2-camera` (6-1절).
- Paxini: `pip install -e third_party/paxini` (6-1절).

- [ ] `user_pc/config/hardware_motors.yaml` 있음 (1단계 영점 기록은 10/09에 끝)

## 4. 안전 수칙

> **위험**
> - LEAP **5V를 즉시 끊을 수단**을 손 닿는 곳에 둔다. 이상하면 **5V를 먼저 끊고** `Ctrl+C`.
> - **5V는 항상 손을 편 상태에서 켠다.** 모터가 회전수를 누적해서, 접힌 채 켜면 다음 전원 투입 때 영점이 360° 어긋난다.
> - 시험 중 손가락 주변에 손·케이블을 두지 않는다. LEAP Hand v1(16모터) 전용이다.

> **주의**
> - `omy_ai`는 launch **즉시 팔이 움직인다**. 작업 공간을 비우고 비상 정지 수단을 확인한다.
> - 팔이 움직이는 동안 **손은 주먹**으로 둔다. (`leap_*` 함수는 `--safe-pose fist`가 기본)
> - 텔레옵 중에는 **leader를 반드시 손으로 잡는다.** 10/09에 leader가 갑자기 크게 튄 적이 있다.

처음 구동은 항상 `--dry-run` 먼저, 그다음 `leap_manus`(엄지 IK, 기본)로 간다. `--thumb affine`은 손가락·엄지 대응이 의심될 때 진단용으로만 쓴다. **[실측 11/03]** IK가 더 좋았다.

- [ ] 5V 차단 수단이 손 닿는 곳에 있다
- [ ] LEAP이 편 손 상태다

## 5. 로봇 전원, 네트워크, SSH, 컨테이너

단계 2와 4에서 팔이 필요하다. 3단계(Manus 단독)에서는 필요 없다.

1. 로봇 전원 버튼을 눌렀다 떼서 LED가 **흰색**이 될 때까지 기다린다.
2. 이더넷으로 Robot PC ↔ User PC를 연결한다. 로봇이 IP를 못 받으면(`ping`이 `Time to live exceeded`, USB 랜이 `getting IP configuration`) User PC를 공유 모드로 한 번 바꾼다. 저장되어 유지된다. **[실측 11/12]**
   ```bash
   nmcli connection modify "Wired connection 1" ipv4.method shared   # User PC 10.42.0.1, 로봇은 약 10초 뒤 10.42.0.241
   ```
3. SSH 접속 (비밀번호 없음. 안 되면 `robotis@`).

**USER PC**
```bash
ssh root@omy-snpr44b1050.local     # = 10.42.0.241. 이름이 안 풀리면 ssh root@10.42.0.241
```

**ROBOT PC**
```bash
hostname -I                                  # User PC에서 접속 가능한 IP 확인
cd /data/docker/open_manipulator
docker ps                                    # open_manipulator가 보이면 이미 실행 중
./docker/container.sh start                  # 없을 때만 (인터넷 필요)
./docker/container.sh enter                  # 터미널마다 반복
```

> **컨테이너 `.bashrc`가 로드되지 않은 셸**이면 `zenohd: command not found`가 나고 환경변수도 같이 빠진다. 이 상태로 `omy_ai`를 띄우면 팔은 움직여도 zenoh에 안 붙어서 LEAP이 무반응이 된다. 터미널마다:
> ```bash
> source /opt/ros/jazzy/setup.bash
> export ROS_DOMAIN_ID=30 RMW_IMPLEMENTATION=rmw_zenoh_cpp
> ```

> **중복 실행 확인.** 컨테이너에는 follower/leader를 자동 실행하는 s6 서비스가 있다. `ros2 node list`와 `pgrep -a zenohd`가 **비어 있는지** 먼저 본다. 떠 있으면 그대로 쓰고 `omy_ai`는 실행하지 않는다.

> SSH가 `banner exchange` 타임아웃이면 ping과 TCP 22가 되어도 USB 랜 허브 문제다. 10/09에는 허브를 교체해 해결했다. **[실측 10/09]**

- [ ] LED 흰색, ssh 접속됨

## 6. zenohd와 omy_ai

**ROBOT PC · 터미널 A**
```bash
zenohd                                  # 종료하지 않는다
# 컨테이너 .bashrc가 안 읽힌 셸이면:  ros2 run rmw_zenoh_cpp rmw_zenohd
```

**USER PC**
```bash
leap_topics        # 에러 없이 나오면 연결된 것 (leap_env가 zenoh 환경을 잡는다)
```
- [ ] `ros2 topic list`가 에러 없이 나온다

**ROBOT PC · 터미널 B**

> **손은 주먹으로 대기**시킨 뒤 실행한다. 팔이 즉시 움직인다 (home → ready, 약 20초). leader 트리거를 쥔 채로 둔다.

**LEAP 90° 장착 (현재 기본): `omy_ai_wrist_flip`** **[실측 11/12]**

```bash
ssh root@omy-snpr44b1050.local
cd /data/docker/open_manipulator && ./docker/container.sh enter
export ROS_DOMAIN_ID=30 RMW_IMPLEMENTATION=rmw_zenoh_cpp   # 빠지면 DDS로 떠서 User PC가 팔 토픽을 못 본다
source /workspace/omy_ws/install/setup.bash
ros2 launch omy_leap_bringup omy_ai_wrist_flip.launch.py
```

- LEAP을 플랜지에서 **오른쪽 90°** 돌려 달고, follower joint6을 **+π/2** 돌려서 home에서 손가락이 위를 향한다.
- home 단계에서 손목이 왼쪽으로 90° 돈다. home·ready의 joint6 = π/2 (ready = [0, −90°, 152°, −62°, 90°, **90°**]).
- leader 기준으로 joint6은 +90° ~ −180°까지 돈다. **leader가 켜질 때 leader 손목을 0 근처로 잡는다.**
- 원리: leader broadcaster가 `leader 위치 + offsets`를 보내므로 joint6 offset만 π/2로 둔다. Homing Offset·순정 파일·모터 설정은 바꾸지 않았다. 코드: `OMY_Tactile_Robot_PC/omy_leap_bringup`.
- joint6만 π 돌리는 방식은 쓰지 않는다. follower joint6 모터 한계가 **±π**라 한쪽으로 못 돈다.
- D405는 `link6` 몸통에 붙어 있어서 90°만 돌아 **손 옆**에 온다.
- 녹화하면 joint6이 π/2 근처다. **순정 장착 데이터와 한 데이터셋에 섞지 않는다.**
- leader self-collision 검사는 offset 전 각도와 그리퍼 모델로 판단한다. 11/12에는 막힌 적이 없지만 정확하지 않다.

**순정 장착(손가락 아래)일 때만: `omy_ai`**

```bash
ros2 launch open_manipulator_bringup omy_ai.launch.py     # alias: omy_ai
```

### omy_ai가 하는 일

| 순서 | 실행 | 하는 일 |
|---|---|---|
| 1 | `omy_f3m_follower_ai` | follower(OMY-F3M) ros2_control 시작 |
| 2 | `joint_trajectory_executor` | 초기 자세로 이동. **home → ready** (각 10초). ready = [0, −90°, 152°, −62°, 90°, 0] (wrist_flip은 joint6 = 90°) |
| 3 | `omy_l100_leader_ai` | executor가 끝난 뒤 leader 시작. 중력 보상 + 동기화 |

LEAP을 단 상태에서도 공식 `omy_ai`가 그대로 동작한다. **[실측 10/09]** `omy_ai_wrist_flip`도 순서는 같고 joint6 값만 다르다.
leader 로그에 `BULK_READ_FAIL`(−3001, −3002)이 몇 초마다 찍히지만 허용 안이라 동작은 계속된다. 원인은 미조사다.

**확인 (터미널 C)**
```bash
ros2 control list_controllers                            # arm_controller, joint_state_broadcaster가 active
ros2 topic echo /leader/joint_trajectory --field points  # 값 7개 (마지막이 leader 트리거)
```
- [ ] leader를 움직이면 follower가 따라온다
- [ ] 트리거를 쥐면 7번째 값이 변한다
- [ ] (wrist_flip) home에서 손가락이 위를 향하고, leader 손목을 양쪽으로 돌려도 follower가 따라온다

## 6-1. 손목 카메라와 Paxini 촉각

**USER PC · 손목 카메라 D405** **[실측 11/12]**

OMY `Camera` 포트 → User PC USB.

```bash
sudo apt install ros-humble-realsense2-camera        # 한 번 (librealsense2 2.58)
ros2 launch realsense2_camera rs_launch.py camera_namespace:=camera camera_name:=cam_wrist \
  enable_depth:=false depth_module.color_profile:=424x240x30
ros2 run rqt_image_view rqt_image_view               # /camera/cam_wrist/color/image_raw/compressed
```

- 컬러 토픽은 `color/image_raw`다. config들에 적힌 `color/image_rect_raw`는 이 드라이버에서는 없다.
- 지금은 **USB 2.0(480M)으로만** 잡힌다. 기본 설정(848x480 + 깊이)은 9.3 Hz, 위 설정(424x240@30, 깊이 끔)은 18~30 Hz. 노트북 본체 USB3 직결과 USB3 케이블은 아직 시험하지 않았다.
- **OMY를 다시 켜면 카메라가 USB에서 사라진다.** 다시 꽂는다.
- `backend-hid.cpp ... Failed to read busnum/devnum` 경고는 노트북 내장 센서 때문이라 무시한다.
- 큰 이미지는 `ros2 topic hz`가 값을 못 낸다. 작은 rclpy 구독자로 잰다.

**USER PC · Paxini 촉각** **[실측 11/12]** 연동 확인. 절차는 정리 중이다.

```bash
pip install -e ~/SHAPE_UP_Tactile/third_party/paxini     # 한 번 (의존성은 pyserial)
```

- 사용법: `third_party/paxini/README.md`, `third_party/paxini/docs/SETUP_LINUX.md`, `USAGE_GUIDE.md`.
- 이 SDK는 공식 Paxini SDK가 아니라 커뮤니티 래퍼다 (`docs/FINDINGS.md`).

## 7. 단계 2: leader 트리거로 LEAP 열고 닫기

**이미 10/09에 검증됨.** 오늘은 팔 + zenoh + LEAP 경로가 살아 있는지 확인용이다.

leader 트리거 값 입력: 편 상태와 쥔 상태에서 7번째 값을 읽어 `user_pc/config/leader_gripper.yaml`의 `open_value` / `closed_value`에 넣는다. 지금은 임시값 0.0 / 1.0이고, 편 상태 실측은 약 0.197, **쥔 상태는 미측정**이다.

**USER PC**
```bash
leap_leader --dry-run     # 먼저 로그만. 트리거를 쥐고 펼 때 값이 따라가는지
leap_leader               # 실물. 주먹 → [teleop] waiting → live
```
- [ ] (a) 팔을 천천히 움직이면 follower가 따라온다
- [ ] (b) 트리거를 열고 닫으면 LEAP이 열리고 닫힌다
- [ ] (c) 팔을 움직이면서 동시에 열고 닫아도 서로 간섭이 없다

토픽이 0.5초 끊기면 마지막 자세를 유지(hold), 3초 끊기면 안전 자세(release). `Ctrl+C`로 종료하면 Torque OFF.

## 8. 2단계 정리, 3단계 준비

3단계(Manus 단독)는 팔이 필요 없다. 아래 순서로 끄고 새로 시작한다.

1. **User PC**: `leap_leader` 셸에서 `Ctrl+C` (Torque OFF).
2. **Robot PC 터미널 B**: `omy_ai` `Ctrl+C` — **팔이 처질 수 있으니 손으로 받친다.**
3. **Robot PC 터미널 A**: `zenohd` `Ctrl+C`.
4. **LEAP 5V를 편 손으로 껐다 켠다** (모터 회전수 누적 초기화).

3단계 셸은 모두 `LEAP_NO_ZENOH=1`이어야 한다 (`~/.bashrc` 기본값). 2단계에서 `unset` 했던 셸이면 `export LEAP_NO_ZENOH=1` 후 `leap_env`를 다시 한다. 확인: `echo "[$RMW_IMPLEMENTATION]"`이 `[]`.

- [ ] leap_leader 종료, omy_ai 종료(팔 받침), zenohd 종료
- [ ] LEAP 5V를 편 손으로 재투입

## 9. 단계 3-1: Manus 노드와 토픽 확인

코드가 SDK 소스에서 읽어 가정한 값이 맞는지 실제 echo로 확인한다. 글러브를 착용한다. **[실측 11/03]** 아래 항목 모두 확인됨.

> **위험 · MANUS Core Dashboard를 먼저 끈다.** 노드는 integrated 모드(기본)로 동글을 직접 연다. Dashboard가 켜져 있으면 `Resource busy` + `No license found … Integrated`로 토픽이 안 나온다. 확인: `pgrep -a MANUS_Core`가 비어 있어야 한다. Dashboard에 붙는 local 모드(`-p connection_type:=local`)도 넣어 두었지만 Linux Dashboard는 SDK 연결을 받지 않아 쓸 수 없었다.

**셸 1 · Manus 노드** (이 User PC, 동글도 이 PC에)
```bash
leap_env
echo "[$RMW_IMPLEMENTATION]"                    # [] 이어야 한다
ros2 run manus_ros2 manus_data_publisher        # "running in integrated mode", Resource busy 없음
```

**셸 2 · 확인**
```bash
leap_env
ros2 topic list | grep -i manus                 # /manus_glove_0, /manus_glove_0/vibration_cmd
ros2 topic hz /manus_glove_0                    # 약 120 Hz (11/03: 119.9)
ros2 topic echo /manus_glove_0 --once > ~/echo.txt
```

`echo.txt`에서 확인한다. 하나라도 틀리면 키포인트가 빠져 엄지가 조용히 affine으로 돈다.

- [ ] 손목 raw node가 `chain_type=Hand`, `joint_type=Invalid` **[실측 11/03]**
- [ ] 엄지에 `joint_type=DIP` 노드가 있다 **[실측 11/03]**
- [ ] ergonomics 값이 도(°) 단위다 (−35 ~ 42 범위) **[실측 11/03]**
- [ ] ergonomics 이름 20개 (`ThumbSpread, ThumbCMCStretch, ThumbMCPStretch, ThumbIPStretch, IndexSpread, IndexMCPStretch …`)가 모두 있다

- 토픽이 `/manus_glove_0`이 아니면 `user_pc/config/manus_leap.yaml`의 `topic`을 바꾼다. 왼손이면 `--glove-side Left`. 오른손을 `/manus_glove_right`로 고정하려면 노드를 `-p glove_topic_template:=manus_glove_{side}`로 실행한다.
- 노드는 120 Hz로 마지막 값을 반복 발행하고 timestamp가 없다. ergonomics가 0.5초 넘게 완전히 같으면 끊김으로 보고 hold한다.

## 10. 단계 3-2: 글러브 캘리브레이션

**먼저 Manus SDK 캘리브레이션** **[실측 11/12]**. 노드는 integrated 모드라 Dashboard 캘리브레이션이 적용되지 않는다. 안 하면 검지 PIP가 0에 붙어 검지가 중간에 멈춘다 (11/12: PIP가 0에 붙는 비율 60% → 1%). **글러브를 완전히 충전한 상태에서** 한다. 11/12에는 배터리 `DEAD` 상태에서 해서 엄지 IK가 오히려 나빠졌다. 엄지 단계를 신경 써서 하고, **`K`로 `.mcal`을 꼭 저장한다**. 글러브를 껐다 켜도 유지되는지는 아직 모른다.

```bash
# ROS Manus 노드를 끈 상태에서 (동글은 프로그램 하나만 쓴다)
cd third_party/manus/Python && python3 examples/sdk_client.py
# 1 (Integrated) → C → H로 Right → S → 단계마다 E 실행, P 다음 → F → K 저장(.mcal)
```
그 뒤 노드를 다시 켜고, 아래 우리 캘리브레이션도 **다시** 한다 (글러브 각도가 바뀐다).

작업자마다 한다. **글러브를 낀 손으로** 한다. LEAP은 필요 없다. 결과는 `config/manus_calibration.yaml` (gitignore).

> **편 손은 충분히 쭉 편다.** 덜 편 채로 기록하면 평소 편 손이 "편 손"으로 읽혀 LEAP이 덜 펴진다. **[실측 11/03]** 더 펴서 다시 하니 해결. 주먹은 엄지를 검지·중지 위로 감싼다 (주먹 안에 넣지 않는다).

```bash
leap_glovecal --force      # 편 손 Enter → 주먹 Enter
```
- [ ] 마지막 줄 `fist thumb, mm in front of palm`의 두 값 부호가 같다

부호가 다르면 WARNING이다. `config/manus_leap.yaml`의 `thumb_ik.flip_normal`을 `true`로 바꾸고 다시 한다.

## 11. 단계 3-3: dry-run

LEAP을 건드리지 않는다.

```bash
leap_manus --dry-run
```
- [ ] `[teleop] live`가 되고, 손을 움직이면 값이 바뀐다
- [ ] 로그가 `affine`으로 떨어지지 않는다 (키포인트를 찾았다)

`waiting`에서 안 바뀌면 순서대로 확인한다.
1. 노드가 도는가, `ros2 topic echo`로 값이 오는가
2. 토픽 이름(`manus_leap.yaml`), `--glove-side`
3. 두 셸의 RMW가 같은가 (`echo $RMW_IMPLEMENTATION`)
4. 글러브가 멈춘 값만 반복 중이 아닌가 (0.5초 이상 동일하면 버림)
5. ergonomics 이름 20개가 다 있는가 (하나라도 빠지면 reading을 버림)

## 12. 단계 3-4: LEAP 실물

> 5V를 **편 손**으로 켰고, 차단 수단이 손 닿는 곳에 있는지 확인한다.

```bash
leap_check                    # ID 0~15 응답, 오류 0
leap_manus                    # 엄지 IK (기본). 편 손, 주먹, 손가락 하나씩, 엄지, pinch 순서로 천천히
# leap_manus --thumb affine   # 진단용: 엄지 대응이 이상할 때만
```
`manus_leap.yaml`은 시작할 때만 읽는다. 값을 바꾸면 `Ctrl+C` 후 다시 띄운다.

**엄지 방식 (11/03 수정)**

| 관절 | 방식 | 설정 |
|---|---|---|
| 12·13·14번 | IK: 엄지 끝 + IP 관절 위치를 맞춘다 | `thumb_ik.ip_weight: 0.3` |
| 15번 (엄지 맨 위 관절) | 글러브 `ThumbIPStretch`를 그대로 따른다 (affine). 끝만 맞추는 IK에서는 15번이 거의 안 굽었다 **[실측 11/03]** | `thumb_ik.ip_joint: affine` (예전 방식은 `ik`) |
| 15번 젖힘 | 편 손보다 더 젖히면 LEAP도 뒤로 젖힌다 (최대 20°). 전에는 0°에서 잘렸다 **[미검증]** | `thumb_ip_extend_max_deg: 20.0` (0 = 끔) |

- [ ] 손가락 5개가 글러브를 따라간다 (방향 정상)
- [ ] 엄지가 대응된다, 맨 위 관절도 같이 굽는다 **[실측 11/03]**
- [ ] 엄지 맨 위 관절이 손등 쪽으로 젖혀진다 **[미검증]**
- [ ] 엄지 끝–검지/중지/약지 끝 pinch
- [ ] 글러브를 벗거나 노드를 끄면 hold(0.5초) → release(3초)로 안전 자세

안 맞을 때:
- 손가락 방향이 반대 → `manus_leap.yaml`의 `side_gain` 또는 `joint_map`
- 엄지가 이상함 → `--thumb affine`으로 대응표부터 맞춘 뒤 IK
- 엄지 맨 위 관절이 덜/더 젖혀짐 → `thumb_ip_extend_max_deg`
- pinch 틈이 큼 → 15번 고정 때문일 수 있다. `ip_joint: ik`와 비교
- **검지가 끊김** **[실측 11/12 해결]**: 글러브 `IndexPIPStretch`가 0에 붙던 것. 원인은 Manus **SDK 캘리브레이션 누락**이었다 (10절). Dashboard 캘리브레이션은 integrated 모드에 적용되지 않는다.
- **엄지가 안 펴짐 / 엄지 맨 위 관절이 튐** **[실측 11/12, 미해결]**: SDK 캘리브레이션 뒤 `ThumbCMCStretch` 범위가 5°로 줄었다. 글러브를 충전하고 SDK 캘리브레이션(`.mcal` 저장) → `leap_glovecal --force` → `leap_manus --log-csv logs/run_ik.csv`로 다시 본다.
- 빠르게 움직이면 LEAP이 최대 0.5초 늦다 (속도 제한 120°/s). 250~300°/s로 올리는 것을 검토 중이다.
- IK에서 손끝 틈이 남음 → pinch snap 추가 검토 (spec 7절)
- pinch 결과는 `docs/field-test/`에 10/09 형식으로 남긴다

## 13. 단계 4: Manus + 팔

팔은 leader, 손은 글러브. 두 프로세스는 독립이고 leader 트리거는 LEAP에 영향이 없다 (`--source manus`).

1. 3단계를 끝낸 뒤 `leap_manus`를 `Ctrl+C`로 종료하고, LEAP을 **주먹**으로 대기시킨다 (safe-pose가 주먹).
2. **ROBOT PC**: 터미널 A `zenohd`, 터미널 B `omy_ai_wrist_flip` (90° 장착, 6절). leader 트리거를 쥔 채로.
3. Manus 노드(셸 1)는 그대로 두고 **USER PC**에서:
   ```bash
   export LEAP_NO_ZENOH=1
   leap_manus
   ```

- [ ] 팔을 움직이는 동안에도 손이 글러브를 따라간다
- [ ] 글러브를 벗으면 hold → release 된다
- [ ] 물체 하나를 집어 본다

> leader를 **손으로 잡고** 한다. 팔이 움직이는 동안 LEAP은 주먹이어야 한다.

## 14. 단계 5-1: Cyclo 준비

> **보류 (11/13).** User PC(Humble)가 Robot PC(Jazzy) 토픽의 메시지를 못 받는다 **[실측 11/12]**. 그래서 Cyclo(Jazzy 컨테이너)에서는 반대로 손·카메라가 안 보일 것으로 예상한다. 촉각도 같이 모아야 해서 **자체 녹화 프로그램(LeRobot 형식)**으로 간다. 14·15절은 참고용으로 남긴다.

세화형의 `docs/data_preparation/omy_demonstration_runbook.md`(카메라 3대 기록)를 그대로 쓰고, 달라지는 점만 더한다. 자세한 내용은 [`data_preparation/omy_leap_cyclo_recording.md`](data_preparation/omy_leap_cyclo_recording.md).

| 무엇 | 토픽 | Cyclo 역할 |
|---|---|---|
| 팔 state | `/joint_states` (joint1..6) | observation.state.arm |
| 팔 action | `/leader/joint_trajectory` | action.arm |
| 손 state | `/leap/joint_states` (rad, mA) | observation.state.hand |
| 손 action | `/leap/joint_command` (rad) | action.hand |
| 부가 | `/leap/human_hand` · `/leap/human_keypoints` · `/leap/teleop_mode` | extra_topics (bag에만) |

state·action 각각 팔 6 + 손 16 = **22차원**. action은 로봇에 **실제로 보낸 최종 명령**이다.

**로봇 config 복사 (USER PC 호스트)**
```bash
cp ~/SHAPE_UP_Tactile/user_pc/config/omy_f3m_leap_config.yaml ~/cyclo_intelligence/shared/shared/robot_configs/
nano ~/cyclo_intelligence/shared/shared/robot_configs/omy_f3m_leap_config.yaml
```
- **카메라 3개의 `topic`**을 세화형 B6에서 확인한 실제 RGB 압축 토픽으로 바꾼다 (파일 값은 예시).
- 손 `joint_names` 16개는 `leap_teleop`이 내는 이름과 글자까지 같아야 한다. 바꾸지 않는다.
- 팔 `joint_names`는 `joint1..6`만 (`rh_r1_joint` 제외).
- 세화형 B7(`omy_f3m_config.yaml` 편집)은 하지 않는다. 새 로봇 타입이다.

- [ ] 세화형 A, B1–B6 완료: 카메라 3대 동작, 토픽 경로 확인
- [ ] config 복사, 카메라 topic 수정

## 15. 단계 5-2: 기록하기

**zenoh를 켠다.** Manus 노드(셸 1)를 `Ctrl+C` 하고, `unset LEAP_NO_ZENOH` 한 셸에서 다시 띄운다. 둘 다 같은 환경이어야 한다.

**셸 1 · Manus 노드**
```bash
unset LEAP_NO_ZENOH
leap_env && ros2 run manus_ros2 manus_data_publisher
```

**셸 2 · 기록용 발행**
```bash
unset LEAP_NO_ZENOH
leap_record                      # leap_manus --publish
leap_topics                      # /leap/joint_command, /leap/joint_states, /leap/human_*, /leap/teleop_mode
ros2 topic hz /leap/joint_command /leap/joint_states     # 50 Hz 근처인지
```
- [ ] `/leap/*` 토픽이 **컨테이너에서도** 보인다 **[미검증]**
- [ ] `joint_states`가 50 Hz 근처 (16모터 피드백 비용)

**브라우저 · Cyclo UI**
1. Cyclo 실행 후 `http://localhost:7080/`, 로봇 유형 **OMY F3M + LEAP** 선택.
2. `Record → Topic Monitor`에서 `/leap/*`, 팔 두 토픽, 카메라 3개가 모두 수신되는지 본다.
3. 시작 상태에 놓고 `Record Start` → 짧게 시연 → `Save Episode`.

**기록 확인**
```bash
ros2 bag info /workspace/rosbag2/<데이터셋>/0/
```
- [ ] 토픽 5개(`/leap/*`)의 메시지 수가 0보다 크다
- [ ] `/leap/human_keypoints`가 0이 아니다 (0이면 키포인트를 못 찾은 것)
- [ ] `Convert Dataset` 후 state·action이 22차원 **[미검증]**

## 16. 종료 순서

1. 녹화가 끝났는지 확인한다.
2. **`leap_*` 셸 `Ctrl+C`** (Torque OFF). 손이 풀려 처지니 물체가 손에 없는지 본다.
3. 카메라 터미널(realsense), 촉각 기록, Cyclo 터미널.
4. **`omy_ai_wrist_flip`(또는 `omy_ai`) `Ctrl+C`** — **팔이 처질 수 있으니 손으로 받친다.**
5. `zenohd` `Ctrl+C`, Manus 노드 종료.
6. **LEAP 5V OFF.**
7. 보관하려면 17절의 pack, 그다음 로봇 전원 OFF.

켜는 순서: `LEAP 5V(편 손)` → `Manus 노드` → `zenohd` → `omy_ai_wrist_flip` → `leap_*` → `카메라·촉각` → `녹화`. 끄는 순서는 반대.

## 17. pack / unpack

OMY를 접어 보관하거나 펴는 launch다. `omy_3m.launch.py`에 목표 자세만 바꿔 넣는 래퍼다.

| | 명령 | 이동 | 자세 |
|---|---|---|---|
| **pack** | `ros2 launch open_manipulator_bringup omy_3m_pack.launch.py` | home → pack (각 10초) | [0, 0, −150°, −30°, 0, 0] |
| **unpack** | `ros2 launch open_manipulator_bringup omy_3m_unpack.launch.py` | home | 전부 0 |

> **위험**
> - `omy_ai`와 **동시에 실행하지 않는다** (둘 다 follower ros2_control을 띄운다).
> - `omy_3m`은 끝단 없는 6축 모델이다. **LEAP을 단 채로 접을 때 손이 베이스·바닥에 부딪히는지는 확인된 바 없다. [미검증]** 처음에는 손을 떼거나, 팔을 받치고 5V를 끈 채 천천히 한다.
> - 접기 전 LEAP 5V를 끄고 케이블이 당기지 않는지 본다.

최초 수령 시 포장 해제(unpacking) 절차는 이 레포에 없다. [ROBOTIS Setup Guide](https://docs.robotis.com/docs/systems/omy/quick_start_guide/setup_guide)를 따른다.

## 18. 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| `No module named 'manus_ros2_msgs'` | `LEAP_MANUS_WS` export 했나, `colcon build` 했나 |
| `[teleop] waiting`에서 안 바뀜 (Manus) | 노드 동작 / 토픽 이름 / 두 셸의 RMW / 값이 멈춤 / ergonomics 20개 |
| 엄지가 이상함, 로그에 `affine` | 손목 `Invalid`, 엄지 `DIP` 노드 이름. `KEYPOINT_NODES`는 `sources/manus.py` |
| 손가락 방향 반대 | `side_gain` 또는 `joint_map` (`manus_leap.yaml`) |
| `No module named rclpy` | `PYTHONPATH`가 ROS 경로를 덮어씀. `leap_env`를 거쳤는지 |
| `ModuleNotFoundError: dynamixel_sdk` | ROS를 source 하지 않은 셸 |
| `Missing or unresponsive DYNAMIXEL IDs` | 5V, USB, Dynamixel Wizard가 포트를 점유 중인지 |
| `error: … not found. Run calibrate_motors` | 영점 파일이 없다. 1단계 영점 기록을 먼저 |
| `ros2 topic list`가 비어 있음 (zenoh) | ROBOT_IP, 포트 7447, `zenohd` 실행 여부, `ZENOH_CONFIG_OVERRIDE` |
| 팔은 움직이는데 LEAP 무반응 (leader) | `omy_ai`가 `RMW_IMPLEMENTATION`/`ROS_DOMAIN_ID` 없이 실행됨. export 후 재실행 |
| `zenohd: command not found` | 컨테이너 .bashrc 미로드. `ros2 run rmw_zenoh_cpp rmw_zenohd` |
| bringup `0xc Multi-turn Error` | Debug USB + Dynamixel Wizard로 Clear (10/09 문서 부록 A). **Factory Reset 금지** |
| `Resource busy` / `dongle interface is claimed by another program` | MANUS Core Dashboard가 동글을 잡고 있음. Dashboard를 끄고 노드 재실행 |
| 노드 시작 시 "SDK license" 에러 | 먼저 Dashboard가 꺼졌는지. 꺼진 상태에서도 나면 라이선스에 Integrated 기능이 없음 |
| 노드가 `tcp/10.42.0.241:7447` 접속 실패 후 `bad_alloc` | 셸에 zenoh 환경이 남음. `export LEAP_NO_ZENOH=1` 후 `leap_env` 다시 (11/03부터 `leap_env`가 남은 변수를 지운다) |
| `No module named 'serial'` | `sudo apt install python3-serial` |
| pytest `No module named '_pytest.scope'` | `-p no:anyio` (또는 `PYTEST_ADDOPTS`) |
| `ncursesw/ncurses.h` (Manus 빌드) | `sudo apt install libncurses-dev` |
| 텔레옵 중 leader가 튐 | 원인 미확인. leader를 손으로 잡는다 |
| `ping 10.42.0.241`이 `Time to live exceeded` | USB 랜이 IP를 못 받음. `nmcli connection modify "Wired connection 1" ipv4.method shared` (5절) |
| follower joint6이 한쪽으로 덜 돎 | joint6을 π 근처에 두면 모터 한계(±π)에 걸린다. 90° 장착 + `omy_ai_wrist_flip`(π/2)을 쓴다 |
| `leap_check`에서 한 모터만 ±180° | 혼이 반 바퀴 돌아 조립됨 (11/12 ID 11). 편 손에서 1·5·9번(약 −85°) 말고는 0 근처(±15°)여야 한다 |
| LEAP 일부 ID(예: 0~3)만 ping 실패 | 그 손가락 쪽 케이블을 다시 꽂는다 **[실측 11/12]** |
| User PC에서 Robot PC 토픽이 보이는데 메시지 0개 | Humble↔Jazzy `rmw_zenoh` 불통 (3절). 텔레옵은 무관 |
| D405가 안 보임 / 느림 | OMY를 다시 켰으면 다시 꽂는다. USB2로 잡히면 424x240@30, 깊이 끔 (6-1절) |

## 19. 아직 모르는 것

실물에서 처음 확인하는 항목. 틀리면 어디를 고치는지 같이 적었다.

| 항목 | 확인 방법 | 틀리면 |
|---|---|---|
| ~~손목 `Invalid`, 엄지 `DIP`, ergonomics 도 단위, Integrated 라이선스~~ | **[실측 11/03]** 모두 맞음 | (Dashboard를 끄면 Integrated 라이선스 OK) |
| 엄지 IP 젖힘 (`thumb_ip_extend_max_deg` 20°) | 3-4 편 손에서 엄지 젖히기 | 각도 조정, 0이면 끔 |
| 15번 affine 고정 시 pinch 정확도 | 3-4 pinch | `ip_joint: ik`와 비교 |
| ~~검지 PIP가 0에 붙음~~ | **[실측 11/12]** SDK 캘리브레이션 누락이 원인 | 10절 |
| 엄지 IK (SDK 캘리브레이션 뒤 나빠짐) | 충전 후 재캘리브레이션, `--log-csv` | `ThumbCMCStretch` 범위 확인 |
| SDK 캘리브레이션이 글러브 재부팅 후 유지되는가 | 껐다 켜고 PIP 확인 | ROS 노드가 `.mcal`을 불러오게 (`CoreSdk_SetGloveCalibration`) |
| ~~Humble `rmw_zenoh`(User PC) ↔ Jazzy `zenohd`(Robot PC)~~ | **[실측 11/12]** 탐색만 되고 데이터 0개 | DDS 통일 / Jazzy 컨테이너 / 24.04 |
| 호스트 `leap_teleop` 토픽이 컨테이너 Cyclo에 보이는가 | 5단계 `leap_topics` | 호스트 zenoh 환경을 맞춘다 |
| `/leap/joint_states` 주기 (16모터 피드백 비용) | `ros2 topic hz` | 발행 주기를 낮춘다 |
| UI에 **OMY F3M + LEAP**이 나타나는가 | Cyclo 실행 후 Home | Cyclo 컨테이너 재시작 |
| 변환기가 `rh_r1_joint`를 걸러내는가 (22차원) | Convert 결과 | config 팔 `joint_names` 확인 |
| 팔·손 `header.stamp` 대 bag 수신 시각 | 첫 에피소드 | 두 PC를 chrony로 맞춘다 |
| LEAP을 단 채 pack/unpack, LEAP 하중 | 팔을 받치고 천천히 | 손을 떼고 접는다 |
| leader 트리거 쥔 상태 값 | 단계 2 | `leader_gripper.yaml` 갱신 |

---

자세한 내용: `user_pc/README.md` · `docs/field-test/2026-11-03-*.md` · `docs/data_preparation/omy_leap_cyclo_recording.md` · `docs/superpowers/specs/2026-10-29-ros-data-interface-design.md`
