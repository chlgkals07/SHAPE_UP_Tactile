# OMY 로봇 연결, 구조, omy_ai, pack/unpack

OMY 팔에 LEAP Hand를 달고 Manus로 텔레옵하기 위해 **로봇 쪽(Robot PC)을 어떻게 켜고 연결하는지**를 정리한 문서다. 손 쪽 절차는 `user_pc/README.md`, 단계별 요약은 `2026-11-03-manus-teleop-quickstart.md`, 10/09 실물 기록은 `2026-10-09-*.md`를 본다.

근거 표기: **[소스]** `third_party/open_manipulator`(ROBOTIS 저장소 @ `9f84095`)의 코드/launch/config에서 직접 읽음, **[실측 10/09]** 현장에서 해 본 결과, **[공식 문서]** ROBOTIS 문서(이 레포에 없고 10/09 문서가 인용), **[미검증]** 아직 해 보지 않음.

---

## 1. 전체 구조

### 하드웨어
| 장치 | 역할 | 연결 |
|---|---|---|
| **OMY-F3M** (follower) | 실제 움직이는 팔. 6축(joint1..6) + 끝단(원래 그리퍼 `rh_r1_joint`, 우리는 **LEAP Hand**로 교체) | Robot PC 내부 |
| **OMY-L100** (leader) | 사람이 잡고 움직이는 팔. 7모터(6축 + 트리거 `rh_r1_joint`) | Robot PC 내부 (버스) |
| **Robot PC** | OMY 본체 안의 PC. ROS 2 컨테이너 `open_manipulator`가 돈다 | 이더넷으로 User PC와 연결 |
| **User PC** | 우리 작업 PC. LEAP, Manus, 카메라, Cyclo가 여기 연결된다 | 이더넷 (Robot PC), USB (LEAP, Manus 동글, 카메라) |
| **LEAP Hand v1** | 16모터 손. 5V 전원 + FTDI USB (`/dev/ttyUSB0`) | User PC에 직접 USB, **ROS 밖** |
| **Manus 글러브** | 사람 손 입력. 동글 USB, SDK ROS 2 노드 | User PC (Manus 노드) |

### 소프트웨어 프로세스
```
[ROBOT PC · 컨테이너]                               [USER PC]
 zenohd (:7447) ◄──────── zenoh client ──────────── leap_teleop (LEAP 구동, 손)
                                                    Manus SDK 노드 (/manus_glove_0)
 omy_ai.launch.py                                   RealSense ×3, Cyclo (5단계)
  ├ omy_f3m_follower_ai  (follower, 팔 구동)
  ├ joint_trajectory_executor (home → ready)
  └ omy_l100_leader_ai   (leader, 중력보상 + 동기화)
      ├ /leader/joint_trajectory  → follower가 따라감
      └ /joint_states             ← follower 상태
```
- **팔의 텔레옵 루프는 Robot PC 안에서 닫힌다.** leader를 움직이면 follower가 따라간다. User PC는 관여하지 않는다.
- **손은 User PC에서 따로 닫힌다.** `leap_teleop`이 Manus(또는 leader 트리거) 입력을 LEAP으로 보낸다. 팔과 손은 서로 독립 프로세스다.
- 두 PC는 **zenoh**(`rmw_zenoh_cpp`)로 ROS 토픽을 주고받는다. Robot PC의 `zenohd`가 라우터, User PC는 client다. 팔 토픽을 읽어야 하는 것은 Cyclo 기록(5단계)과 leader 트리거 입력(2단계)뿐이다.

## 2. 로봇 연결

### 2-1. 전원과 네트워크
1. 전원 버튼을 눌렀다 떼서 LED가 **흰색**이 될 때까지 기다린다 [공식 문서].
2. 이더넷으로 Robot PC ↔ User PC를 연결한다 (같은 네트워크).
3. SSH 접속. 호스트 이름은 로봇 SN 기반이다 [공식 문서]:
   ```bash
   ssh root@omy-<SN>.local          # 비밀번호 없음. 안 되면 robotis@ 로 시도
   ```
   - 44B1050 로봇은 `10.42.0.241` / `omy-snpr44b1050.local` (User PC의 USB 랜을 NetworkManager 공유 모드 `10.42.0.1`로 둔 경우) [실측 10/09].
   - `hostname -I`로 Robot PC에서 User PC가 접속 가능한 IP를 확인한다. IP가 바뀌면 `OMY_ROBOT_IP`와 `ZENOH_CONFIG_OVERRIDE`를 같이 고친다.
4. **증상: ping과 TCP 22는 되는데 `Connection timed out during banner exchange`로 SSH가 안 됨** → 재부팅·USB-A 직결로는 안 풀렸고 **더 좋은 USB 랜 허브로 교체**하자 해결됐다 [실측 10/09].

### 2-2. Robot PC 컨테이너
```bash
cd /data/docker/open_manipulator
docker ps                          # open_manipulator가 보이면 이미 실행 중 (compose: restart: always)
./docker/container.sh start        # 없을 때만. image pull을 하므로 인터넷 필요
./docker/container.sh enter        # 컨테이너 진입. 터미널마다 반복
```
컨테이너 `.bashrc`에 `ROS_DOMAIN_ID=30`, `RMW_IMPLEMENTATION=rmw_zenoh_cpp`, alias `zenohd`/`omy_ai`가 이미 있다 [공식 Dockerfile].

> **`.bashrc`가 로드되지 않은 셸**에서는 `zenohd: command not found`가 나고 **환경변수도 같이 빠진다.** 이 상태로 `omy_ai`를 띄우면 팔은 움직이지만 zenoh에 붙지 않아 User PC에서 `/leader/joint_trajectory` 발행자가 0개가 된다 (LEAP 무반응). 터미널마다 아래를 해 준다 [실측 10/09]:
> ```bash
> source /opt/ros/jazzy/setup.bash
> export ROS_DOMAIN_ID=30 RMW_IMPLEMENTATION=rmw_zenoh_cpp
> ros2 run rmw_zenoh_cpp rmw_zenohd                              # zenohd 대신
> ros2 launch open_manipulator_bringup omy_ai.launch.py          # omy_ai 대신
> ```

> **s6 서비스 충돌 확인**: 컨테이너에는 follower/leader를 자동 실행하는 s6 서비스(`open_manipulator_bringup`, `leader_bringup`)가 있다 [소스 `docker/s6-services`]. 이미 떠 있으면 `omy_ai`가 중복 실행된다. `ros2 node list`와 `pgrep -a zenohd`가 **비어 있는지** 먼저 본다. 떠 있으면 그것을 그대로 쓰고 `omy_ai`는 실행하지 않는다.

### 2-3. User PC 쪽 연결
User PC 셸이 같은 도메인과 RMW, 같은 라우터를 봐야 한다. `scripts/leap_aliases.sh`의 `leap_env`가 이를 한다.
```bash
export ROS_DOMAIN_ID=30 RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_CONFIG_OVERRIDE='mode="client";connect/endpoints=["tcp/<ROBOT_IP>:7447"]'
ros2 daemon stop                  # 오래된 daemon 정리 (공식 트러블슈팅)
ros2 topic list                   # /leader/joint_trajectory, /joint_states 가 보여야 연결된 것
```
다른 PC 사이에서는 `transport/shared_memory/enabled=true`가 필요 없다. 컨테이너 시험에서는 켜면 `Failed to create POSIX SHM provider`로 초기화가 실패했다.

## 3. omy_ai가 하는 일 [소스 `omy_ai.launch.py`]

`omy_ai.launch.py`는 세 단계를 **순서대로** 실행한다.

| 순서 | 실행 | 하는 일 |
|---|---|---|
| 1 | `omy_f3m_follower_ai.launch.py` | follower(OMY-F3M) ros2_control 시작. 팔 6축 + 끝단 |
| 2 | `joint_trajectory_executor` | follower가 시작되면 **초기 자세로 이동**: `home` → `ready` (각 10초) |
| 3 | `omy_l100_leader_ai.launch.py` | executor가 **끝난 뒤** leader 시작. 중력 보상 + leader→follower 동기화 |

- `ready` 자세(`initial_positions.yaml`): joint1..6 = `[0, -90°, 152°, -62°, 90°, 0]`, 끝단 0 [소스]. `home`은 전부 0.
- 그래서 **launch 즉시 팔이 움직인다** (home → ready까지 약 20초). 작업 공간을 비우고 비상 정지 수단을 확인한 뒤 실행한다.
- 이 이동 중에는 leader가 아직 시작하지 않았으므로 leader를 잡고 있어도 된다. 3단계가 시작되면 leader가 follower와 동기화된다.
- LEAP을 단 상태에서도 공식 `omy_ai`가 그대로 동작했다 (끝단 `rh_r1_joint` 항목은 토픽에 남는다) [실측 10/09]. 우리 패키지(`omy_leap_bringup`)는 필요 없었다.
- **손목 뒤집기 모드** (`omy_leap_bringup/omy_ai_wrist_flip.launch.py`, `OMY_Tactile_Robot_PC` README) [미검증]
  - 홈 자세에서 손가락이 위로 가게 한다. 180°를 나눠서 LEAP 기구 장착으로 90°(오른쪽), follower joint6으로 +π/2를 돌린다. D405는 link6에 붙어 있어서 90°만 돌아 손의 옆에 온다.
  - leader broadcaster의 `offsets`에서 joint6을 π/2로 둔다 [소스 `joint_trajectory_command_broadcaster.cpp`: 발행값 = leader 위치 + offset]. 그리고 `home`/`ready`의 joint6을 π/2로 둔다.
  - joint6 하나로 π를 돌리지 않는 이유: follower joint6 모터의 Min/Max Position Limit이 ±262144 pulse = **±π**다 [실측 11/12, `get_dxl_data`]. URDF ±2π보다 모터 한계가 우선한다. home π에서는 한쪽으로 돌 여유가 0이었다.
  - π/2에서는 leader 기준 +90° ~ −180°까지 돈다.
  - Homing Offset은 바꾸지 않는다. 그래서 URDF/TF가 실제 자세와 그대로 맞는다.
- leader 로그에 `FastBulkRead Rx Fail [Dxl Size : 7]` / `BULK_READ_FAIL`(-3001, -3002)이 몇 초마다 찍히지만 허용 안이라 동작은 계속된다. 원인은 미조사이고 follower가 아니라 **leader 버스**(모터 7개) 로그다 [실측 10/09].
- **텔레옵 중 leader가 갑자기 크게 튄 적이 있다.** 텔레옵하는 동안은 **leader를 반드시 손으로 잡는다** [실측 10/09].

### 확인
```bash
ros2 control list_controllers                            # arm_controller, joint_state_broadcaster가 active
ros2 topic echo /leader/joint_trajectory --field points  # 값 7개 (마지막이 rh_r1_joint = leader 트리거)
ros2 topic echo /joint_states --once                     # follower 상태
```
leader를 천천히 움직여 follower가 따라오는지, 트리거를 쥐면 7번째 값이 변하는지 본다. 트리거 값은 `user_pc/config/leader_gripper.yaml`로 0~1에 정규화된다 (편 상태 약 0.197, 쥔 상태는 미측정).

## 4. pack / unpack

OMY를 접어서 보관하거나 운반 자세로 옮기는 launch다 [소스 `omy_3m_pack.launch.py`, `omy_3m_unpack.launch.py`]. 둘 다 `omy_3m.launch.py`에 목표 자세 파일만 바꿔 넣는 얇은 래퍼다.

| | 명령 | 이동 | 자세 파일 |
|---|---|---|---|
| **pack** (접기) | `ros2 launch open_manipulator_bringup omy_3m_pack.launch.py` | home → pack (각 10초) | `config/omy_3m/pack_positions.yaml` |
| **unpack** (펴기) | `ros2 launch open_manipulator_bringup omy_3m_unpack.launch.py` | home | `config/omy_3m/initial_positions.yaml` |

- **pack 자세**: joint1..6 = `[0, 0, -150°, -30°, 0, 0]`, **unpack/home**: 전부 0 [소스].
- 이 launch는 `omy_ai`와 **동시에 실행하지 않는다.** 둘 다 follower ros2_control을 띄우므로 하나를 종료하고 다른 것을 쓴다.
- `omy_3m`은 끝단 없는 6축 모델이다. 우리 로봇은 끝단에 LEAP이 달려 있다. **LEAP이 달린 채로 접을 때 손이 베이스·바닥과 부딪히지 않는지는 [미검증]**이다. 처음에는 손을 떼거나, 팔을 손으로 받치고 5V를 끈 채 천천히 해 본다.
- 접기 전에 LEAP 5V를 **끄고**, 손이 케이블에 당기지 않는지 본다.
- 공식 문서의 unpacking(최초 수령 시 포장 해제) 절차는 이 레포에 없다. 상자에서 처음 꺼낼 때는 ROBOTIS Setup Guide의 절차를 따른다 (https://docs.robotis.com/docs/systems/omy/quick_start_guide/setup_guide).

### 접는 순서
1. `omy_ai`를 쓰고 있었다면 `Ctrl+C`로 종료한다 (**팔이 처질 수 있으니 손으로 받칠 준비**).
2. LEAP 5V OFF, `leap_teleop` 종료.
3. `omy_3m_pack.launch.py` 실행 → 접힌 자세까지 이동하는 동안 지켜본다.
4. 이동이 끝나면 `Ctrl+C`, 그다음 로봇 전원을 끈다. 문서에 로봇 종료 절차는 없다.

## 5. 하루 순서 (팔 + 손 + 기록)

**켜기**
1. 작업 공간을 비운다. LEAP 5V는 **편 손으로** 켠다 (모터 회전수 누적 초기화).
2. 로봇 전원 ON (LED 흰색), 이더넷 연결, `ssh`로 확인.
3. Robot PC 터미널 A: `zenohd`. 종료하지 않는다.
4. User PC: `leap_topics`(또는 `ros2 topic list`)가 에러 없이 나오는지 확인.
5. **손을 주먹으로 대기시킨다.** (`leap_manus`/`leap_leader`는 `--safe-pose fist`가 기본)
6. Robot PC 터미널 B: `omy_ai` (leader 트리거를 쥔 채로). 팔이 home → ready로 움직인다.
7. User PC: `leap_manus` (또는 `leap_leader`). `[teleop] waiting` → `live`.
8. 기록하려면 카메라, Cyclo는 `docs/data_preparation/omy_leap_cyclo_recording.md`.

**끄기** (반대 순서)
1. `leap_*` `Ctrl+C` (Torque OFF).
2. `omy_ai` `Ctrl+C` (**팔 받치기**).
3. `zenohd` `Ctrl+C`, Manus 노드 종료, LEAP 5V OFF.
4. 보관하려면 4절의 pack, 그다음 로봇 전원 OFF.

## 6. 문제가 났을 때 [실측 10/09]

| 증상 | 원인 | 해결 |
|---|---|---|
| bringup `0xc Multi-turn Error` | 액추에이터 멀티턴 상태 이상 | Debug USB + Dynamixel Wizard 2.0으로 Clear (`2026-10-09-omy-leap-field-test.md` 부록 A) |
| Wizard Packet 창이 포트를 못 엶 | 메인 창이 `/dev/ttyACM0` 점유 | 메인 창 **Disconnect** 후 Packet 창에서 Open |
| 토크가 안 켜짐 | 알람이 걸린 다이나믹셀은 Torque Enable 거부 | 먼저 Clear |
| Clear 후 원점이 틀어짐 | 홈이 아닌 자세에서 Clear | 6축을 홈 슬릿에 맞춘 뒤 ID 1~6에 다시 Clear, ±1° 확인 |
| 팔은 움직이는데 LEAP 무반응 | `omy_ai`가 `RMW_IMPLEMENTATION`, `ROS_DOMAIN_ID` 없이 실행되어 zenoh 미연결 | 2-2의 export 후 `omy_ai` 재실행 |
| `zenohd: command not found` | 컨테이너 `.bashrc` 미로드 | `ros2 run rmw_zenoh_cpp rmw_zenohd` |
| SSH `banner exchange` 타임아웃 | USB 랜 허브 | 허브 교체 |
| leader 로그 `BULK_READ_FAIL` 반복 | leader 버스 간헐적 통신 실패 | 허용 안이라 계속 동작. 원인 미조사 |
| 텔레옵 중 leader가 튐 | 미확인 | leader를 손으로 잡는다 |
| 엄지가 잘 안 닫힘 | 엄지 뒷부분 받침 기구 없음 | 하드웨어 미해결 |

**Factory Reset은 하지 않는다** (ID, 통신 속도, Homing Offset 등 OMY 설정이 초기화된다).

## 7. 아직 모르는 것
- LEAP을 단 채로 pack/unpack이 안전한가 (손 충돌, 하중)
- LEAP 하중이 OMY 허용 하중 안인가 (사양 확인 필요)
- leader가 튀는 원인과 `BULK_READ_FAIL`의 관계
- Robot PC 종료 절차 (문서에 없음)
- 최초 포장 해제 절차 (ROBOTIS Setup Guide에서 확인)

## 출처
- Setup Guide: https://docs.robotis.com/docs/systems/omy/quick_start_guide/setup_guide
- Teleoperation: https://docs.robotis.com/docs/systems/omy/quick_start_guide/operation_guide/teleoperation
- Zenoh Communication: https://docs.robotis.com/docs/systems/omy/quick_start_guide/zenoh_communication
- 소스: `third_party/open_manipulator/open_manipulator_bringup/launch/{omy_ai,omy_3m_pack,omy_3m_unpack,omy_3m}.launch.py`, `config/{omy_f3m_follower_ai,omy_3m}/*positions.yaml`, `docker/s6-services/`
- 10/09 기록: `docs/field-test/2026-10-09-omy-leap-field-test.md`, `2026-10-09-results.md`
