# 정책 실행기 평가 (Stage A + B, 2026-11-21)

계획: [2026-11-20-policy-runner.md](../superpowers/plans/2026-11-20-policy-runner.md) §7. 평가 기준은 구현 전에 `14e415b` 로 고정했다.

## 조건

- 브랜치 `feat/policy-runner` (main `8c635ae` 에서). 평가 시점 HEAD `1c5cee8`.
- 기계: MacBook (Apple Silicon), macOS 15.5, Python 3.12.14 (`policy_runner/.venv`, uv). 백그라운드 작업으로 실행.
- rig: `recorder/config/rig.fake.yaml` (가짜 팔 100 Hz, 손 50 Hz, 카메라 2대 30 Hz). 정책 서버: `policy-runner fake-server` (받은 state 를 50 행으로 되돌려 주는 hold 정책).
- 실데이터: git-lfs 로 받은 `data/samples/2026-11-17/sync_test` 의 두 에피소드 (`2035_hamin/ep_0001` 깨끗함, `1852_hamin/ep_0001` 샘플 누락).
- 한 번에 재현: `cd policy_runner && ./audit/run_all.sh`

## 1. 고정 평가 (`audit/run_all.sh`)

| 항목 | 결과 |
|---|---|
| policy_runner 수락 테스트 | 83 passed |
| leap_teleop 테스트 (policy source 포함) | 170 passed |
| control_hub 테스트 (정책 페이지 포함) | 110 passed, 36 skipped, 1 failed |
| ruff | 통과 |
| 코멘트·docstring | `wire.py` 라이선스 머리말 외 없음 |
| 의도적 버그 | 12/12 잡힘 |

control_hub 의 실패 1건은 `tests/test_remote.py::test_probe_finds_tagged_processes_and_stops_them` 이다. `/proc` 을 읽는 Linux 전용 테스트이고, `remote.py` 와 이 테스트는 `8c635ae` 이후 바뀌지 않았다(`git diff --stat 8c635ae` 결과 없음). skip 36건은 tmux 가 없는 이 Mac 에서 tmux 를 쓰는 테스트다. 둘 다 Ubuntu 에서는 돌 것으로 보지만 확인하지 않았다(미검증).

### 수락 테스트가 확인하는 것

- **정렬 동일성:** 가짜 rig 를 녹화기로 녹화하고 `convert_episode` 로 변환한 뒤, 같은 원시 샘플을 새 Hub 에 재생하면서 매 격자 시각에 `ObsAligner.align` 을 부른다. state 와 두 카메라 이미지가 bit 단위로 같다. 카메라 latency 0 과 `cam_wrist: 35 ms` 두 경우 모두 확인했다.
- **11/17 실데이터 재생:** 두 에피소드 모두 통과. 기준은 두 가지다. state 불일치는 전부 "offline 이 아직 도착하지 않은 손 샘플(`t_src ≤ t < t_recv`)을 쓴 경우"로 설명되어야 하고, 불일치 비율은 5% 미만이어야 한다. 정확한 불일치 수는 테스트가 출력하지 않는다.
- **실행 사이클 식:** K ∈ {10, 25} × 지연 L ∈ {150, 280, 990} ms, 1800 tick(60 s). 보낸 행 수, 채택한 chunk 수, HOLD tick 수가 정수식 `K·⌊N/c⌋ + max(0, N mod c − w)` (c = w + K, w = ⌈L/dt⌉) 과 정확히 같다. 6 조합 모두 감사기 통과.
- **프로토콜:** msgpack 왕복, metadata 먼저 수신, `/healthz`, 문자열 오류 → `ServerError`, stall → `InferTimeout`, 끊김 → `Disconnected` 뒤 재연결, timeout 뒤 늦게 온 응답은 쓰지 않음, NaN·inf·shape·dtype 이상 응답 거부.
- **end-to-end:** 실제 스레드로 3 s 돌린 trace 가 감사기를 통과한다. 서버 manifest 가 다르면 시작을 거부한다. UI API 의 상태 값과 시작/정지 버튼을 확인한다. 손 UDP 는 rad → deg 로, `HAND_JOINTS` 순서대로 보낸다.

### 의도적 버그 (각각 넣었을 때 처음 실패한 테스트)

| id | 버그 | 잡은 테스트 |
|---|---|---|
| M01 | 정렬이 `t_obs` 뒤 샘플까지 쓴다 | `test_align_never_uses_a_sample_after_t_obs` |
| M02 | 손 feedback NaN 필터 제거 | `test_hand_state_skips_samples_without_feedback` |
| M03 | timeout 뒤 연결 유지 | `test_late_reply_after_timeout_is_never_used` |
| M04 | NaN 검사 제거 | `test_injected_bad_replies_fail_the_check[nan_every]` |
| M05 | 밀린 행 몰아 보내기 | `test_executor_does_not_catch_up` |
| M06 | 응답 도착 시각 기준 스케줄 | `test_rows_go_out_one_per_dt_from_adoption` |
| M07 | K 대신 H 행 실행 | `test_at_most_k_rows_per_chunk_then_a_new_request` |
| M08 | 손 UDP 에 rad 전송 | `test_hand_udp_sends_degrees_in_hand_joint_order` |
| M09 | JPEG 왕복 제거 | `test_online_obs_matches_converted_episode[latency0]` |
| M10 | READY 에서 tick 동작 | `test_nothing_is_sent_before_arm` |
| M11 | 첫 행–측정 상태 검사 제거 | `test_first_row_far_from_state_is_rejected` |
| M12 | 오래된 chunk 검사 제거 | `test_stale_chunk_is_discarded` |

## 2. 실제 프로세스로 돌린 결과

모두 `policy-runner run config/runner.fake.yaml` 을 띄우고 `/api/arm` 으로 시작했다. 결과는 trace 를 감사기(`audit/audit_trace.py`)와 요약(`audit/summary.py`)에 넣어 얻었다. trace 는 `policy_runner/traces/`(git 제외)에 있다.

| trace | 조건 | 감사기 | 결과 |
|---|---|---|---|
| `014229` | 지연 120 ms, 약 10 s | 611 events, 0 problems | chunk 29, 보낸 행 289, late 1 |
| `014645` | Hub iframe 확인 중 (Chrome·Hub 동시 실행) | 3964 events, **1 problem** | "two sends closer than dt": 행 2→3 간격 23.318 ms (< dt − jitter 23.333 ms). 아래 결함 1 |
| `014927` | 격자 수정 뒤, 지연 120 ms, 60 s, 처음 30 s 동안 CPU 바쁜 프로세스 4개 | 2554 events, 0 problems | chunk 125, 보낸 행 1249, late 0. 예정 대비 지연 p50 3.75 / p99 5.09 / max 5.98 ms |
| `015556` | 완료 기준 B: `--delay-ms 150 --jitter-ms 50 --nan-every 7 --stall-every 13`, 60 s, FAULT 마다 자동 reset·arm (`audit/soak.py`) | 2377 events, 0 problems | 아래 표 |
| `014433` | 손 모드: runner `mode: hand --allow-hand` → UDP → `leap_teleop --source policy --dry-run` | 177 events, 0 problems | 아래 손 경로 |

완료 기준 B 실행 (`015556`):

| 값 | 결과 |
|---|---|
| armed tick 1745 | send 801, late 64, hold 880 (50.4%) |
| chunk | 87 채택, 0 거부 |
| 응답 | 정상 87, `bad reply`(NaN) 14, `no reply within 1000 ms`(stall) 8 |
| FAULT | 14번, 전부 NaN 응답. 14번 모두 reset 뒤 다시 돌았다 |
| 예정 대비 지연 | p50 7.02, p99 9.92, max 10.00 ms |
| 왕복 | p50 182.7, p99 211.7, max 211.7 ms |

NaN 응답 14개는 모두 chunk 가 되기 전에 FAULT 로 갔다. 감사기가 확인한 대로 보낸 행 801개는 모두 22개의 유한한 값이다. stall 8번은 1 s timeout 뒤 재연결해서 이어졌고, 연속 실패 한도(3)에는 닿지 않았다.

손 경로 (`014433` 과 같은 시각의 `leap_teleop` 로그): `[teleop] waiting` → (arm) `live`, 목표 최대 59.7° → (disarm 0.5 s 뒤) `hold` → (3 s 뒤) `release`, 0°(safe pose). 59.7° 는 가짜 손 state 를 hold 정책이 그대로 돌려준 값이다. 따라서 deg → rad → deg 왕복이 맞다.

Hub 정책 페이지는 Chrome headless 로 찍어 직접 봤다. 정책 페이지 안에 실행기 UI 가 뜨고 RUNNING, 보낸 행 1648 이 보였다. 녹화 페이지는 "녹화기가 꺼져 있습니다" 와 켜기 버튼을 그대로 보여 준다. 이 Mac 에는 tmux 가 없어서, 화면 확인용으로만 job tmp 의 빈 `tmux` shim 으로 Hub 를 띄웠다.

## 3. 평가 중 찾은 결함

1. **채택 시각의 지터가 다음 행을 당겼다** (`014645`). 늦게 깬 tick 의 실제 시각을 chunk 시작 시각으로 잡았다. 그래서 다음 tick 들이 예정보다 일찍 보내졌고, 두 행이 23.318 ms 간격으로 나갔다. `9b73f4a` 에서 행 번호와 예정 시각을 ticker 의 격자 시각 기준으로 바꿨다. 늦음은 여전히 실제 시각으로 잰다. 수정 뒤 `014927`, `015556` 에서는 이 위반이 없었다.
2. **감사기가 길이가 다른 action 에서 예외로 죽었다.** freeze 직전 lint 수정(`zip(strict=True)`) 때문이었다. `51f556e` 에서 길이가 22 인 두 행일 때만 step 을 비교하게 고쳤다.
3. **고정 테스트의 latency 경우가 구현 불가능한 기대를 했다.** `latency_ms` 가 있으면 offline 변환은 격자 시각 뒤에 도착한 프레임을 고른다. 온라인은 그 프레임을 볼 수 없다. `0060e86` 에서 판정을 바꿨다. offline 프레임이 그 시각까지 도착했으면 bit 일치, 아니면 그때까지 도착한 마지막 프레임과 bit 일치. 이 기준은 계획의 11/17 재생 기준("offline 이 아직 도착하지 않은 샘플을 쓴 경우")과 같다.

## 4. 고정 기준에서 달라진 점

- 위 2, 3 의 테스트·감사기 수정 (각각 별도 commit).
- 의도적 버그를 `.patch` 파일 대신 `audit/mutants.py` 의 문자열 치환 표로 만들었다. 대상 문자열이 정확히 한 번 있어야 하고, 실행 뒤에는 항상 원본으로 되돌린다. 버그 목록 자체(`MUTANTS.md`)는 그대로다.
- `Executor.tick(now_ns, grid_ns=None)` 인자를 추가했다 (결함 1). 기존 호출은 그대로 동작한다.
- 새 설정 `policy.warmup_timeout_s`, `policy.max_failures`, `observation.fail_after_ms` 는 고정 테스트의 설정에 없다. 그래서 코드에서 기본값(60, 3, 1000)으로 읽는다. 예제 설정에는 값을 다 적었다.

## 5. 한계 (미검증)

- **tick 정밀도는 이 Mac 에서만 쟀다.** 같은 기계에서 runner 없이 1/30 s 대기만 150번 한 결과는 `Event.wait` p50 9.35 / p99 10.11 ms, `time.sleep` p50 8.55 / p99 10.05 ms 늦었다. 백그라운드 프로세스의 타이머 병합으로 보인다. 그래서 `015556` 의 late 64번(3.7%)은 이 기계의 대기 오차가 jitter 한도 10 ms 에 닿은 결과로 본다. 실제로 돌 Ubuntu User PC 에서는 재지 않았다.
- 실제 π0.5 서버와 실제 checkpoint 는 연결하지 않았다 (Stage C).
- 실제 rig(카메라·Paxini·zenoh 팔·LEAP)로는 돌리지 않았다. 손 경로는 `leap_teleop --dry-run`(LogDriver)까지만 확인했다.
- 정책 모드에서 `StaleGuard` release(3 s 뒤 safe pose)는 쥔 물체를 놓친다. 값은 실물 단계 전에 정한다.
