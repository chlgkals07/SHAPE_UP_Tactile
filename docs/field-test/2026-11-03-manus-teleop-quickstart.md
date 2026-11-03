# 11/03 Manus 텔레옵 시험: 단축 함수로 하는 순서

`user_pc/README.md`의 최종 절차를 **단축 함수(`scripts/leap_aliases.sh`)로 줄여서** 적은 현장용 요약이다. 이유와 세부는 README를 본다.
전제: 1단계(LEAP 영점·관절 시험)와 2단계(팔 + leader 트리거로 LEAP 열고 닫기)는 10/09에 검증했다. 오늘은 **Manus를 붙이고, 팔과 합치고, Cyclo에 기록**하는 것이 목표다.

## 1. 단계별로 무엇이 켜져 있어야 하나

| 단계 | 하는 일 | Robot PC (`zenohd`, `omy_ai`) | Manus 노드 | LEAP 5V | zenoh 환경 |
|---|---|---|---|---|---|
| 2 | leader 트리거 → LEAP (검증 끝, 환경 확인용) | **필요** | 불필요 | 필요 | 필요 |
| 3 | Manus → LEAP, **팔 없음** | **불필요** | 필요 | 필요 (dry-run은 불필요) | **끈다** (`LEAP_NO_ZENOH=1`) |
| 4 | Manus + 팔 | 필요 | 필요 | 필요 | 끈다 (아래 참고) |
| 5 | Cyclo 기록 | 필요 | 필요 | 필요 | **켠다** |

- `--source manus`는 `/manus_glove_*` 토픽만 구독한다. 팔 토픽은 읽지 않으므로 3, 4단계의 `leap_teleop`은 팔과 무관하다. 팔과 손은 서로 독립 프로세스다.
- **같은 RMW 규칙**: Manus 노드와 `leap_teleop`은 같은 RMW를 써야 서로 토픽이 보인다. 3, 4단계는 둘 다 기본 RMW(zenoh 끔), 5단계는 둘 다 zenoh(켬)로 맞춘다. 한쪽만 zenoh면 `[teleop] waiting`에서 안 바뀐다.
- 5단계가 zenoh를 쓰는 이유는 `/leap/*`를 Cyclo(컨테이너)가 받아야 하기 때문이다.
- Manus 노드와 LEAP이 **다른 PC**면 두 PC가 같은 토픽을 볼 수 있어야 한다. 같은 PC에서 돌리는 것이 가장 단순하다.

## 2. 처음 한 번

```bash
# 단축 함수 (~/.bashrc 끝에 넣으면 새 셸마다 자동)
source <repo>/user_pc/scripts/leap_aliases.sh
export LEAP_ROS_DISTRO=jazzy            # Manus PC가 Ubuntu 22.04면 humble
export OMY_ROBOT_IP=10.42.0.241         # ROBOT PC IP
export LEAP_MANUS_WS="<repo>/third_party/manus/ROS2 package"

# Manus 노드 빌드 (Manus PC에서 한 번)
source /opt/ros/$LEAP_ROS_DISTRO/setup.bash
cd "$LEAP_MANUS_WS" && colcon build
```
- 동글용 udev 규칙(`third_party/manus/70-manus-hid.rules`)을 `/etc/udev/rules.d/`에 넣고 다시 꽂는다.
- 노드가 "SDK license" 에러를 내면 라이선스에 해당 기능이 없는 것이다.

## 3. 3단계: Manus 단독 (팔 없음)

**셸 두 개**를 연다. 둘 다 `LEAP_NO_ZENOH=1`.

**셸 1: Manus 노드** (글러브 착용)
```bash
export LEAP_NO_ZENOH=1
leap_env                                  # ROS + manus_ros2_msgs를 source
ros2 run manus_ros2 manus_data_publisher
```

**셸 2: 확인과 캘리브레이션**
```bash
export LEAP_NO_ZENOH=1
leap_env
ros2 topic list | grep -i manus           # /manus_glove_0 (또는 _1)
ros2 topic echo /manus_glove_0 --once > ~/echo.txt
```
`echo.txt`에서 세 가지를 확인한다.
- 손목 raw node가 `chain_type=Hand`, `joint_type=Invalid`인가
- 엄지에 `joint_type=DIP` 노드가 있는가
- ergonomics 값이 도(°) 단위인가 (`ThumbSpread`, `ThumbCMCStretch`, `IndexSpread` … 20개)

토픽이 `/manus_glove_0`이 아니면 `user_pc/config/manus_leap.yaml`의 `topic`을 바꾼다. 왼손이면 `--glove-side Left`.

```bash
leap_glovecal --force                     # 편 손 Enter → 주먹 Enter
```
마지막 줄 `fist thumb, mm in front of palm`의 두 값 부호가 다르면 WARNING이다. `manus_leap.yaml`의 `thumb_ik.flip_normal`을 `true`로 바꾸고 다시 한다.

```bash
leap_manus --dry-run                      # LEAP을 건드리지 않고 로그만
```
- `[teleop] live`가 되고, 손을 움직일 때 값이 바뀌어야 한다.
- `--thumb ik`인데 로그가 `affine`으로 떨어지면 키포인트를 못 찾은 것이다 (위 손목·엄지 DIP 확인).

**LEAP 실물** (5V를 **편 손으로** 켠다. 5V 차단 수단을 손 닿는 곳에 둔다)
```bash
leap_check                                # ID 0~15 오류 0
leap_manus --thumb affine                 # 편 손, 주먹, 손가락 하나씩, 엄지 순서로 천천히
leap_manus                                # 대응이 맞으면 엄지 IK. 엄지–검지 pinch 시험
```
- 손가락이 반대로 움직이면 `manus_leap.yaml`의 `side_gain` 또는 `joint_map`을 조정한다.
- 엄지가 이상하면 `--thumb affine`으로 돌아가 대응표부터 맞춘다.
- 글러브를 벗거나 노드를 끄면 `hold`(0.5초) → `release`(3초)로 안전 자세로 가는지 일부러 확인한다.
- 값이 0.5초 넘게 완전히 같으면 끊김으로 본다 (SDK 노드가 120 Hz로 마지막 값을 반복하기 때문).

**통과**: 손가락 5개가 글러브를 따라가고, 엄지가 대응되며, 끊으면 안전 자세로 간다.

## 4. 4단계: Manus + 팔

1. Robot PC에서 `zenohd`(터미널 A), `omy_ai`(터미널 B)를 띄운다 (명령은 `user_pc/README.md` 2단계). **손은 주먹으로 대기**시킨 상태에서 켠다.
2. User PC에서 Manus 노드(셸 1)는 그대로 두고:
   ```bash
   export LEAP_NO_ZENOH=1
   leap_manus
   ```
3. 팔은 leader를 손으로 잡고 움직이고, 손은 글러브로 움직인다. 이때 leader 트리거는 LEAP에 영향이 없다 (`--source manus`이므로).
4. **통과**: 팔을 움직이는 동안에도 손이 글러브를 따라간다. 가능하면 물체를 하나 집어 본다.

## 5. 5단계: Cyclo 기록

Cyclo가 `/leap/*`를 받아야 하므로 **zenoh를 켠다.** Manus 노드도 같은 환경으로 다시 띄운다.

```bash
# 셸 1 (Manus 노드): LEAP_NO_ZENOH를 풀고 다시 시작
unset LEAP_NO_ZENOH
leap_env && ros2 run manus_ros2 manus_data_publisher

# 셸 2
unset LEAP_NO_ZENOH
leap_record                               # leap_manus --publish
leap_topics                               # /leap/joint_command, /leap/joint_states, /leap/human_*, /leap/teleop_mode
ros2 topic hz /leap/joint_command /leap/joint_states     # 50 Hz 근처
```
그다음 카메라, Cyclo 설정, 녹화는 `docs/data_preparation/omy_leap_cyclo_recording.md`의 E2~E6을 따른다.

## 6. 종료

`leap_*`를 실행한 셸에서 `Ctrl+C` (Torque OFF 후 종료) → 4, 5단계라면 Robot PC `omy_ai` `Ctrl+C` (팔 받치기) → `zenohd` → Manus 노드 → LEAP 5V OFF.

## 7. 막히면

| 증상 | 확인 |
|---|---|
| `No module named 'manus_ros2_msgs'` | `LEAP_MANUS_WS`를 export했나. 빌드했나 (`colcon build`) |
| `[teleop] waiting`에서 안 바뀜 (Manus) | ① 노드가 도는가, `ros2 topic echo`로 값이 오는가 ② 토픽 이름 ③ 두 셸의 RMW가 같은가 (`echo $RMW_IMPLEMENTATION`) ④ 글러브가 멈춘 값만 반복 중이 아닌가 ⑤ ergonomics 이름 20개가 다 있는가 |
| 엄지가 이상함 / 로그에 `affine` | 손목 `Invalid`, 엄지 `DIP` 노드 이름 확인. `KEYPOINT_NODES`는 `sources/manus.py` |
| 손가락 방향 반대 | `side_gain` 또는 `joint_map` (`manus_leap.yaml`) |
| `No module named rclpy` | `PYTHONPATH`가 ROS 경로를 덮어쓴 것. `leap_env`를 거쳤는지 |
| `ros2 topic list`가 비어 있음 (5단계) | `ROBOT_IP`, 포트 7447, `zenohd` 실행 여부 |
| `Missing or unresponsive DYNAMIXEL IDs` | 5V, USB, Dynamixel Wizard가 포트를 점유 중인지 |

## 8. 안전 (매 단계)

- LEAP 5V를 즉시 끊을 수 있어야 한다. **5V는 항상 손을 편 상태에서 켠다.**
- 처음 구동은 항상 `--dry-run` 먼저, 그다음 `--thumb affine`.
- 팔이 움직이는 동안 손은 주먹(`--safe-pose fist`, 함수의 기본값).
- 팔 텔레옵 중에는 leader를 손으로 잡는다.
- 이상하면 **5V를 먼저 끊고** `Ctrl+C`.
