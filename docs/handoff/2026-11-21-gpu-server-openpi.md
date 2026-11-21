# GPU 서버 작업 인수인계: openpi-RLT 에 OMY + LEAP 정책 추가 (2026-11-21)

이 문서는 GPU 서버에서 openpi-RLT 작업을 시작할 때 읽는 배경이다. User PC 쪽(정책 실행기)은 끝났고, 서버 쪽에 우리 rig 용 정책 config 를 만드는 것이 남았다.

## 1. 배경

- 로봇: OMY 팔 6축 + LEAP 손 16관절 (`robot_type: omy_f3m_leap`, `mount: wrist_flip`). 카메라는 손목 RealSense D405 하나(`cam_wrist`). 외부 카메라 `cam_ext` 는 아직 설치하지 않았다.
- 데이터: SHAPE_UP_Tactile 의 녹화기(`tactile_rec`)가 기록하고 LeRobot v2.1 로 변환한다.
- 정책: π0.5 fine-tuning. **우리 데이터로 학습한 checkpoint 는 아직 없다.**
- User PC 의 정책 실행기(`policy_runner`, 브랜치 `feat/policy-runner`)는 openpi WebSocket 프로토콜 클라이언트를 직접 구현했다. 가짜 서버로 평가를 끝냈다(수락 테스트 83, 의도적 버그 12/12, 60 s 고장 주입 soak 감사기 0 위반).
- 자세한 설명: SHAPE_UP_Tactile `docs/policy-runner-guide.html`.

## 2. 서버에서 고치지 않는 것

`scripts/serve_policy.py` 와 `WebsocketPolicyServer` 는 그대로 쓴다. openpi-RLT main `70fea7b` 소스에서 확인한 동작은 다음과 같다.

- 연결 직후 서버가 `msgpack(policy.metadata)` 를 먼저 보낸다.
- 요청 하나(bytes)마다 응답 하나(bytes)를 보낸다. 응답에는 `server_timing{infer_ms, prev_total_ms}` 가 추가된다.
- 예외가 나면 traceback 문자열(텍스트 프레임)을 보내고 연결을 닫는다.
- `GET /healthz` → 200. 기본 포트 8000.
- **추론할 때는 repack transform 을 적용하지 않는다.** `create_trained_policy` 의 `repack_transforms` 기본값이 빈 `Group()` 이다. 그래서 요청 dict 가 data transform(`OmyLeapInputs`)으로 바로 들어간다.
- `metadata` 는 `TrainConfig.policy_metadata` 다 (`config.py:604`).

## 3. User PC 가 보내고 기대하는 것 (계약)

### 요청

| 키 | 값 |
|---|---|
| `state` | `float32[22]`. 팔 joint1–6 (rad), 그 뒤 LEAP 16관절 (rad). 순서는 아래 `joint_names` |
| `images` | `{카메라 이름: uint8[H, W, 3]}`, RGB, 회전 보정 후. 실제 rig 는 `cam_wrist` (424, 240, 3) 하나다. Mac 가짜 rig 는 `cam_wrist` (424, 240, 3) 와 `cam_ext` (480, 640, 3) |
| `prompt` | str. rig 설정의 `session.text` (예: "Pick up the cup") |

이미지는 학습 데이터와 bit 단위로 같다(JPEG 왕복 + `orient_image`). 224×224 resize 는 openpi 모델 쪽(`resize_with_pad`)에서 한다.

### 응답

- `actions`: `float[50, 22]`. **절대 관절 목표**이고, 단위와 순서는 state 와 같다.
- 실행기가 거부하는 응답은 다음과 같다. 모양이 (50, 22) 가 아님, float 가 아님, NaN/inf 가 있음 → FAULT. 첫 행이 측정 state 와 0.15 rad 넘게 다름, 실행할 10행 안에서 행 사이 차이가 0.05 rad 를 넘음 → 그 chunk 를 버린다.

### metadata

`policy_metadata = {"manifest": {...}}`. 실행기는 시작할 때 아래 9개 키를 **모두** 자기 `manifest.yaml` 과 비교한다. 하나라도 다르면 시작하지 않는다.

```yaml
schema_version: 1
joint_names: [joint1, joint2, joint3, joint4, joint5, joint6, leap_index_mcp_side,
  leap_index_mcp_flex, leap_index_pip_flex, leap_index_dip_flex, leap_middle_mcp_side,
  leap_middle_mcp_flex, leap_middle_pip_flex, leap_middle_dip_flex, leap_ring_mcp_side,
  leap_ring_mcp_flex, leap_ring_pip_flex, leap_ring_dip_flex, leap_thumb_cmc_side,
  leap_thumb_cmc_flex, leap_thumb_mcp_flex, leap_thumb_ip_flex]
fps: 30
pred_horizon: 50
mount: wrist_flip
hand_action: sent
cameras: [cam_wrist]          # Mac 가짜 rig 시험이면 [cam_wrist, cam_ext]
checkpoint: <문자열, 양쪽 동일>
norm_stats_id: <문자열, 양쪽 동일>
```

## 4. 만들 것 (openpi-RLT, 브랜치 `feat/omy-leap`, main `70fea7b` 에서)

openpi-RLT 는 팀 레포라 PR 로 합친다. push 와 PR 은 사람이 결정한다.

| 순서 | 내용 | 위치 |
|---|---|---|
| 1 | `OmyLeapInputs` / `OmyLeapOutputs` | `src/openpi/policies/omy_leap_policy.py` (새 파일) |
| 2 | `LerobotOmyLeapDataConfig` + `TrainConfig(name="pi05_omy_leap")` (+ 필요하면 `_lora`) | `src/openpi/training/config.py` |
| 3 | 변환 단위 테스트 | `src/openpi/policies/omy_leap_policy_test.py` 같은 곳 |
| 4 | norm stats | `scripts/compute_norm_stats.py --config-name pi05_omy_leap` |
| 5 | 학습 | `scripts/train.py pi05_omy_leap --exp-name ...` |
| 6 | serving | `scripts/serve_policy.py --port 8000 policy:checkpoint --policy.config=pi05_omy_leap --policy.dir=<ckpt>` |

참고할 기존 코드는 `agilexbag_image_policy.py` 와 `LerobotAgilexBagImageDataConfig` (`config.py:366`)다. 구조가 거의 같다.

### `OmyLeapInputs`

- `data["images"]` 에서 고른다. `cam_ext` → `base_0_rgb`, `cam_wrist` → `left_wrist_0_rgb`, `right_wrist_0_rgb` 는 항상 0 이미지 + mask False.
- `cam_ext` 가 없으면 `base_0_rgb` 도 0 이미지 + mask False. agilex 처럼 예외를 내면 안 된다. 실제 rig 에는 외부 카메라가 없다.
- `state` 는 `data["state"]` 그대로 넘긴다(22). 모델 쪽에서 32로 padding 한다.
- `actions` 가 있으면 넘긴다(학습). 프롬프트는 `prompt` 를 쓰고, 없으면 `task` 를 쓴다.
- 이미지 dtype/layout 정리(`_parse_image`)는 agilex 것과 같게 한다. 학습 때 LeRobot 이 float CHW 로 줄 수 있다.

### `OmyLeapOutputs`

- `{"actions": np.asarray(data["actions"][:, :22])}`.

### Data config repack (학습용)

```python
{"images": {"cam_wrist": "observation.images.cam_wrist"},   # cam_ext 를 달면 추가
 "state": "observation.state",
 "actions": "action",
 "prompt": "task"}                                          # 또는 prompt_from_task=True
```

데이터셋에는 촉각(`observation.tactile.*`)과 `observation.hand_current` 키도 있다. π0.5 기준선에서는 쓰지 않으므로 repack 에서 고르지 않는다.

### 정해야 할 것

1. **delta vs 절대 action.** openpi 의 관절 공간 config 는 `DeltaActions` 입력 + `AbsoluteActions` 출력을 자주 쓴다. 어느 쪽이든 **서버 출력은 절대값**이어야 한다. delta 를 쓴다면 mask 범위도 정해야 한다. 팔 6만(`make_bool_mask(6, -16)`)인지, 22 전부인지. 정하지 않았다.
2. **full fine-tuning vs LoRA.** VRAM 에 따라 정한다. openpi README 기준 대략 추론 > 8 GB, LoRA > 22.5 GB, full > 70 GB 다. 기억에 의존한 수치라 서버 README 에서 다시 확인한다 (UNVERIFIED).
3. **실행 환경.** `vla-docker-rtxpro6000` 은 upstream openpi `215abfb` 를 설치한다. openpi-RLT `70fea7b` 와 같은 코드인지 확인하지 않았다 (UNVERIFIED). 우리 config 를 추가하려면 openpi-RLT 체크아웃을 uv 로 쓰는 쪽이 맞아 보인다. 서버에서 하나로 정한다.

## 5. 데이터셋 만들기

녹화기 변환은 openpi env 안에서 돌린다. openpi 가 고정한 lerobot(`0cf8648`, v2.1 API)을 import 하기 때문이다.

```bash
tactile-rec convert --config <rig.yaml> --in <에피소드 경로> --out <출력> \
  --format lerobot --repo-id <hf_user>/omy_leap_<task>
```

- 저장 키: `observation.state` (22), `action` (22: leader 팔 + 손 `sent`), `observation.images.cam_wrist`, `task`.
- 지금 있는 실데이터는 2026-11-17 `sync_test` 2 에피소드뿐이다(git LFS). 파이프라인 시험에는 충분하지만 학습용으로는 부족하다.
- tactile_rec 을 openpi env 에 같이 설치하는 방식은 "레포 하나에 환경 하나" 규칙과 부딪친다. `--format npz` 로 변환한 뒤 openpi 쪽에서 LeRobot 으로 옮기는 방법도 있다. 서버에서 정한다.

## 6. 학습 전에 Mac 을 User PC 로 쓰는 연결 시험

지금 User PC 에는 GPU 서버 ssh key 가 없다. 그래서 Mac(가짜 rig)에서 붙는다. 목적은 정책 품질이 아니라 **프로토콜, 모양, 지연, manifest 대조**다.

1. **C1: 지연만 재기.** 서버에서 기존 공개 config(예: `pi05_aloha`, `pi05_base`)를 띄운다. 서버 안에서 `examples/simple_client` 로 첫 요청(JIT)과 정상 상태 왕복 시간을 잰다. 이 값으로 `infer_timeout_ms`, `chunk_max_delay_ms`, K 를 정한다.
2. **C2 smoke: 우리 config, 학습 안 한 가중치.** checkpoint 디렉터리를 만든다. 내용은 `pi05_base` params, 그리고 11/17 샘플로 계산한 `assets/<asset_id>/norm_stats.json`. 이걸 `pi05_omy_leap` 으로 serving 한다. 출력은 의미 없지만 모양과 dtype 이 맞고, 실행기의 첫 행 검사에서 거부되는 것까지 확인할 수 있다. 이 방법이 그대로 로드되는지는 확인하지 않았다 (UNVERIFIED). 안 되면 몇십 step 짧게 학습해 진짜 checkpoint 형식을 만든다.
3. **Mac 에서 연결.**
   ```bash
   ssh -N -L 8000:127.0.0.1:8000 <gpu-server>          # 서버 포트는 망에 열지 않는다
   curl -s http://127.0.0.1:8000/healthz
   cd policy_runner
   uv run policy-runner probe <runner.yaml> --count 50
   uv run policy-runner run <runner.yaml>               # http://127.0.0.1:8810
   ```
   `<runner.yaml>` 은 `runner.fake.yaml` 을 복사해 쓴다. manifest 의 `checkpoint` / `norm_stats_id` 는 서버 metadata 와 같은 값으로 바꾼다. `cameras: [cam_wrist, cam_ext]` 는 가짜 rig 기준이다.
4. 끝나면 trace 를 `audit/audit_trace.py` 와 `audit/summary.py` 에 넣는다. RTT 분포와 HOLD 비율을 `docs/results/` 에 기록한다.

## 7. 서버 작업 순서 제안

1. openpi-RLT 위치, 브랜치, 환경(uv / docker)을 확인하고, GPU 와 VRAM 을 확인한다(`nvidia-smi`).
2. C1 지연 측정.
3. `feat/omy-leap` 브랜치를 만들고 `omy_leap_policy.py` 와 단위 테스트를 작성한다. 가짜 요청 dict 로 Inputs → 모델 입력 모양, Outputs → (50, 22) 를 확인한다.
4. `pi05_omy_leap` config, 11/17 샘플 LeRobot 변환, norm stats 계산.
5. C2 smoke serving → Mac 에서 연결 시험.
6. 실제 데이터 수집 뒤 학습 (C3).
