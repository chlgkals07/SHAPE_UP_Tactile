# Manus 글러브 → LEAP Hand 리타게팅 설계

- 작성일: 2026-10-27
- 상태: 초안 (논의 반영본)
- 범위: Manus Pro Haptic 글러브로 LEAP Hand v1의 16관절을 직접 조종한다. 팔은 기존대로 OMY leader가 움직인다.
- 이전 단계: [`2026-10-08-leap-omy-teleop-design.md`](2026-10-08-leap-omy-teleop-design.md), [10/09 결과](../../field-test/2026-10-09-results.md)

## 1. 목표와 비목표

**목표**
1. Manus 글러브의 손가락 관절각을 받아 LEAP Hand 16관절로 실시간 매핑한다.
2. 사용자별 캘리브레이션으로 손 크기·가동범위 차이를 흡수한다.
3. 입력은 **사람 손 표현**으로 두고, 로봇 손 고유 계산은 retargeter에만 둔다. 나중에 ROBOTIS 손을 붙일 때 retargeter 설정과 driver만 추가한다.
4. 구현은 단계마다 수식과 동작을 설명하며 진행한다 (리타게팅 원리를 이해하는 것도 목표).

**비목표 (이번 단계)**
- 손끝 IK / 최적화 리타게팅 (엄지 IK, `dex-retargeting`) — 7절 판단 기준에 따라 다음 단계
- leader 그리퍼 모터 제거 — 8절, 리타게팅 다음 단계
- Meta Quest로 팔 제어 — 보류 (OMY 팔 제어까지 바뀌는 큰 작업)
- 햅틱 피드백 (LEAP 전류/촉각 → 글러브 진동) — 보류. 촉각 연구와 연결되는 후보
- ROBOTIS 손 지원 코드 — 구조만 열어 두고 만들지 않는다

## 2. 확인된 사실 / 미확인

| 사실 | 근거 |
|---|---|
| `Reading`은 scalar `grasp` 또는 LEAP 16관절 `hand` 중 하나를 싣는다 | `user_pc/src/leap_teleop/types.py` |
| 루프는 source → retarget → StaleGuard → driver이고 retargeter는 `Reading -> ndarray(16)` 함수다 | `app.py`, `types.py` |
| LEAP 관절 순서: 검지·중지·약지·엄지 × 4 (손가락은 `mcp_side, mcp_flex, pip, dip`, 엄지는 `cmc_side, cmc_flex, mcp, ip`) | `hand/joints.py` |
| follower `arm_controller`는 `allow_partial_joints_goal: true` | `omy_f3m_follower_ai/hardware_controller_manager.yaml` |

**미확인 (0단계에서 확인)**
- Linux SDK Integrated 모드로 Pro Haptic이 동작하는지, 라이선스 동글만 꽂으면 되는지
- SDK에 포함된 ROS 2 노드의 유무와 메시지 형식
- ergonomics 데이터: 손가락당 4값 × 5손가락 = 20값, 단위 도(°)로 **추정**. 엄지는 `CMCSpread, CMCStretch, MCPStretch, IPStretch`(이름은 SDK 문서로 확인)
- 스켈레톤 노드 위치(손끝 키포인트) 제공 여부와 좌표계
- 갱신 주기와 지연
- Linux에서 햅틱 출력 가능 여부

## 3. 아키텍처

```
[User PC, Ubuntu 24.04 + ROS 2 Jazzy]
 Manus 동글 ─► Manus SDK (Integrated) ─► ManusSource ──Reading(human=…)──┐
                                                                         ▼
                                      ManusLeapRetargeter (관절별 affine, clip, filter)
                                                                         ▼
                                      StaleGuard (기존) ─► LEAP v1 driver (기존)

[Robot PC] leader 팔 ─► follower 팔 (기존 omy_ai, 그대로)
```

### 바뀌는 것
| 위치 | 변경 |
|---|---|
| `types.py` | `Reading`에 `human: np.ndarray | None` 추가 (Manus ergonomics 20값, 순서는 `sources/manus.py`의 상수). 셋 중 정확히 하나 |
| `sources/manus.py` | 새 파일. SDK(또는 ROS 2 토픽)에서 최신 값을 받아 `Reading(human=…)` 반환 |
| `retarget/joint_map.py` | 새 파일. 4절 수식 |
| `tools/calibrate_manus.py` | 새 파일. 5절 절차로 W, b를 구해 yaml로 저장 |
| `cli.py` | `--source manus` 추가 |
| `config/manus_leap.yaml` | 캘리브레이션 결과 (사용자별, gitignore) |

나머지(StaleGuard, driver, 안전범위)는 그대로 쓴다.

## 4. 리타게팅 방식 (관절각 직접 매핑)

입력 h ∈ ℝ²⁰ (사람 관절각), 출력 q ∈ ℝ¹⁶ (LEAP 관절각, 0 = 편 손).

### 4-1. 관절별 affine 매핑 (이번 단계)
LEAP 관절 i를 대응하는 사람 관절 j 하나로 만든다.

    q_i = g_i · (h_j − h_j,open) + q_i,open

- `h_j,open`: 사람이 손을 폈을 때 값, `g_i`: 사람 가동범위(ROM) → LEAP 가동범위 비율
- 새끼손가락 4값은 쓰지 않는다
- 장점: 한 관절이 이상하면 그 줄만 보면 된다. 단점: 엄지는 회전축·위치가 달라 1:1이 맞지 않는다 (pinch 실패 예상)
- 관행: 엄지 외 손가락은 이 방식이 실제로 쓰인다 ([2609.06009](https://arxiv.org/pdf/2609.06009))

### 4-3. 후처리
1. **관절 한계 clip**: 기존 안전범위를 그대로 쓴다.
2. **굽힘–측면 결합 제한**: `mcp_flex`가 클수록 `mcp_side` 허용 폭을 줄인다 (손가락 충돌 방지).
3. **One-Euro 필터**: 느릴 때는 떨림 제거, 빠를 때는 지연 최소. 파라미터 2개(`min_cutoff`, `beta`)를 yaml에서 조정한다.
4. **속도 제한**: 틱당 최대 변화량.

### 4-4. 다음 후보 (구현하지 않음)
- **엄지만 손끝 IK**: 엄지 4관절만 LEAP URDF FK로 손끝 위치를 사람 엄지 끝(스켈레톤, 손 크기 스케일)에 맞추고 opposition 항을 더한다. 이전 해에서 시작. 나머지 손가락은 4-1 그대로 ([2609.06009](https://arxiv.org/pdf/2609.06009)).
- **전체 최적화**: `dex-retargeting` DexPilot / keyvector 방식. 같은 `human` 입력에 키포인트만 더하면 된다.
- 혼합 행렬(`q = W·h + b`, 최소제곱)은 검토 후 제외: 엄지 문제는 기구학 차이라 선형으로 풀리지 않고, 캘리브레이션 자세 수 대비 파라미터가 많다. LEAP 텔레옵 관행에도 없다.

## 5. 캘리브레이션 절차

`tools/calibrate_manus.py`가 안내하고, 자세마다 1초씩 평균을 낸다.

1. **가동범위(ROM)**: 손가락을 하나씩 끝까지 굽혔다 펴고, 벌렸다 모은다 → 관절마다 사람 min/max
2. **편 손**: h_open 기록 (LEAP `open`에 대응)
3. g_i = (LEAP 관절 범위) / (사람 ROM). LEAP 범위는 `open`~`fist`(`postures.yaml`)를 쓴다.

- 결과는 `config/manus_leap.yaml`에 저장한다. 사람 h_open, ROM, 관절 대응표, 필터 파라미터를 담는다.

## 6. 안전
- 기존 StaleGuard 그대로: 글러브 데이터가 끊기면 hold → release(`--safe-pose`).
- 글러브 미착용·추적 손실 상태를 SDK가 알려 주면 Reading을 내지 않는다 (=stale).
- 첫 실물 구동은 속도 제한을 낮춘 값으로 한다.

## 7. 시험과 판단 기준

**하드웨어 없이** (pytest)
- `joint_map`: open → LEAP open, ROM 끝 → LEAP fist, 새끼손가락 무시
- clip·결합 제한·속도 제한, One-Euro 필터 (정지 입력에서 출력 고정)
- `ManusSource`: SDK 호출부를 가짜로 바꿔 Reading 변환과 stale 처리
- `--dry-run --source manus` (녹화한 글러브 데이터 재생)

**실물**
1. 0단계: 글러브 데이터만 출력 — 손가락마다 값이 맞는 방향으로 변하는지
2. LEAP 단독: 편 손·주먹·벌리기가 따라오는지, 떨림·지연 체감
3. **pinch 시험**: 엄지 끝을 검지·중지·약지 끝에 각각 붙이기, 펜과 작은 블록 집기

**판단**
| pinch 결과 | 다음 |
|---|---|
| 통과 | 이 방식으로 확정, leader 작업(8절)으로 |
| 엄지만 실패 | 4-4 엄지 손끝 IK 추가 |
| 전반적 실패 | `dex-retargeting` 도입 |

## 8. 다음 단계: leader 그리퍼 모터 제거 (별도 spec)
조작자 손이 트리거를 놓고 Manus로 손가락을 쓰므로, leader 끝단 손잡이·모터를 떼고 손목 마운트로 바꾼다.

| 할 일 | 근거 |
|---|---|
| leader xacro를 6관절로 (ID 7 제거) | `omy_l100_current.ros2_control.xacro`가 ID 1~7을 선언 — 그대로 떼면 bringup 실패로 **추정** |
| `spring_actuator_controller` 제거, broadcaster에서 `rh_r1_joint` 제거 | `omy_l100_leader_ai/hardware_controller_manager.yaml` |
| 중력보상 재조정 (URDF link6/7 질량 또는 `torque_scaling_factors`) | link6 질량 약 109g에 손잡이·모터가 포함 |
| follower는 6관절 명령을 받는다 | `allow_partial_joints_goal: true` |
| 손목 마운트는 즉시 빼낼 수 있는 구조로 | 10/09 leader 급격한 튐 미해결 |

서브모듈은 수정하지 않고, 바꾼 xacro·yaml은 별도로 둔다 (이전 spec 3절 방식).

## 9. 단계 요약
| 단계 | 내용 | 완료 기준 |
|---|---|---|
| 0 | Linux Manus SDK bring-up, 2절 미확인 항목 확인 | 글러브 값 출력, 이 문서 2절 갱신 |
| 1 | `Reading.human`, `ManusSource`, 4-1 매핑, dry-run | pytest 통과, 녹화 데이터 dry-run |
| 2 | 캘리브레이션 도구 + 4-3 후처리 | pytest 통과 |
| 3 | 실물 시험 (7절) | 결과 문서 (10/09와 같은 형식) |
| 4 | 판단 기준에 따라 엄지 IK / dex-retargeting / leader 작업 | — |
