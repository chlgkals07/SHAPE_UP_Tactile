# Manus 글러브 → LEAP Hand 리타게팅 구현 계획

> 상태: 승인됨 (2026-10-28). Spec: [`2026-10-27-manus-leap-retargeting-design.md`](../specs/2026-10-27-manus-leap-retargeting-design.md), 설계 근거: [`2026-10-28-manus-leap-thumb-ik-rationale.md`](../specs/2026-10-28-manus-leap-thumb-ik-rationale.md)

## 구현 중 변경 (2026-10-29)
- 엄지 opposition 항: 논문의 끝–끝 방향 항 → **지문 면 법선 항** (끝–끝 방향은 손끝 위치에만 의존해 자세를 못 고름). 설계 근거 문서 5절.
- 설정 분리: `config/manus_leap.yaml`(추적, 조정 값) + `config/manus_calibration.yaml`(gitignore, 사용자별; 예시 `.example.yaml`). 기존 `hardware_motors` 규칙과 같다.
- 손바닥 정렬 R은 yaml 상수가 아니라 매 샘플 키포인트로 계산, 거울상만 `flip_normal`로. 캘리브레이션 확인은 편 손이 아니라 주먹에서 (편 손은 엄지가 손바닥 평면 안).
- IK 틱당 10회 제한 (도달 불가 목표에서 최대 ~11 ms → ~3 ms).

## Context
OMY leader 그리퍼(scalar 0~1)로 LEAP Hand를 쥐었다 펴는 데까지 검증됨(10/09). 다음은 Manus Pro Haptic 글러브로 16관절을 직접 조종한다. 논의 결과:
- 손가락(검지·중지·약지): **affine** (예전 `shinjju1209/leap-hand@ddfabaa` `neutral_calibration.py` 방식, 편 손/주먹 두 점)
- 엄지: **IK** — LEAP 엄지는 12번(손가락 평행축 회전)·13번(거의 roll)이라 사람 관절과 1:1이 안 된다. 4관절로 3D 위치를 맞추면 해가 여러 개라 opposition(지문 면이 손가락을 향함) + **affine prior** + smoothing 항으로 고른다. 위치만 맞추는 IK는 관절이 떠 버린다는 반대 사례(quest3-dexterous-teleop)를 prior 항이 막는다.
- 문헌에 엄지 affine vs IK 직접 비교가 없으므로 `--thumb affine|ik` 토글을 두고 우리 pinch 시험을 ablation으로 쓴다.
- Manus 데이터는 SDK의 ROS 2 노드 토픽을 구독(`ros2_leader.py`와 같은 패턴). 메시지 형식은 미확인 → Task 0.

확인된 사실 (코드):
- `ANGLE_NAMES` 인덱스 == 모터 ID == URDF 관절 이름 `"0"`~`"15"`; `SIM_MIN/MAX_RADIANS`(`hand/leap_v1.py`) == URDF limit. 우리 각도(도)→라디안이 곧 URDF q (영점은 실측 open, 공칭 π). 그래도 `urdf_offset_deg`·부호 knob은 둔다.
- `LeapHandHardwareController.command_degrees`가 이미 clip + 120°/s slew 제한 → retargeter에서 속도 제한·clip 중복 구현 안 함.
- `Reading`(`types.py`)은 grasp/hand 중 하나. `Retargeter = Callable[[Reading], ndarray]`.

## 산출물 (문서)
1. `docs/superpowers/plans/2026-10-28-manus-leap-retargeting.md` — 이 계획의 레포 사본 (기존 plan 형식)
2. `docs/superpowers/specs/2026-10-28-manus-leap-thumb-ik-rationale.md` — **설계 근거 별도 문서**: 예전 affine 분석(엄지 대응 엇갈림), LEAP 엄지 FK 표, 문헌 근거·반대 사례·ablation 부재, URDF 수치 검증(12번 0° 고정해도 pinch 도달 → 문제는 도달이 아니라 해 선택), 장단점, 결정
3. 기존 spec(`2026-10-27-manus-leap-retargeting-design.md`) 3·4·9절을 이 계획에 맞게 갱신 (혼합 행렬 제거 상태 유지, 엄지 IK를 이번 단계로, 폴더 구조)

## 파일 구조
```
user_pc/
├── assets/leap_hand_right.urdf          # 신규: dex-urdf(MIT)에서 복사, 헤더 주석에 출처·commit
├── config/manus_leap.example.yaml       # 신규(추적): 매핑표, λ, 필터, offset
├── src/leap_teleop/
│   ├── types.py                         # 수정: HumanHand, Reading.human
│   ├── config.py                        # 수정: load_manus_leap()
│   ├── filters.py                       # 신규: OneEuroFilter 이식 (leap-hand@ddfabaa, 로직 그대로)
│   ├── kinematics.py                    # 신규: URDF 파서, FK, 일반 LM 최소제곱
│   ├── retarget/manus_leap.py           # 신규: 손가락 affine + 엄지 affine|ik + 필터
│   ├── sources/manus.py                 # 신규: 순수 변환 함수 + Ros2ManusSource
│   ├── tools/calibrate_manus.py         # 신규: 편 손/주먹 기록 → manus_leap.yaml
│   └── cli.py                           # 수정: --source manus, --manus-config, --thumb
└── tests/  test_types.py(추가), test_kinematics.py, test_manus_leap.py, test_manus_source.py, test_filters.py, test_cli.py(추가)
```
`.gitignore`에 `config/manus_leap.yaml` 추가.

## Tasks

### Task 0 — Manus SDK 확인 (User PC, 사용자 실물)
- Linux SDK Integrated 모드로 글러브 인식, ROS 2 노드 유무, 토픽명·메시지 타입(`ros2 interface show`), ergonomics 이름 20개, raw node(키포인트) 유무·좌표계, 주기. `ros2 bag record`로 편 손/주먹/pinch 녹화.
- 결과를 spec 2절에 기록. **Task 6의 rclpy 부분만 이 결과에 의존**; 나머지 Task는 병행 가능.

### Task 1 — `HumanHand`, `Reading.human` (`types.py`)
- `HUMAN_ANGLE_NAMES`(20, Manus ergonomics 순서: 엄지·검지·중지·약지·새끼 × 4), `KEYPOINT_NAMES = ("wrist","thumb_cmc","thumb_tip","index_mcp","index_tip","middle_mcp","pinky_mcp")`.
- `@dataclass(frozen) HumanHand(angles: ndarray(20,) deg, keypoints: ndarray(7,3) m | None)` — finite·shape 검증.
- `Reading`: grasp / hand / human 중 **정확히 하나**. 기존 테스트 유지 + 신규 케이스.

### Task 2 — `filters.py`
- `one_euro_filter.py` 그대로 이식(첫 줄 vendored 주석). 테스트: 상수 입력 → 상수 출력, 역행 timestamp 거부.

### Task 3 — `kinematics.py` (numpy + `xml.etree`만)
- `load_chain(urdf_path) -> Chain`: joint origin(xyz,rpy)·axis·limit·parent/child 파싱.
- `Chain.link_position(link, q: Mapping[str,float]) -> ndarray(3)` (Rodrigues 회전).
- `least_squares(residual_fn, x0, lo, hi, *, iters=40, damping=2e-2, tol=1e-6)` — 수치 야코비안(전진차분) + LM + clip. 범용 1개 함수.
- 테스트: (a) q=0에서 `index_tip_head`≈(19.5, 45.6, 228.2)mm, `thumb_tip_head`≈(21.9, 174.7, 15.7)mm (탐색 때 계산한 값); (b) 임의 q로 FK한 목표를 IK가 다시 찾음(위치 오차 <1mm); (c) 한계 밖 목표 → 한계 안에서 멈춤.

### Task 4 — `retarget/manus_leap.py`
`ManusLeapRetargeter(cfg, chain, thumb_mode, clock)`의 `__call__(reading) -> ndarray(16) deg`:
1. **손가락 affine** (검지·중지·약지 12관절): flex는 `clip((h−h_open)/(h_closed−h_open),0,1) × fist_target` (span < 10°면 같은 손가락 median ratio 차용 — leap-hand 로직), side는 `side_gain × (h−h_open)`. 매핑표(LEAP 관절 ← Manus 이름)는 yaml.
2. **엄지 affine** `q_aff`: 같은 식, 기본 대응 `12←ThumbCMCSpread, 13←ThumbCMCStretch, 14←ThumbMCPStretch, 15←ThumbIPStretch` (yaml에서 실물로 조정).
3. **엄지 IK** (`thumb_mode == "ik"`이고 keypoints 있을 때; 없으면 `q_aff`로 fallback):
   - 정렬: 사람 palm frame(원점 wrist, 축: wrist→middle_mcp, pinky_mcp→index_mcp, 법선) → `R_align`(yaml 상수, LEAP base 축으로) · 스케일 `s`(캘리브레이션) · 기준점 thumb_cmc ↔ URDF 관절 12 원점.
   - `p* = c_L + s·R·(p_thumb_tip − p_thumb_cmc)`, `n* = R·unit(p_index_tip − p_thumb_tip)`.
   - LEAP 검지 끝 = 1번 결과로 FK(고정).
   - 잔차 `[f(q)−p*, √λo(unit(index_L−f(q))−n*), √λp(q−q_aff), √λs(q−q_prev)]`, 초기값 q_prev, `least_squares` 호출.
   - 기본 λ: λo=0.2, λs=0.05 (2609.06009), λp=0.01 — **위치 잔차는 m 단위라 실물 조정 필요**, yaml.
4. **굽힘–측면 결합 제한** (검지·중지·약지): `|side| ≤ side_max × (1 − clip(mcp_flex / mcp_flex_max, 0, 1)) + side_floor` — 굽힐수록 벌림 허용 폭 축소(주먹 때 이웃 손가락 충돌 방지). `side_max`, `side_floor`(완전히 굽혀도 남길 여유, 기본 5°)는 yaml.
5. 16관절 합치기 → `+urdf_offset_deg`/부호 → OneEuro(`reading.timestamp`) → 반환. clip·slew는 driver가 함.
- 테스트: open 입력 → 0 근처; closed → fist 목표; 주먹 상태에서 큰 side 입력 → side_floor 이내로 제한, 편 손에서는 그대로; 새끼손가락 값 무시; keypoints 없음 → affine fallback; IK: FK로 만든 사람 목표(s=1, R=I 합성 데이터)를 받으면 엄지 끝 오차 <2mm; λp 크게 → q_aff에 붙음; 두 번 호출 시 warm start 연속성.

### Task 5 — `config.py` + `config/manus_leap.example.yaml`
- `ManusLeapConfig` dataclass + `load_manus_leap(path)`: 매핑표, h_open/h_closed(20), fist 목표(기존 `postures.yaml` 재사용 → `load_postures`), side_gain, thumb 대응, R_align(3×3), scale, λo/λp/λs, one_euro(min_cutoff, beta), urdf_offset_deg(16). 누락·shape 오류 → `ValueError` (기존 loader 스타일).

### Task 6 — `sources/manus.py`
- 순수 함수 `human_from_glove(ergonomics: Mapping[str,float], nodes: Mapping[str, xyz] | None) -> HumanHand | None` — 이름 누락·NaN → None. 테스트는 이것만.
- `Ros2ManusSource(topic, side="right")`: `Ros2LeaderSource` 구조 그대로 복사(rclpy는 `__init__` 내부 import, 백그라운드 executor, 안전한 close). 메시지 필드 접근은 Task 0 결과로 확정 — 그 전엔 `manus_ros2_msgs/ManusGlove`(ergonomics[type,value], raw_nodes[pose]) **추정**으로 작성하고 TODO 대신 spec에 미확인 표시.
- `ros2 bag play`로 녹화 데이터 재생 = 하드웨어 없는 dry-run (별도 재생 코드 안 만듦).

### Task 7 — `tools/calibrate_manus.py`
- `calibrate_motors.py` 대화 패턴 재사용: `OPEN` 입력 → 1.5 s median 기록(h_open, scale = |LEAP 검지 mcp→tip| / |사람 index_mcp→index_tip|), `FIST` → h_closed. 예시 yaml을 기반으로 `config/manus_leap.yaml` 저장(`--force` 없으면 덮어쓰기 거부).
- 확인 출력: 편 손에서 IK 엄지 목표와 LEAP q=0 엄지 끝 거리(mm) — 크면 R_align/부호가 틀린 것.
- 순수 계산 부분(median, scale)만 테스트.

### Task 8 — `cli.py`
- `--source manus`, `--manus-config config/manus_leap.yaml`, `--thumb {ik,affine}` (기본 ik). source가 manus면 `ManusLeapRetargeter`, 아니면 기존 `ScalarPostureRetargeter`. `.example.yaml`로 실물 실행 거부(모터 보정과 같은 규칙).
- 테스트: parser 선택지, 예시 파일 거부.

### Task 9 — 문서
- 위 산출물 1~3, `user_pc/README.md`에 "Manus로 구동" 절(Task 0 결과 반영 후 명령 확정), 실물 시험 계획(LEAP 단독 → pinch 시험 affine vs ik 각각 → leader 팔 + Manus).

순서: 9(설계근거·plan 사본 먼저) → 1 → 2 → 3 → 5 → 4 → 6 → 7 → 8 → 9(README). 각 Task 끝에 pytest + 커밋 (`feat/manus-teleop`, push 안 함).

## 재사용
- `sources/ros2_leader.py` 구조 (rclpy 지연 import, executor 스레드, close)
- `config.py` `_load_mapping`, `load_postures`, `make_posture`
- `hand/leap_v1.py` `SIM_MIN/MAX_RADIANS` (IK 한계), driver의 clip·slew
- leap-hand `one_euro_filter.py`, `neutral_calibration.py` 수식(span·fallback)
- `tools/calibrate_motors.py` 대화형 기록 패턴

## 엄지 두 모드 (둘 다 구현, `--thumb`로 선택)
- `affine`: 엄지 4값 → 12~15번 1:1 직선. 대응표는 yaml. IK의 prior이자 fallback(키포인트 없음)으로도 쓰임.
- `ik` (기본): affine 결과에서 출발, 엄지 끝 위치 + opposition(지문 면이 손가락 향함) + affine prior + smoothing 최소화.

## 팔+손 동시 제어
- 이미 분리돼 있음: 팔 = Robot PC `omy_ai`(leader→follower), 손 = User PC `leap-teleop`(USB 직접). `--source manus`로 바꾸는 것뿐, 통합 코드 불필요 (10/09와 같은 2-프로세스 운용).
- **leader 트리거 모터(ID 7) 제거는 별도 세션, `OMY_Tactile_Robot_PC` 레포**: leader는 트리거가 팔과 같은 ros2_control 시스템이라 follower처럼 mock 대체 불가 → 6관절 xacro 복사본, `spring_actuator_controller` 제거, broadcaster에서 `rh_r1_joint` 제거, 중력보상 재조정.
- 나중(데이터 수집): LEAP 명령/상태를 ROS 토픽으로 publish해 팔과 같은 bag에 녹화 — 이번 범위 밖.

## 하지 않는 것 (논의 후 확정)
- pinch snap — IK만으로 pinch 시험 후 손끝 틈이 남으면 추가 (IK 목표 교체 10줄 내외). 오작동(주먹·원통 잡기 때 붙음) 위험 때문에 먼저 IK 단독 성능 확인.
- dex-retargeting — 의존성(pinocchio, nlopt)·numpy 충돌 위험, 손가락 affine 장점 상실. ROBOTIS 손 단계에서 재검토.
- 햅틱, leader 모터 제거(별도 세션), LEAP 상태 ROS publish, ROBOTIS 손 코드.
- 설계 근거 문서에 위 세 항목(결합 제한 포함 이유, snap·dex-retargeting 보류 이유)을 같이 기록.

## Verification
- 이 맥: scratchpad venv(numpy, PyYAML, pytest)로 `PYTHONPATH=src python -m pytest -q` — 기존 96개 + 신규 전부 통과.
- 합성 데이터 스크립트 확인: FK로 만든 사람 손 → retargeter → 엄지 끝 오차·opposition 각도 출력.
- User PC (사용자): Task 0 → `ros2 bag play` + `--dry-run --source manus` → LEAP 단독 실물 → pinch 시험을 `--thumb affine`/`--thumb ik` 각각 (엄지–검지/중지/약지 접촉, 펜·블록 집기) → 결과 문서(10/09 형식).
