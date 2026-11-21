# GPU 서버 smoke: openpi `pi05_omy_leap` ↔ policy_runner (2026-11-21)

목적은 정책 품질이 아니라 **프로토콜, manifest 대조, 응답 모양, 지연**이다. 학습한 checkpoint 는 아직 없다. 서버와 실행기를 같은 GPU 서버(inst-i108, RTX PRO 6000 Blackwell 96 GB)에서 돌렸고, `ws://127.0.0.1:8000` 로 붙었다. Mac 과 ssh 터널은 쓰지 않았다.

## 조건

| 항목 | 값 |
|---|---|
| 서버 코드 | openpi-RLT `feat/omy-leap` (main `70fea7b` 기반). `serve_policy.py` 는 고치지 않음 |
| 서버 환경 | 해당 worktree 의 uv venv (jax 0.5.3 cuda12, `XLA_PYTHON_CLIENT_MEM_FRACTION=0.3`, 약 30 GB 사용) |
| config | `pi05_omy_leap`: π0.5, action_horizon 50, `discrete_state_input=True`, 22축 delta 학습 / 절대값 출력 |
| 가중치 | `pi05_base` params (학습 안 함). checkpoint 디렉터리 = `params` symlink + `assets/local/omy_leap_sync_test/norm_stats.json` |
| norm stats | 11/17 `2026-11-17_2035_hamin/ep_0001` 1634 frame. `1852` 에피소드는 변환기가 거부함 (arm_state 6.4 s 끊김). sha256 앞자리 `e50848eb5795` |
| 실행기 | `feat/policy-runner-server-smoke` (2026-11-22 에 `feat/policy-runner` 로 합침), `config/runner.server-smoke.yaml` (가짜 rig, `cam_wrist` 만, dry_run, K 10) |
| manifest | `cameras: [cam_wrist]`, `checkpoint: pi05_base-untrained`, `norm_stats_id: omy_leap_sync_test_20261117` |

샘플 에피소드에는 카메라 영상(`cam_wrist.mjpeg`)이 없다 (git 에 타임스탬프만 있음). 그래서 `cameras: []` rig 로 state/action 만 변환했고, norm stats 는 `compute_norm_stats.py` 에서 `OmyLeapInputs` (이미지 슬롯 매핑) 단계만 뺀 일회용 스크립트로 계산했다. 같은 data loader, 같은 `DeltaActions`, 같은 `RunningStats` 를 쓴다. 스크립트와 rig 파일은 서버 `/workspace/users/hamin/checkpoints/pi05_omy_leap/` 에 있다. 실데이터는 영상이 있으므로 원래 스크립트를 쓰면 된다.

## 결과

| 시험 | 결과 |
|---|---|
| openpi 단위 테스트 `omy_leap_policy_test.py` | 7 passed (실행기 요청 → 모델 입력 모양, 0 delta → 측정 state 와 같은 절대 action, manifest 9키) |
| policy_runner 수락 테스트 (Linux) | 83 passed |
| checkpoint 로드 | 학습 없이 조립한 디렉터리가 그대로 로드됨. `/healthz` 200 까지 16–20 s |
| `probe --count 50` (JIT 뒤) | manifest 차이 없음, 응답 50개 모두 (50, 22) float 유한값. RTT 중앙값 71.5 ms, 최대 407.5 ms, 서버 infer 중앙값 68.5 ms |
| 새 서버 첫 요청 (JIT) | **36.3 s** (한 번 측정). 그 뒤 중앙값 77.0 ms |
| `run` dry_run 60 s + `audit/soak.py` | 감사기 4207 events, **0 problems**. 요청 601 / 응답 실패 0 / FAULT 0. RTT p50 73.9, p99 84.0, max 87.9 ms |
| chunk 채택 | 600 개 전부 거부, HOLD 100 %. 사유 "first row is 1.445 rad from the measured state (limit 0.15)" |

## 해석

- 연결 계약(metadata 먼저, 요청 하나에 응답 하나, manifest 9키, (50, 22) 절대 action)은 맞는다.
- chunk 거부는 학습 안 한 가중치 때문에 예상한 결과이고, 실행기 첫 행 검사가 의도대로 동작한 것이다. executor 의 실제 송신 경로는 학습한 checkpoint 로 확인해야 한다.
- 첫 요청 JIT 36 s 는 `warmup_timeout_s: 60` 안이지만, Blackwell 에서 cuDNN conv 알고리즘 탐색이 오래 걸린다(서버 로그 `slow_operation_alarm`). GPU 가 바쁠 때는 60 s 를 넘을 수 있다 (미검증). `probe` 기본 `--timeout-ms 30000` 은 새 서버에서 첫 요청이 시간 초과된다.
- RTT ≈ 75 ms 는 30 fps 기준 약 3 tick 이다. `infer_timeout_ms: 1000`, `chunk_max_delay_ms: 500`, K 10 (333 ms) 은 여유가 충분하다.

## 재현 (GPU 서버)

```bash
# 서버
cd /workspace/users/hamin/projects/openpi-RLT/.claude/worktrees/omy-leap
OPENPI_DATA_HOME=/workspace/users/hamin/cache/openpi XLA_PYTHON_CLIENT_MEM_FRACTION=0.3 \
  uv run scripts/serve_policy.py --port 8000 policy:checkpoint --policy.config=pi05_omy_leap \
  --policy.dir=/workspace/users/hamin/checkpoints/pi05_omy_leap/pi05_base-untrained

# 실행기 (다른 터미널)
cd /workspace/users/hamin/projects/SHAPE_UP_Tactile/.claude/worktrees/runner-smoke/policy_runner
uv run policy-runner probe config/runner.server-smoke.yaml --count 50 --timeout-ms 600000
uv run policy-runner run config/runner.server-smoke.yaml &   # UI :8810
uv run python audit/soak.py --seconds 60
uv run python audit/audit_trace.py traces/<trace>.jsonl && uv run python audit/summary.py traces/<trace>.jsonl
```

## Mac 에서 ssh 터널로 연결 (2026-11-21 21:07)

같은 서버와 같은 checkpoint 에 Mac(가짜 rig)에서 `ssh -N -L 8000:127.0.0.1:8000 gpu`(계정 `hamin`)로 붙었다. 실행기 설정은 `config/runner.server-smoke.yaml` 그대로다.

| 시험 | 서버 안 (위) | Mac + 터널 |
|---|---|---|
| `/healthz` | 200 | 200 (31 ms) |
| `probe --count 50` 첫 요청 (새 서버 JIT) | 36.3 s | 36.7 s |
| `probe` RTT 중앙값 / 최대 | 71.5 / 407.5 ms | 117.2 / 426.5 ms |
| 서버 infer 중앙값 | 68.5 ms | 70.7 ms |
| 60 s `run` + `soak.py` 감사기 | 0 problems | 3386 events, **0 problems** |
| 요청 수 / 응답 실패 / FAULT | 601 / 0 / 0 | 395 / 0 / 0 |
| `run` RTT p50 / p99 / max | 73.9 / 84.0 / 87.9 ms | 125.1 / 318.7 / 477.5 ms |
| chunk | 600 전부 거부 (첫 행) | 394 전부 거부 (첫 행 1.05–1.37 rad) |

- 망을 거치면 RTT 중앙값이 약 50 ms 늘고 꼬리가 길어진다(p99 318.7 ms). `infer_timeout_ms: 1000`, `chunk_max_delay_ms: 500` 안이지만 p99 가 K 10 (333 ms) 에 가깝다. 같은 망 경로라면 HOLD 비율이 커진다. 학습한 checkpoint 로 다시 잰다.
- 요청 수가 601 → 395 로 줄었다. 사이클마다 응답을 기다리는 tick 이 늘었기 때문이다. 채택이 모두 거부되므로 사이클 = 대기 tick + 1 이다.
- trace: `policy_runner/traces/2026-11-21_210708.jsonl` (git 제외).

이번에 서버를 다시 띄우면서 바꾼 것:
- smoke checkpoint 의 `params` symlink 가 없어진 경로(`/workspace/teams/tactile/openpi-RLT/checkpoints/...`)를 가리키고 있었다. `/workspace/teams/tactile/data/checkpoints/openpi-assets/checkpoints/pi05_base/params` 로 바꿨다.
- 비대화형 ssh 에서는 `uv` 가 PATH 에 없다(`/workspace/users/hamin/conda/envs/hamin/bin/uv`). 그래서 worktree 의 `.venv/bin/python scripts/serve_policy.py ...` 로 띄웠다. 로그: `/workspace/users/hamin/logs/serve_smoke_mac.log`.
- `serve_policy.py` 는 `0.0.0.0:8000` 에 bind 한다. 외부에서 8000 에 닿는지는 확인하지 않았다 (미검증).
