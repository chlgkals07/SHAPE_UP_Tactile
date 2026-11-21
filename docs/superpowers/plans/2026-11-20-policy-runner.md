# Policy Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 우리 rig 의 관측 → π0.5 서버 → 22차원 관절 목표 → (dry-run) 명령 추적까지를 한 프로그램으로 잇는다. 첫 이정표는 "실제 π0.5 응답이 dry-run 실행 로그로 남는다"이고, 모터 송신은 이 계획의 범위 밖(D·E 단계)이다.

**Architecture:** 새 패키지 `policy_runner/` 가 `tactile_rec` 의 Hub·Stream·align·features 를 import 해서 관측을 만든다. 스레드는 셋: 기존 Hub reader(수집, 계속), `InferenceWorker`(추론, 필요할 때), `Executor`(실행, 1/fps 간격). 손은 `leap_teleop` 이 USB 를 계속 소유하고 runner 는 localhost UDP 로 16관절 목표만 보낸다(`--source policy`). 서버는 openpi `scripts/serve_policy.py` 를 그대로 쓰고, 로컬/원격은 endpoint 주소만 다르다.

**Tech Stack:** Python 3.12, uv, numpy 2, msgpack, websockets 17 (sync client / asyncio server), PyYAML. 시험은 pytest + `FakeClock` + recorder 의 `ManualRig` 방식.

**Design source:** `docs/policy-deployment-guide.html` (2026-11-20 통합판). 이 계획은 그 문서의 §08~14 를 현재 main(`8c635ae`)과 openpi-RLT(`sehwa118/openpi-RLT` main `70fea7b`)에 대조해 구체화한 것이다.

---

## 0. 확정한 결정 (2026-11-20)

| 결정 | 고른 것 | 대안 | 이유 |
|---|---|---|---|
| 손 경로 | `leap_teleop` 이 USB 소유, runner 는 UDP 로 목표 전송 (`sources/policy_udp.py`) | runner 가 `LeapHandDriver` 직접 소유 | clip·slew·캘리브레이션·Torque OFF·`--record-udp` 피드백을 그대로 쓴다. runner 가 죽어도 `StaleGuard` 가 독립 watchdog 로 남는다 |
| 손 상태 생산자 | 기존 `hand_udp` stream 그대로 (`leap_teleop --record-udp`) | runner 가 버퍼에 직접 주입 | 위 결정의 결과. recorder 쪽 변경 0 |
| openpi client | 쓰지 않는다. wire 코덱(`msgpack_numpy`)만 출처 표기해 옮기고 client 는 직접 작성 | `openpi-client` 패키지 의존 | `openpi-client` 는 `numpy<2.0` 을 요구하고 recorder `uv.lock` 은 numpy 2.2.6 이다. 한 환경에 둘 수 없다. 또 그 client 의 `infer()` 는 timeout 없이 `recv()` 를 무기한 기다린다 |
| 패키지·이름 | `policy_runner`, CLI `policy-runner`, `ObsAligner`/`AlignedObs`, `ActionChunk`, `pred_horizon`(H)/`exec_horizon`(K) | 가이드의 `shape_policy`, `ShapeUpInputs`, `PlanBuffer` | 레포 규칙(`tactile_rec`, `control_hub`)과 openpi 관례(로봇 이름: `AlohaInputs`) |
| openpi 쪽 이름 | `omy_leap_policy.py` 의 `OmyLeapInputs`/`OmyLeapOutputs`, config `pi05_omy_leap` | `ShapeUpInputs`, `pi05_shape_up` | 위와 같음. `rig.name`/`robot_type` 이 `omy_f3m_leap` |
| 실행 방식 | 겹치지 않는 chunk (요청 1개 in-flight, K개 실행 후 다음 요청) | 중첩 추론, RTC | 시간 의미와 장치 연결부터 검증. 대기 구간은 trace 로 측정 |
| 브랜치 | `feat/policy-runner` (main `8c635ae` 에서) | — | |
| 이미지 (2026-11-21) | 실행 중 프레임도 녹화기와 같은 JPEG 왕복(`cv2.imencode` quality = `record.jpeg_quality` → `cv2.imdecode`)을 거친 뒤 `orient_image` | 원본 프레임 그대로 | 학습 이미지는 `.mjpeg` 에서 디코드한 프레임이다. 같은 왕복을 하면 온라인 이미지가 학습 이미지와 bit 단위로 같아진다 |
| 필수 stream (2026-11-21) | config 에 따로 두지 않는다. `dataset.arm_state`, `dataset.hand`, manifest 의 카메라가 필수다 | `observation.required` 목록 | 같은 정보를 두 곳에 두지 않는다 |
| 실행 격자 (2026-11-21) | Executor 는 arm 시각부터 1/fps 격자에서만 돈다. chunk 는 도착 뒤 첫 tick 에 채택한다. 다 쓴 tick 에서 다음 요청 | 도착 즉시 새 격자 | 시각이 단순하다. 대가로 사이클이 `K + ceil(L/dt)` tick 으로 가이드 식보다 최대 1 tick 길다 |
| 코드 규칙 (2026-11-21) | karpathy 식: 작은 순수 함수, 얇은 층, 위에서 아래로 읽힘, 이름으로 설명. **코멘트·docstring 없음**(라이선스 표기만 예외) | 기존 패키지의 docstring 형식 | 사용자 지시 |
| UI (2026-11-21) | runner 가 자기 웹 UI(:8810)를 띄우고 Control Hub 에 "정책" 페이지(iframe)를 녹화 페이지와 같은 방식으로 추가. 내용: 서버 주소·checkpoint·상태·stream age·추론 지연·chunk 나이와 위치·최근 문제·arm/disarm/reset | Hub 안에 직접 구현 | 녹화기와 같은 구조. Hub 는 장치·프로그램을 import 하지 않는다 |
| 손 모드 (2026-11-21) | `execution.mode: dry_run`(trace 만) / `hand`(leap_teleop 으로 UDP). `hand` 는 CLI `--allow-hand` 가 있어야 시작 | 한 모드 | 받는 쪽이 `--dry-run` 인지 runner 는 알 수 없다. 사람이 명시적으로 허용해야 한다 |
| 동일성 판정 (2026-11-21) | `latency_ms` 가 있으면 offline 이 고른 프레임이 그 시각까지 도착했을 때만 bit 일치를 요구하고, 아니면 도착한 마지막 프레임과 비교 | 무조건 bit 일치 | offline 은 격자 뒤에 도착한 프레임을 쓸 수 있고 온라인은 못 쓴다. 고정 테스트를 `0060e86` 에서 고쳤다 |
| 실행 격자 기준 (2026-11-21) | chunk 시작과 행 번호는 ticker 의 예정 격자 시각, 늦음은 실제 시각으로 잰다 (`tick(now, grid)`) | 실제 깬 시각 기준 | 실측 trace 에서 두 행이 23.318 ms 간격으로 나갔다 (`9b73f4a`) |
| 의도적 버그 방식 (2026-11-21) | `audit/mutants.py` 의 문자열 치환 표 (정확히 한 번 일치, 항상 복원) | `.patch` 파일 | 패치가 엉뚱한 곳에 적용될 일이 없고 한 파일로 읽힌다 |
| 동작 검사 삭제 (2026-11-21) | 실행기는 chunk 를 동작 기준(첫 행–측정 상태 `first_row_max_rad`, 행 사이 `step_max_rad`)으로 거부하지 않는다. 관절 범위·속도 제한은 장치 제어기(LEAP 드라이버 clip·slew)가 맡는다. 남긴 검사: 형식(NaN·모양·manifest), 오래된 chunk, 관측 나이·어긋남, 늦은 행 건너뛰기 | 데이터 기반 그룹별 한도로 유지, 기록만 하는 모드 | 사용자 결정. 0.15 / 0.05 는 데이터에서 정한 값이 아니었고 11/17 시연이 자주 넘었다(손 sent−pos p99 0.18 rad, 10행 창 손 23–44 % / 팔 10–17 % 가 0.05 초과). openpi 예제 클라이언트도 하지 않는다. 감사기 규칙 2개, 테스트 2개, M11 을 함께 지웠다 |
| 실패 한도 (2026-11-21) | `policy.max_failures`(3) 연속 실패, `observation.fail_after_ms`(1000) 관측 실패 지속이면 FAULT. 시작 때 warm-up 1회(`policy.warmup_timeout_s` 60) | 무한 재시도 | §4 상태 기계. 고정 테스트 설정에 없는 키라 코드 기본값으로 읽는다 |
| websockets (2026-11-21) | `websockets>=17.1`, `connect(..., legacy=True)`, Python ≥ 3.11 | context manager 연결 | 연결을 오래 유지한다. 17.1 부터 직접 연결은 `legacy=True` 가 필요하다 (설치된 17.4 소스에서 확인) |

## 1. 현재 코드에서 확인한 사실 (이 계획의 전제)

- `Stream.recent(since_ns)` / `latest()` 는 lock 아래 버퍼(기본 2 s)를 돌려준다. `Stream.push(..., t_recv_ns=...)` 로 기록 시각을 그대로 넣을 수 있다 → 재생과 시험에 쓴다.
- `align.pick_latest`, `staleness_s`, `stream_times(mode=recv|src|respread)` 는 순수 numpy.
- `features.joint_vector`(arm rad + hand deg→rad, float32), `joint_names`, `orient_image`(회전 + BGR→RGB) 가 단위·순서·회전의 유일한 지점이다. 키 `observation.state`, `action`, `observation.images.<cam>` 은 openpi Agilex config 의 repack 키와 같은 형식이다.
- `convert/episode.py`: state 의 손은 `pos` 가 유한한 샘플만, action 은 `arm_action.pos`(leader) + `hand.<hand_action>`(현재 `sent`).
- `rig.example.yaml` (main): `arm_state` 400 Hz, `arm_action` 300 Hz(header stamp 없음 → recv), `hand` 50 Hz `src`(같은 PC mono), `tactile_a` 하나 `respread`, `cam_wrist` 30 Hz, `cam_ext` 주석 처리, `dataset.fps: 30`.
- **baseline 입력에는 온라인에서 못 쓰는 시간 모드가 없다.** 카메라·팔은 `recv`, 손은 `src`(mono, causal). `respread` 는 tactile 에만 쓰이고 tactile 은 baseline 입력이 아니다.
- `leap_teleop`: `Source.poll()` → retarget → `StaleGuard.resolve()` → `driver.command()` → `publisher.publish()`(record UDP). `Reading(hand=16 deg)` 는 이미 있다. 지금 retargeter 는 grasp(`ScalarPostureRetargeter`)·human(`ManusLeapRetargeter`)만 받는다. `StaleGuard` 는 0.5 s 뒤 hold, 3 s 뒤 safe pose(`--safe-pose`)로 release.
- openpi-RLT main `70fea7b`: 서버는 연결 직후 metadata 를 보내고, 이후 bytes 요청마다 bytes 응답, 예외면 traceback 문자열을 보낸다. `GET /healthz` → 200. `serve_policy.py` 기본 port 8000. `--env ALOHA` 기본 policy 는 `pi05_aloha` + `gs://openpi-assets/checkpoints/pi05_base`.
- openpi-RLT pi05 Agilex config: `action_dim=32`(padding), `action_horizon=50`, 이미지 slot `base_0_rgb`/`left_wrist_0_rgb`/`right_wrist_0_rgb`. 없는 카메라는 droid 처럼 0 이미지 + mask False.
- `TRLT`, `TRLT-3DTacDex` 브랜치는 serving·client·policies 를 건드리지 않는다(촉각 RL token 오프라인 실험). baseline 배포는 main 경로로 충분하다.
- `vla-docker-rtxpro6000` 은 upstream openpi `215abfb` 를 설치한다. openpi-RLT `70fea7b` 와 같은 코드인지 확인하지 않았다 (UNVERIFIED). 서버를 어느 쪽으로 띄울지 C 단계 전에 하나로 정한다.
- `data/samples/2026-11-17/` 의 `.npz` 는 git LFS 다. 이 Mac 에는 `git lfs` 가 없어 포인터만 있다. `cam_wrist.mjpeg` 는 원래 올라가 있지 않다.

## Global Constraints

- `policy_runner/` 는 `tactile_rec` 을 import 해도 되지만 `tactile_rec` 은 `policy_runner` 를 모른다. `control_hub` 는 둘 다 import 하지 않는다(기존 규칙).
- runner 는 USB 를 열지 않는다. 카메라·PaXini 는 Hub 가, 손은 `leap_teleop` 이, 팔은 Robot PC 가 소유한다.
- 수치 파라미터(포트, timeout, age·skew 예산, 제한값)는 `policy_runner/config/runner.example.yaml` 에 둔다. 코드 기본값으로 박지 않는다.
- 필수 입력이 없거나 오래됐으면 0 으로 채우지 않는다. 요청을 보내지 않고 `problems` 에 이유를 남긴다.
- Executor 는 네트워크를 기다리지 않는다. 늦은 tick 에 여러 행을 몰아 보내지 않는다.
- 이 계획의 어떤 단계도 모터 명령을 보내지 않는다. `commands/arm_omy.py` 는 만들지 않는다(D 단계). `commands/hand_udp.py` 는 만들되 `mode: dry_run` 이 아니면 시작을 거부한다(E 단계에서 푼다).
- ruff `line-length = 100`, `E, F, I, B, UP`. 화면·로그 문구는 기존 패키지와 같은 형식.

## Review Focus

1. 미래 샘플을 쓰지 않는다: 기준 시각 `t_obs_ns` 이후에 도착한 샘플은 절대 고르지 않는다 → `test_align_never_uses_a_sample_after_t_obs`.
2. 온라인 관측 = 학습 변환: 같은 기록, 같은 grid 시각에서 `AlignedObs.state`·이미지가 `convert_episode()` 와 bit 단위로 같다 → `test_online_obs_matches_converted_episode`.
3. timeout 뒤 늦게 온 응답이 다음 요청의 답으로 읽히지 않는다 → `test_late_reply_after_timeout_is_never_used`.
4. 잘못된 응답(NaN, shape, 문자열 오류)은 command 층에 닿지 않는다 → `test_bad_reply_never_reaches_commands`.
5. 추론이 멈춰도 Executor tick 은 제때 돌고 HOLD 로 간다. 멈췄다 풀려도 밀린 행을 한꺼번에 보내지 않는다 → `test_executor_does_not_catch_up`.

---

## 2. 파일 구조

```
policy_runner/                         [신규]
├─ pyproject.toml                      tactile-rec (path, editable) + msgpack + websockets + pyyaml
├─ .python-version                     3.12
├─ uv.lock
├─ config/
│  ├─ runner.example.yaml              endpoint, timeout, 예산, 실행 모드, rig 경로
│  ├─ runner.fake.yaml                 fake rig + fake server (손 하드웨어 없이)
│  └─ manifest.example.yaml            checkpoint 와 짝지은 계약
├─ src/policy_runner/
│  ├─ config.py                        RunnerConfig 읽기·검증 (온라인 불가 시간 모드 거부)
│  ├─ manifest.py                      Manifest: joint_names, fps, H, camera slots, image, mount, ids
│  ├─ align_obs.py                     ObsAligner, AlignedObs, Pick, to_request()
│  ├─ wire.py                          msgpack_numpy (openpi-client 70fea7b 에서 옮김, 출처 표기)
│  ├─ inference.py                     PolicyClient (timeout·재연결), InferenceWorker (thread)
│  ├─ chunk.py                         ActionChunk, check_reply()
│  ├─ executor.py                      상태 기계 + tick + limits
│  ├─ commands/
│  │  ├─ dry_run.py                    명령을 trace 에만 남긴다
│  │  └─ hand_udp.py                   leap_teleop policy source 로 16관절 deg 전송
│  ├─ trace.py                         chunk·tick 시각 jsonl + 요약(p50/p95/p99/max)
│  ├─ fake_server.py                   openpi 와 같은 handshake 의 가짜 서버 + 고장 주입
│  └─ cli.py                           check / fake-server / probe / dry-run
└─ tests/
user_pc/src/leap_teleop/
├─ sources/policy_udp.py               [신규] PolicyUdpSource
├─ retarget/passthrough.py             [신규] Reading.hand 를 그대로 돌려준다
└─ cli.py                              [수정] --source policy, --policy-udp HOST:PORT
control_hub/config/hub.fake.yaml       [수정] policy_fake_server, policy_dry_run 항목
openpi-RLT (팀 레포, 별도 PR)          [C 단계] omy_leap_policy.py, pi05_omy_leap config
```

## 3. 데이터 계약

### wire 요청 (runner → 서버)

```python
{
    "state": float32[22],                       # manifest.joint_names 순서, rad
    "images": {"cam_wrist": uint8[H, W, 3],     # upright RGB (features.orient_image 결과)
               "cam_ext":   uint8[H, W, 3]},    # rig 에 있을 때만
    "prompt": str,                              # session.text
}
```

리사이즈는 서버 쪽 model transform(224 resize_with_pad)에 맡긴다. 학습 때와 같은 경로를 한 번만 지나게 하려는 것이다. 원격에서 대역폭이 문제면 C 단계 측정 뒤에 다시 정한다.

### wire 응답 (서버 → runner)

`{"actions": float[H, 22], "policy_timing": {...}, "server_timing": {...}}`. runner 는 `actions` 만 쓰고 timing 은 trace 에 넣는다. 22 로 자르는 것은 서버(`OmyLeapOutputs`)의 일이다. runner 는 22 가 아니면 거부한다.

### AlignedObs

```python
@dataclass(frozen=True)
class Pick:
    seq: int            # Stream 이 붙인 도착 번호
    t_ns: int           # 정렬에 쓴 시각 (recv 또는 mono src, latency 보정 후)
    age_ns: int         # t_obs_ns - t_ns

@dataclass(frozen=True)
class AlignedObs:
    obs_id: int
    t_obs_ns: int                    # User PC monotonic
    picks: dict[str, Pick]
    state: np.ndarray | None         # float32[22]
    images: dict[str, np.ndarray]    # cam -> uint8 HWC RGB
    ok: bool
    problems: tuple[str, ...]        # "cam_wrist: 212 ms old (limit 100)" 같은 문장
```

### ActionChunk

```python
@dataclass
class ActionChunk:
    chunk_id: int
    obs_id: int
    t_obs_ns: int
    t_sent_ns: int
    t_reply_ns: int
    actions: np.ndarray      # float32[H, 22], 읽기 전용 복사본
    exec_horizon: int        # K, 1 <= K <= H
    t_start_ns: int = -1     # 채택 시각; 행 i 의 예정 시각 = t_start_ns + i * dt
    cursor: int = 0
```

### leap_teleop policy UDP (runner → leap_teleop, 127.0.0.1)

`{"v": 1, "seq": int, "t_ns": int, "chunk_id": int, "hand_deg": [16]}`. 순서는 `HAND_JOINTS`(= `leap_teleop.hand.joints.ANGLE_NAMES`). rad → deg 변환은 runner 의 `commands/hand_udp.py` 한 곳에서만 한다.

### manifest (checkpoint 와 짝)

`schema_version, joint_names[22], units: rad, action_kind: absolute_joint, fps, pred_horizon, camera_slots {cam_ext: base_0_rgb, cam_wrist: left_wrist_0_rgb}, image {rotation_deg per cam, color: rgb}, mount: wrist_flip, hand_action: sent, norm_stats_id, checkpoint`. runner 는 시작할 때 manifest 를 rig config(`dataset.fps`, `arm_dof`, `cameras`, `mount`, `hand_action`)와 대조하고, 서버 metadata 에 manifest 가 있으면 그것과도 대조한다. 하나라도 다르면 시작하지 않는다.

### config (runner.example.yaml 초안. 값은 측정 전 자리표시)

```yaml
rig: ../recorder/config/rig.yaml        # 같은 rig 파일을 녹화기와 공유
manifest: config/manifest.example.yaml
policy:
  endpoint: ws://127.0.0.1:8000         # 원격이면 ssh -L 로 당겨서 같은 주소
  connect_timeout_s: 5
  infer_timeout_ms: 2000                # 측정 후 확정
observation:
  max_age_ms: {cam_wrist: 100, arm_state: 20, hand: 60}   # 필수 stream 마다 하나. 측정 후 확정
  max_skew_ms: 100
ui: {host: 127.0.0.1, port: 8810}
execution:
  mode: dry_run                          # dry_run | hand_only (E 단계 전까지 dry_run 만 허용)
  exec_horizon: 10                       # K
  chunk_max_delay_ms: 500                # t_start - t_obs 가 이보다 크면 버린다
  tick_jitter_ms: 10                     # tick 이 이만큼 늦으면 그 tick 은 건너뛰고 기록
  first_row_max_rad: 0.15                # 첫 행과 현재 측정 상태의 관절별 최대 차이
  step_max_rad: 0.05                     # 이웃 행 사이 관절별 최대 변화
hand_udp: {host: 127.0.0.1, port: 47810}
trace: {dir: ~/.local/state/policy_runner/traces}
```

`fps` 와 `dt` 는 config 에 따로 두지 않는다. `rig.dataset.fps` 에서 계산하고 manifest 의 fps 와 같아야 한다.

## 4. 상태 기계

```
STOPPED → STARTING → READY ──(arm)──→ RUNNING ──→ HOLD ──→ RUNNING
                                   │                     │
                                   └──────→ FAULT ←──────┘ (명시적 reset 만)
```

- STARTING: Hub 시작, manifest 대조, 서버 연결·metadata, warm-up 요청 1회(결과는 버린다).
- READY: 관측은 돈다. 명령 없음. `arm` 명령(CLI 키 입력 또는 Hub API) 전에는 RUNNING 으로 가지 않는다.
- RUNNING: 유효 chunk 의 행을 tick 마다 보낸다.
- HOLD: 유효 chunk 가 없다(대기·거부·만료). dry-run 에서는 "hold" 를 기록만 한다. 실제 장치에서 hold 의 뜻(마지막 목표 유지)은 E 단계에서 장치별로 정한다.
- FAULT: 서버 문자열 오류, 연결 끊김 N회, manifest 불일치, 관측 실패 지속. 재연결만으로 RUNNING 에 돌아가지 않는다.

---

## 5. Task 목록

### Stage A · 관측 정렬

**Task A1: 패키지 뼈대와 환경**
- [ ] `policy_runner/pyproject.toml`: `dependencies = ["tactile-rec", "numpy", "msgpack", "websockets>=13", "PyYAML"]`, `[tool.uv.sources] tactile-rec = { path = "../recorder", editable = true }`, dev extra `pytest, ruff`. `.python-version` 3.12. `uv lock`.
- [ ] `uv run --extra dev pytest` 가 빈 tests 로 통과.
- [ ] 레포 README 의 패키지 표에 `policy_runner/` 한 줄. 환경은 "uv + `policy_runner/.venv`" 로 적는다.

**Task A2: config·manifest 읽기**
- [ ] `config.py`: `RunnerConfig.load(path)`. rig yaml 은 `tactile_rec.config` 로 읽는다.
- [ ] 거부 규칙: required stream 이 rig 에 없음, required stream 의 `dataset.time` 이 `respread`, required stream 이 `src` 인데 `src_clock` 이 mono 가 아님(`remote_wall`, `host_wall` 의 episode 단위 offset 은 온라인에서 재현 불가), `exec_horizon` 이 `1..pred_horizon` 밖.
- [ ] `manifest.py`: 읽기 + `check_against(rig_config)` → 불일치 문장 목록.
- [ ] tests: `test_config_rejects_respread_for_required_stream`, `test_config_rejects_remote_src_time`, `test_manifest_mismatch_lists_every_field`.

**Task A3: ObsAligner**
- [ ] `align(t_obs_ns)`: 각 stream 의 `recent(t_obs_ns - window)` 에서 시각 배열을 만들고 `align.stream_times`(offline 과 같은 mode·latency) → `pick_latest`. 손 state 는 `pos` 유한 샘플만 후보로 한다(offline 의 `hand_has_feedback` 와 같은 규칙).
- [ ] `t_ns > t_obs_ns` 인 샘플은 후보에서 뺀다. 버퍼에 이미 들어왔더라도 쓰지 않는다.
- [ ] age·skew·유한성·shape 검사 → `ok`, `problems`. 이미지는 `features.orient_image` 를 거친 뒤 복사해서 넣는다(버퍼의 배열과 메모리를 공유하지 않는다).
- [ ] `to_request(obs, prompt)` → wire dict.
- [ ] tests (FakeClock + passive Stream):
  - `test_align_never_uses_a_sample_after_t_obs`
  - `test_old_stream_makes_obs_not_ok_and_names_it`
  - `test_skew_over_budget_is_reported`
  - `test_missing_required_stream_is_not_zero_filled`
  - `test_hand_state_skips_samples_without_feedback`
  - `test_optional_tactile_absence_does_not_block`

**Task A4: 온라인 = 학습 동일성**
- [ ] `tests/test_equivalence.py`: recorder `tests/conftest.py` 의 `ManualRig` 와 같은 방식으로 fake rig 를 만들고 녹화 세션을 돌리면서, `on_step` 에서 grid 시각마다 `ObsAligner.align()` 결과를 모은다. 녹화된 episode 를 `convert_episode()` 로 변환해 같은 grid 시각끼리 비교한다.
  - `test_online_obs_matches_converted_episode`: `observation.state` 와 `observation.images.<cam>` 이 bit 단위로 같다.
  - `test_equivalence_holds_with_camera_latency_setting`: `latency_ms: {cam_wrist: 35}` 에서도 같다.
- [ ] `tests/test_samples_1117.py` (LFS 가 받아져 있을 때만, 없으면 skip): 11/17 깨끗한 episode 의 기록 시각을 그대로 passive Stream 에 재생해 state 동일성과 age·skew 분포를 출력한다. 카메라는 프레임 시각만 있으므로 시각만 비교한다.
- [ ] `ManualRig` 를 복사하지 않고 쓰는 방법: recorder `tests/conftest.py` 를 `tactile_rec.testing` 같은 모듈로 옮기는 것은 recorder 변경이므로 하지 않는다. 같은 일을 하는 30줄짜리 helper 를 `policy_runner/tests/rig.py` 에 둔다.

**완료 기준 A:** 위 테스트 전부 통과. `policy-runner check --config config/runner.fake.yaml --no-server` 가 fake rig 로 관측 하나를 만들어 picks·age·problems 를 출력한다.

### Stage B · 가짜 서버와 dry-run

**Task B1: wire 코덱과 client**
- [ ] `wire.py`: openpi-client `msgpack_numpy.py` 를 옮기고 맨 위에 출처(`Physical-Intelligence/openpi` via `sehwa118/openpi-RLT@70fea7b`, Apache-2.0)를 적는다. 동작은 바꾸지 않는다.
- [ ] `PolicyClient(endpoint, connect_timeout_s)`: `websockets.sync.client.connect(..., compression=None, max_size=None, open_timeout=...)` → 첫 메시지 metadata. `infer(obs, timeout_s)`: send → `recv(timeout=...)`. 문자열 응답 → `ServerError`. timeout → 연결을 **닫고** `InferTimeout`. 닫는 이유: 같은 연결에서 늦게 도착한 응답이 다음 요청의 답으로 읽히기 때문이다. 다음 요청 전에 재연결한다.
- [ ] tests: `test_roundtrip_preserves_dtype_and_shape`, `test_string_reply_raises_server_error`, `test_late_reply_after_timeout_is_never_used`.

**Task B2: fake server**
- [ ] `fake_server.py`: `websockets.asyncio.server.serve(...)`, `process_request` 로 `/healthz` 200, 연결 직후 metadata(`{"fake": true, "manifest": ...}`), 요청마다 응답. openpi 서버와 같은 순서·형식이다.
- [ ] 행동 생성: `hold`(H 행 모두 현재 state) / `sine`(state 주변 작은 사인, 진폭은 인자). 어느 쪽도 실물에 보내져도 큰 움직임이 아니도록 기본은 `hold`.
- [ ] 고장 주입 (CLI 인자, 요청 번호 기준으로 재현 가능): `--delay-ms`, `--jitter-ms`, `--nan-every N`, `--bad-shape-every N`, `--error-every N`(traceback 문자열), `--drop-every N`(연결 끊기), `--stall-every N`(응답 안 함).
- [ ] `policy-runner fake-server --port 8000 [--...]`.
- [ ] tests: `test_fake_server_handshake_matches_openpi`(metadata 먼저, `/healthz`), 고장 인자별 1개씩.

**Task B3: InferenceWorker 와 chunk 검사**
- [ ] `InferenceWorker`: 요청 slot 1개(`max_inflight=1`). Executor 가 `want_chunk()` 를 부르면 worker 가 `align(now)` → `ok` 가 아니면 요청하지 않고 이유를 trace 에 남긴 뒤 짧게 쉬었다 다시 → `infer` → `check_reply` → 결과 slot. 장치에는 접근하지 않는다.
- [ ] `check_reply(reply, manifest, obs)`: `actions` 존재, shape `(H, 22)`, `H == manifest.pred_horizon`, 전부 유한, dtype float. 실패하면 이유 문장.
- [ ] tests: `test_bad_reply_never_reaches_commands`(NaN·shape·문자열 각각), `test_not_ok_obs_sends_no_request`.

**Task B4: Executor**
- [ ] 절대 시각 스케줄: chunk 를 채택하면 `t_start_ns = now`, 행 i 의 예정 시각 = `t_start_ns + i*dt`. tick 은 예정 시각까지 `sleep`. 예정 시각보다 `tick_jitter_ms` 이상 늦으면 그 행은 보내지 않고 `late` 로 기록한 뒤 cursor 를 그 시각에 맞는 행으로 옮긴다. 밀린 행을 몰아 보내지 않는다.
- [ ] 채택 조건: `now - t_obs_ns <= chunk_max_delay_ms`, 첫 행과 현재 측정 state(최신 `arm_state`/`hand` pick) 차이 `<= first_row_max_rad`, 이웃 행 차이 `<= step_max_rad`. 하나라도 어기면 chunk 를 버리고 HOLD.
- [ ] K 개를 소비하면 다음 chunk 를 요청한다(겹치지 않는 방식). 기다리는 동안 HOLD.
- [ ] 22 → arm 6 + hand 16 으로 나눠 각 command 로 넘긴다. 이 계획에서는 둘 다 `dry_run`.
- [ ] tests (FakeClock): `test_rows_go_out_one_per_dt`, `test_executor_does_not_catch_up`, `test_stale_chunk_is_discarded`, `test_first_row_far_from_state_is_rejected`, `test_hold_while_waiting_for_chunk`, `test_fault_needs_explicit_reset`.

**Task B5: trace 와 dry-run CLI**
- [ ] `trace.py`: chunk 마다 `t_obs, t_sent, t_reply, t_start`, 서버 `infer_ms`, 각 pick 의 age, tick 마다 예정·실제 시각과 결과(sent/late/hold). jsonl. 끝날 때 p50/p95/p99/max 와 기한 초과율을 출력한다.
- [ ] `policy-runner dry-run --config ... --duration 60`: Hub + worker + executor + dry_run commands. `arm` 은 `--arm` 플래그로 시작 즉시(dry-run 에서만 허용).
- [ ] tests: `test_dry_run_end_to_end_with_fake_server`(fake rig + 실제 fake-server 프로세스, 5 s, trace 의 chunk 수와 tick 수 검사).

**Task B6: leap_teleop policy source (손 하드웨어 없이 검증)**
- [ ] `sources/policy_udp.py`: `PolicyUdpSource(host, port)` 가 패킷을 받아 `Reading(timestamp=<수신 monotonic s>, hand=hand_deg)`. 버전·길이·유한성 검사, 나쁜 패킷은 세고 버린다.
- [ ] `retarget/passthrough.py`: `reading.hand` 를 그대로 돌려준다(복사).
- [ ] `cli.py`: `--source policy`, `--policy-udp 127.0.0.1:47810`. 나머지(`--dry-run`, `--record-udp`, `--stale-timeout`, `--release-timeout`, `--safe-pose`)는 그대로 쓴다.
- [ ] runner `commands/hand_udp.py`: rad → deg, 패킷 전송. `mode != dry_run` 이면 생성자에서 거부(E 단계 전까지).
- [ ] tests (user_pc): `test_policy_source_reads_hand_packet`, `test_policy_source_rejects_bad_packets`, `test_policy_source_goes_stale_through_guard`.
- [ ] 통합 확인(수동, 하드웨어 없음): `leap-teleop --source policy --dry-run --record-udp` + `policy-runner dry-run`(손 command 만 `hand_udp` 로 바꾼 설정) → `tactile-rec check hand` 또는 runner 의 hand stream 에서 `cmd` 가 runner 가 보낸 값과 같음을 확인.

**Task B7: (선택) 실제 openpi client 로 fake server 호환 확인**
- [ ] `tests/compat/probe_openpi_client.py`: 격리 환경에서 실제 `openpi_client.WebsocketClientPolicy` 를 fake server 에 붙여 metadata·infer 를 확인한다.
  `uv run --isolated --python 3.11 --with "openpi-client @ git+https://github.com/sehwa118/openpi-RLT@70fea7b#subdirectory=packages/openpi-client" python tests/compat/probe_openpi_client.py --port 8000`
  네트워크가 필요하므로 기본 pytest 에는 넣지 않는다.

**Task B8: Control Hub 연결 (fake 만)**
- [ ] `hub.fake.yaml` 에 `policy_fake_server`, `policy_dry_run` 항목, `conflicts: [recorder_fake]`. 실장비용 `hub.example.yaml` 항목은 D 단계에서 추가한다.

**완료 기준 B:** 위 테스트 전부 통과. fake rig + fake server(`--delay-ms 150 --jitter-ms 50 --nan-every 7 --stall-every 13`) 60 s dry-run 의 trace 요약에서 NaN·stall chunk 가 한 번도 command 에 가지 않았고, tick 예정 대비 지연 p99 와 HOLD 비율이 출력된다.

### Stage C · 실제 π0.5 연결

**C0: 서버 위치와 openpi 버전 하나로 정하기** (구현 전 결정)
- GPU 서버의 `vla-rtxpro6000:models` 이미지(upstream openpi `215abfb`) 또는 openpi-RLT `70fea7b` checkout. 우리 config(`pi05_omy_leap`)는 openpi-RLT 에 넣을 것이므로 serving 도 openpi-RLT 로 맞추는 것을 추천한다.

**C1: 우리 checkpoint 없이 실제 추론 지연부터 잰다**
- 서버 (GPU 서버, openpi 환경):
  ```bash
  uv run scripts/serve_policy.py --env ALOHA --port 8000
  # = pi05_aloha config + gs://openpi-assets/checkpoints/pi05_base. 첫 실행에 checkpoint 를 받는다
  ```
- User PC 에서 터널 (서버 포트를 망에 열지 않는다):
  ```bash
  ssh -N -L 8000:127.0.0.1:8000 <gpu-server>
  curl -s http://127.0.0.1:8000/healthz      # OK
  ```
- runner:
  ```bash
  cd policy_runner
  uv run policy-runner probe --endpoint ws://127.0.0.1:8000 --example aloha --n 100
  ```
  `probe` 는 ALOHA 모양 무작위 관측(`state` 14, `cam_high`/`cam_low`/`cam_left_wrist`/`cam_right_wrist` CHW uint8 224, prompt)을 보내고, 첫 요청(JIT 컴파일 포함)과 나머지를 나눠 왕복 시간과 서버 `infer_ms` 의 p50/p95/max, 응답 shape 를 출력한다. 이 값이 `infer_timeout_ms`, `chunk_max_delay_ms`, K 를 정하는 첫 근거다.
  - 같은 명령을 로컬 서버(User PC 에서 서버 실행, RTX 3070 8GB)로도 한 번. VRAM 이 8GB 를 넘으면 실행 전에 알린다.
- 결과는 `docs/results/2026-MM-DD-pi05-latency.md` 에 조건(서버 GPU, commit, 첫/이후 분리)과 함께 남긴다.

**C2: openpi-RLT 에 우리 입출력 변환** (팀 레포, 별도 브랜치·PR)
- `src/openpi/policies/omy_leap_policy.py`:
  - `OmyLeapInputs(action_dim, model_type)`: `images.cam_ext → base_0_rgb`, `images.cam_wrist → left_wrist_0_rgb`, `right_wrist_0_rgb` 는 0 이미지 + mask False. `cam_ext` 가 없는 rig 면 base 도 0 + False (학습과 같게). `state`, `actions`, `prompt` 그대로.
  - `OmyLeapOutputs`: `actions[:, :22]`.
  - `make_omy_leap_example()` (probe·테스트용).
- `training/config.py`: `LeRobotOmyLeapDataConfig` (repack: `observation.images.cam_wrist`, `observation.images.cam_ext`, `observation.state`, `action`), `TrainConfig(name="pi05_omy_leap", model=Pi0Config(pi05=True, action_dim=32, action_horizon=50, ...))`. delta action 은 쓰지 않는다(가이드 합의: 절대 관절 목표).
- 이 변환으로 우리 데이터셋을 학습해 checkpoint 와 `norm_stats` 를 만든다. 학습은 이 계획 범위 밖이다.

**C3: 실제 checkpoint 로 dry-run**
- 서버: `uv run scripts/serve_policy.py --port 8000 policy:checkpoint --policy.config=pi05_omy_leap --policy.dir=<ckpt>`.
- runner: `policy-runner check --config config/runner.yaml` (manifest·metadata 대조, 관측 1개, 추론 1회) → `policy-runner dry-run --config config/runner.yaml --duration 120`.
- 순서: fake rig 로 먼저(입력은 가짜, 출력 shape·지연만 확인) → 실제 센서 Hub(카메라·팔 state·손 feedback; 팔 bringup 과 `leap-teleop --source policy --dry-run --record-udp` 를 켠다. 모터 명령 없음).
- 완료 기준: `actions` 가 `(50, 22)`, 유한, 첫 행과 현재 state 의 차이 분포가 trace 에 있고, 로컬·원격 왕복 지연 p50/p95/p99/max 가 기록된다.

### D 이후 (이 계획 밖, 결정만 기록)

- OMY 명령 경로: follower controller 가 듣는 topic, leader 없이 follower 만 켜는 launch, zenoh-ros2-sdk publisher 사용 가능 여부. 모두 UNVERIFIED.
- 손 hold/release: 정책 모드에서 `StaleGuard` release(3 s 뒤 safe pose)가 쥔 물체를 놓친다. `--release-timeout`·`--safe-pose` 값 또는 policy 전용 동작을 E 전에 정한다.
- 팔 action 정의: 학습 action 은 leader `/leader/joint_trajectory`(7값 중 앞 6) 다. follower 에 같은 값을 목표로 주는 것이 같은 의미인지 D 에서 확인한다.

## 7. 평가 (자율 구현 전에 고정)

구현보다 먼저 아래 ①②를 커밋한다. 그 commit 이 **freeze commit** 이다. 구현 중에 `policy_runner/tests/acceptance/`, `policy_runner/audit/audit_trace.py`, `policy_runner/audit/MUTANTS.md` 를 고치지 않는다. 마지막에 `git diff --stat <freeze> -- <세 경로>` 가 비어 있어야 한다.

### ① 수락 테스트 (`policy_runner/tests/acceptance/`)

공개 인터페이스(§3 계약, 아래 API)만 쓴다.

```python
policy_runner.config.load(path) -> RunnerConfig            # ConfigError(problems)
policy_runner.manifest.Manifest.load(path); .mismatches(rig) -> list[str]
policy_runner.align_obs.ObsAligner(hub, rig, max_age_ms, max_skew_ms).align(t_obs_ns) -> AlignedObs
policy_runner.align_obs.to_request(obs, prompt) -> dict
policy_runner.wire.packb(obj) / unpackb(bytes)
policy_runner.inference.PolicyClient(endpoint, connect_timeout_s).infer(obs, timeout_s)
    # ServerError, InferTimeout, Disconnected
policy_runner.chunk.check_reply(reply, pred_horizon, action_dim) -> list[str]
policy_runner.fake_server.start(port=0, **faults) -> FakeServer(.port, .stop())
policy_runner.executor.Executor(dt_ns, exec_horizon, limits, chunks, measured, commands, trace)
    .arm(now_ns) .disarm(now_ns) .reset(now_ns) .tick(now_ns) .state
    # chunks: request(now_ns, ) / take(now_ns) -> ActionChunk | None / fault -> str
policy_runner.trace.Trace(path)   # jsonl, 이벤트 스키마는 audit_trace.py 의 docstring 이 아닌 SCHEMA 상수
```

| 묶음 | 테스트 |
|---|---|
| config·manifest | respread·원격 src·K 범위·manifest 불일치 거부 |
| 정렬 | 미래 샘플 미사용, 오래된 stream·skew·누락(0 채움 없음)·손 feedback 없는 샘플·촉각 없음 |
| 동일성 | fake rig 녹화 → `convert_episode` 와 state·이미지 bit 일치 (latency 설정 포함). 11/17 실데이터 재생: state 불일치가 있다면 전부 "offline 이 아직 도착하지 않은 샘플을 쓴 경우"로 설명된다 |
| 통신 | dtype·shape 보존, 문자열 오류, timeout 뒤 늦은 응답 미사용, 끊김 |
| fake server | metadata 먼저, `/healthz`, NaN·shape·error·drop·stall 주입 |
| 응답 검사 | NaN·shape·H 불일치·actions 없음 거부 |
| Executor | dt 당 1행, catch-up 없음, 오래된 chunk 버림, 첫 행·이웃 행 제한, READY 에서 명령 없음, FAULT 는 reset 만, K 행 초과 없음 |
| 시뮬레이션 | K ∈ {10, 25} × L ∈ {150, 280, 990} ms, 60 s, FakeClock: chunk 수·행 수·HOLD tick 수가 `K + ceil(L/dt)` 정수 식과 정확히 같다 (아래 표) |
| 끝까지 | fake rig + fake server 스레드 3 s 실시간: trace 가 감사기를 통과, chunk ≥ 1 |
| 손 | `hand` 모드는 `--allow-hand` 없이 거부, UDP 패킷이 rad→deg·`HAND_JOINTS` 순서 |
| leap_teleop | policy source 가 패킷을 Reading 으로, 나쁜 패킷 버림, 조용하면 StaleGuard hold |
| Hub | `page: policy` 점검이 정책 페이지, 기존 설정(`page` 없음)은 녹화 페이지 |

시뮬레이션 기대값 (fps 30, dt = 33 333 333 ns, 60 s = 1800 tick, Python 계산):

| K | L | 대기 tick | 사이클 | 가이드 식 | HOLD | chunk | 행 |
|---|---|---|---|---|---|---|---|
| 10 | 150 ms | 5 | 500.0 ms | 483.3 ms | 33.3 % | 120 | 1200 |
| 10 | 280 ms | 9 | 633.3 ms | 613.3 ms | 47.4 % | 95 | 945 |
| 10 | 990 ms | 30 | 1333.3 ms | 1323.3 ms | 75.0 % | 45 | 450 |
| 25 | 150 ms | 5 | 1000.0 ms | 983.3 ms | 16.7 % | 60 | 1500 |
| 25 | 280 ms | 9 | 1133.3 ms | 1113.3 ms | 26.5 % | 53 | 1323 |
| 25 | 990 ms | 30 | 1833.3 ms | 1823.3 ms | 54.5 % | 33 | 810 |

### ② trace 감사기 (`policy_runner/audit/audit_trace.py`)

runner 를 import 하지 않는다. trace jsonl 만 읽고 위반을 줄마다 출력, 위반이 있으면 exit 1. 감사기 자체도 위반마다 하나씩 만든 가짜 trace 로 시험한다.

1. `send.action` 이 22개, 전부 유한
2. 모든 `send` 의 chunk 가 채택(`chunk.adopted`)됐고, 채택 시각 − `t_obs_ns` ≤ `chunk_max_delay_ns`
3. `obs.picks[*].t_ns` ≤ `obs.t_obs_ns`
4. 연속 `send` 간격 ≥ dt − jitter, `send.t_ns − send.due_ns` ≤ jitter
5. 같은 chunk 의 이웃 `send` 변화 ≤ `step_max_rad`, 채택 chunk 의 `max|row0 − measured|` ≤ `first_row_max_rad`
6. `send` 는 상태가 RUNNING 일 때만
7. FAULT 뒤에는 `state READY reason=reset` 전까지 `send` 없음
8. chunk 당 `send` ≤ K, `row` < K

### ③ 의도적 버그 (`policy_runner/audit/MUTANTS.md` 에 목록 고정, 패치는 구현 뒤 `audit/mutants/*.patch`)

M1 정렬이 `latest()` 사용 · M2 손 feedback 필터 제거 · M3 timeout 뒤 연결 유지 · M4 응답 NaN 검사 제거 · M5 tick 이 밀린 행을 몰아 보냄 · M6 행 예정 시각을 응답 도착 기준으로 · M7 K 대신 H 행 실행 · M8 손 UDP 에 rad 그대로 · M9 JPEG 왕복 제거 · M10 READY 에서 명령 전송. 각 패치를 적용하면 수락 테스트나 감사기 중 하나 이상이 실패해야 한다. 통과하는 패치가 있으면 평가 실패.

### ④ 기계적 검사

recorder·control_hub·user_pc 기존 테스트 통과, `git diff --stat main -- recorder` 비어 있음, `rg "serial|pyrealsense|LeapHand|dynamixel" policy_runner/src` 0, `rg policy_runner recorder control_hub` 0, `ruff check policy_runner`, `policy_runner/src` 에 `#` 코멘트·docstring 없음(`wire.py` 라이선스 머리말 제외).

### ⑤ 보고

`policy_runner/audit/run_all.sh` 가 ①~④ 를 돌리고 `docs/results/YYYY-MM-DD-policy-runner-eval.md` 에 표로 쓴다. 실시간 dry-run tick 지연(p50/p95/p99/max)은 보고만 하고 기준으로 쓰지 않는다.

## 6. 사람이 해야 하는 것 (실행 전)

- 11/17 샘플 재생 테스트: `brew install git-lfs && git lfs install && git lfs pull` (이 Mac). Ubuntu 는 `sudo apt install git-lfs`.
- C1: GPU 서버 접속 정보(ssh host)와 서버 쪽 openpi 환경 위치.
- C2: openpi-RLT 에 브랜치를 만들 권한과 팀 합의.
