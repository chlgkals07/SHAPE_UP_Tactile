# policy_runner

π0.5 정책 서버(openpi websocket 프로토콜)를 OMY + LEAP rig 에 붙이는 실행기.
녹화기(`tactile_rec`)와 같은 규칙으로 팔·손·카메라를 정렬해 서버에 보낸다. 받은 action chunk 는 30 Hz 격자에서 K 행씩 실행한다.

- 관측: 각 stream 에서 `t_obs` 까지 도착한 샘플만 쓴다. 시각 규칙(recv / mono src, `latency_ms`), 손 feedback 필터, 이미지 JPEG 왕복이 녹화기 변환과 같다. 그래서 학습 데이터와 bit 단위로 같은 입력이 나간다.
- 실행: 요청 1개만 기다린다. 받은 chunk 는 다음 tick 에 채택해 K 행을 보내고, 다 보내면 다음 요청을 한다. 늦은 행은 건너뛰고 기록하며, 밀린 행을 몰아 보내지 않는다.
- 안전: 오래된 chunk 는 버린다. NaN·모양 오류·서버 오류, 연속 실패, 관측 실패 지속은 FAULT 로 간다. FAULT 는 reset 해야만 풀린다. 관절 범위·속도 제한은 실행기가 아니라 장치 제어기(LEAP 드라이버의 clip·slew)가 맡는다.
- 손: `mode: hand` 이면 `leap_teleop --source policy` 에 UDP(deg)로 보낸다. USB 는 `leap_teleop` 만 연다. 팔 명령은 아직 없다.
- 모든 판단은 `traces/*.jsonl` 에 남는다. `audit/audit_trace.py` 가 그 trace 를 독립적으로 검사한다.

## 환경

uv + `policy_runner/.venv` (Python 3.12, `.python-version`). recorder 를 editable 로 쓴다.

```bash
cd policy_runner
uv sync --extra dev
```

openpi-client 패키지는 쓰지 않는다. 그 패키지는 `numpy<2` 를 요구한다. wire 코덱만 `wire.py` 로 옮겼다 (Apache-2.0, 출처 표기).

## 사용

```bash
uv run policy-runner check config/runner.fake.yaml                  # 설정·rig·manifest 대조
uv run policy-runner fake-server --manifest config/manifest.fake.yaml --delay-ms 150
uv run policy-runner run config/runner.fake.yaml                    # UI http://127.0.0.1:8810
uv run policy-runner probe config/runner.fake.yaml --count 20      # 왕복 시간과 응답 검사
```

- 실제 rig: `config/runner.example.yaml` 과 `manifest.example.yaml` 을 `runner.yaml` / `manifest.yaml` 로 복사한다. 그다음 서버 주소와 checkpoint 정보를 채운다.
- `mode: hand` 는 `run --allow-hand` 가 있어야 시작한다. 받는 쪽은 `python3 -m leap_teleop.cli --source policy --safe-pose fist --record-udp [--dry-run]`.
- 가짜 서버 고장 주입: `--jitter-ms`, `--nan-every N`, `--bad-shape-every N`, `--stall-every N`, `--drop-every N`, `--error-every N`.
- Control Hub: `hub.example.yaml` 의 `policy`, `policy_fake_server`, `leap_policy` 프로세스와 "정책" 페이지.

## 평가

```bash
./audit/run_all.sh                                   # 수락 테스트 + leap_teleop + control_hub + ruff + 의도적 버그
uv run python audit/audit_trace.py traces/<file>.jsonl
uv run python audit/summary.py traces/<file>.jsonl
uv run python audit/soak.py --seconds 60             # 실행 중인 runner 를 FAULT 마다 reset 하며 돌린다
```

결과: [docs/results/2026-11-21-policy-runner-eval.md](../docs/results/2026-11-21-policy-runner-eval.md). 설계와 결정: [계획](../docs/superpowers/plans/2026-11-20-policy-runner.md). 전체 흐름 설명: [시스템 가이드](../docs/policy-runner-guide.html).
