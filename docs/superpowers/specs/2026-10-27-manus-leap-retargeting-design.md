# Manus 글러브 → LEAP Hand 리타게팅 설계

- 작성일: 2026-10-27
- 상태: 확정 (2026-10-28, 구현 계획 승인)
- 범위: Manus Pro Haptic 글러브로 LEAP Hand v1의 16관절을 직접 조종한다. 팔은 기존대로 OMY leader가 움직인다.
- 이전 단계: [`2026-10-08-leap-omy-teleop-design.md`](2026-10-08-leap-omy-teleop-design.md), [10/09 결과](../../field-test/2026-10-09-results.md)

## 1. 목표와 비목표

**목표**
1. Manus 글러브의 손가락 관절각을 받아 LEAP Hand 16관절로 실시간 매핑한다.
2. 사용자별 캘리브레이션으로 손 크기·가동범위 차이를 흡수한다.
3. 입력은 **사람 손 표현**으로 두고, 로봇 손 고유 계산은 retargeter에만 둔다. 나중에 ROBOTIS 손을 붙일 때 retargeter 설정과 driver만 추가한다.
4. 구현은 단계마다 수식과 동작을 설명하며 진행한다 (리타게팅 원리를 이해하는 것도 목표).

**비목표 (이번 단계)**
- pinch snap, `dex-retargeting` — 7절 판단 기준에 따라 다음 단계
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
                                      ManusLeapRetargeter (손가락 affine, 엄지 affine|IK, filter)
                                                                         ▼
                                      StaleGuard (기존) ─► LEAP v1 driver (기존)

[Robot PC] leader 팔 ─► follower 팔 (기존 omy_ai, 그대로)
```

### 바뀌는 것
구현 계획: [`2026-10-28-manus-leap-retargeting.md`](../plans/2026-10-28-manus-leap-retargeting.md), 설계 근거: [`2026-10-28-manus-leap-thumb-ik-rationale.md`](2026-10-28-manus-leap-thumb-ik-rationale.md)

| 위치 | 변경 |
|---|---|
| `types.py` | `HumanHand`(Manus 관절각 20 + 키포인트 7) 추가, `Reading`은 grasp / hand / human 중 정확히 하나 |
| `sources/manus.py` | 새 파일. ROS 2 토픽 구독 → `Reading(human=…)` |
| `retarget/manus_leap.py` | 새 파일. 손가락 affine + 엄지 affine/IK + 결합 제한 + One-Euro |
| `kinematics.py` | 새 파일. URDF 파서, FK, LM 최소제곱 |
| `filters.py` | One-Euro 필터 (leap-hand에서 이식) |
| `tools/calibrate_manus.py` | 새 파일. 편 손/주먹 기록, 스케일 계산 |
| `cli.py` | `--source manus`, `--manus-config`, `--thumb {ik,affine}` |
| `assets/leap_hand_right.urdf` | dex-urdf(MIT)에서 복사 |
| `config/manus_leap.yaml` | 대응표·가중치·필터 (추적, 공통) |
| `config/manus_calibration.yaml` | 편 손/주먹/스케일 (사용자별, gitignore). 예시는 `.example.yaml`, dry-run 전용 |

나머지(StaleGuard, driver의 clip·속도 제한)는 그대로 쓴다.

## 4. 리타게팅 방식

입력 h ∈ ℝ²⁰ (사람 관절각), 키포인트 7개. 출력 q ∈ ℝ¹⁶ (LEAP 관절각, 0 = 편 손).

### 4-1. 손가락: 관절별 affine
- 굽힘: `q = clip((h − h_open) / (h_closed − h_open), 0, 1) × q_fist` (span이 10° 미만이면 같은 손가락의 중앙 비율을 빌린다)
- 측면: `q = side_gain × (h − h_open)`
- 새끼손가락 4값은 쓰지 않는다. 예전 leap-hand 방식과 같다.

### 4-2. 엄지: affine과 IK 둘 다, `--thumb`로 선택 (기본 IK)
- **affine**: 엄지 4값을 12~15번에 편 손~주먹 비율로. 대응은 BiDex 예제를 따라 12←ThumbMCPStretch, 13←ThumbMCPSpread, 14←ThumbPIPStretch, 15←ThumbDIPStretch (Manus 엄지 이름은 한 마디씩 밀려 있다). 12번 주먹 목표는 `fist_override_deg`(실측 전 0). IK의 prior, 키포인트가 없을 때의 fallback, IK 재시작점.
- **IK**:

      min ‖tip(q) − tip*‖² + λip‖ip(q) − ip*‖² + λp‖q − q_aff‖² + λs‖q − q_prev‖²

  - `tip*`, `ip*` = `c_L + s·R·(사람 점 − 사람 엄지 CMC)`: 사람 엄지 끝과 IP 관절을 LEAP 손바닥 좌표계로 (R은 매 샘플 손바닥 키포인트로)
  - **BiDex 방식**: 끝만 맞추면 자세가 9~44° 어긋나고 IP를 더하면 3° 이내 (설계 근거 7절)
  - LM, 이전 해에서 시작, 관절 한계 안에서, 틱당 최대 10회. 입력이 0.5 s 넘게 끊기거나 키포인트가 빠지면 affine 엄지에서 다시 시작
  - 기본 λip = 0.3, λp = 0.01, λs = 0.05. 위치 잔차 cm, 관절 rad — 실물 조정
- 근거와 장단점은 설계 근거 문서 참고.

### 4-3. 후처리
1. **굽힘–측면 결합 제한**: `|side| ≤ side_max × (1 − clip(mcp_flex / mcp_flex_max, 0, 1)) + side_floor`
2. **URDF 영점 offset**: 실측 open과 URDF 0의 차이 (기본 0)
3. **One-Euro 필터**
4. 관절 한계 clip과 속도 제한은 driver(`command_degrees`)가 이미 한다.

### 4-4. 보류
- pinch snap: IK 단독 pinch 시험에서 틈이 남으면 추가
- dex-retargeting: ROBOTIS 손 단계에서 재검토
- 혼합 행렬: 제외 (설계 근거 문서 6절)

## 5. 캘리브레이션 절차

`tools/calibrate_manus.py`가 안내하고, 자세마다 1.5 s 중앙값을 쓴다.

1. **편 손** (`OPEN`): h_open, 스케일 `s = |LEAP 검지 MCP→끝| / |사람 index_mcp→index_tip|`
2. **주먹** (`FIST`): h_closed
3. 확인 출력: 주먹에서 엄지가 손바닥 앞(+)/뒤(−) 몇 mm인지, 글러브 목표와 LEAP 주먹 자세를 비교. 부호가 다르면 거울상 → `thumb_ik.flip_normal`. (편 손에서는 엄지가 손바닥 평면 안이라 거울상이 안 보인다.)

- 결과는 `config/manus_calibration.yaml`(사용자별, gitignore)에 저장한다. 조정 값은 `config/manus_leap.yaml`(추적).

## 6. 안전
- 기존 StaleGuard 그대로: 글러브 데이터가 끊기면 hold → release(`--safe-pose`).
- 글러브 미착용·추적 손실 상태를 SDK가 알려 주면 Reading을 내지 않는다 (=stale).
- 첫 실물 구동은 속도 제한을 낮춘 값으로 한다.

## 7. 시험과 판단 기준

**하드웨어 없이** (pytest)
- 손가락 affine: open → 0, closed → fist, 새끼손가락 무시, 결합 제한
- kinematics: q=0 FK 값, FK로 만든 목표를 IK가 다시 찾음, 한계 밖 목표
- 엄지 IK: 합성 데이터에서 엄지 끝 오차 < 2 mm, λp가 크면 affine에 붙음, 키포인트 없으면 affine
- `human_from_glove` 변환, One-Euro 필터
- `ros2 bag play` + `--dry-run --source manus` (녹화 데이터)

**실물**
1. 0단계: 글러브 데이터만 출력 — 손가락마다 값이 맞는 방향으로 변하는지
2. LEAP 단독: 편 손·주먹·벌리기가 따라오는지, 떨림·지연 체감
3. **pinch 시험을 `--thumb affine`과 `--thumb ik`로 각각**: 엄지 끝을 검지·중지·약지 끝에 붙이기, 펜과 작은 블록 집기. 문헌에 비교 실험이 없으므로 이것이 우리 비교 실험이다.

**판단**
| pinch 결과 (IK) | 다음 |
|---|---|
| 통과 | 확정, leader 작업(8절)으로 |
| 손끝 틈이 남음 | pinch snap 추가 |
| 손가락까지 부족 | `dex-retargeting` 검토 |

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
| 1 | 구현 계획 Task 1~8 (손가락 affine, 엄지 affine/IK, 결합 제한, 캘리브레이션, CLI) | pytest 통과, 녹화 데이터 dry-run |
| 2 | 실물 시험 (7절) | 결과 문서 (10/09와 같은 형식) |
| 3 | 판단 기준에 따라 pinch snap / dex-retargeting, leader 작업(별도 세션, `OMY_Tactile_Robot_PC`) | — |
