# 녹화기 사용법과 테스트 방법

`recorder/` 의 `tactile-rec` 프로그램을 설치하고, 실물 없이 돌려 보고, 현장에서 확인하고, 데이터셋으로 변환하는 순서다.
설계와 결정 이유는 [`2026-11-14-recorder-design.html`](2026-11-14-recorder-design.html) 에 있다.

실물로 확인하지 않은 부분에는 **[현장 미검증]** 표시가 있다. 5절의 체크리스트가 그 확인 절차다.

## 1. 설치

### User PC (녹화하는 PC)

```bash
cd ~/Projects/SHAPE_UP_Tactile/recorder
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[ui]'                    # 녹화기 + 웹 UI
pip install -e '.[arm,tactile,camera]'    # 실제 장치용: zenoh-ros2-sdk, pyserial, pyrealsense2
pip install -e ../third_party/paxini      # Paxini SDK
pip install -e '.[viz]'                   # 선택: Rerun 재생
```

- `zenoh-ros2-sdk` 는 처음 실행할 때 메시지 정의를 git 에서 내려받는다. **첫 실행은 인터넷이 되는 상태에서** 한다.
- 이 venv 는 ROS 와 무관하다. 셸에 ROS 환경이 올라와 있어서 Python 이 섞이면 명령 앞에 `env -u PYTHONPATH` 를 붙인다.
- `leap_teleop` 은 지금처럼 자기 환경에서 돌린다. 녹화기와 같은 venv 일 필요가 없다.

### 학습 서버 (변환하는 PC)

openpi 환경 안에서 녹화기를 추가로 설치한다. `lerobot` 은 openpi 가 고정한 버전을 그대로 쓴다.

```bash
cd <레포>/recorder
pip install -e .          # openpi 환경이 활성화된 상태에서
```

## 2. 실물 없이 돌려 보기

모든 장치가 가짜 신호를 내는 설정이 들어 있다. UI, 녹화, 변환까지 그대로 동작한다.

```bash
cd recorder
tactile-rec record --config config/rig.fake.yaml
# 브라우저에서 http://localhost:8800
```

- 4초마다 촉각·모터 전류·카메라 밝기가 동시에 튄다. 시간이 맞는지 눈으로 볼 수 있다.
- `Space` 로 시작, 다시 `Space` 로 정지, `S` 로 성공 저장. 결과는 `recorder/data_fake/` 에 쌓인다.
- 화면 없이 자동으로 찍어 보려면: `tactile-rec record --config config/rig.fake.yaml --ui none --auto 9 --episodes 2`

찍은 것을 확인하고 변환까지 해 본다.

```bash
tactile-rec inspect data_fake                       # 에피소드별 스트림 개수, Hz, 최대 공백
tactile-rec tap data_fake/demo_task/*/ep_0001       # 스트림 간 시간 차이
tactile-rec replay data_fake/demo_task/*/ep_0001    # Rerun 뷰어
tactile-rec convert --config config/rig.fake.yaml --in data_fake/demo_task \
    --out /tmp/demo_npz --format npz                # lerobot 없이 되는 변환
```

시험과 코드 검사:

```bash
pip install -e '.[dev]'
env -u PYTHONPATH python -m pytest -q     # 녹화기 시험
ruff check src tests
cd ../user_pc && env -u PYTHONPATH python -m pytest -q   # 텔레옵 시험 (싱크 포함)
```

## 3. 설정 파일

`config/rig.example.yaml` 을 `config/rig.yaml` 로 복사해서 쓴다. 틀린 키나 없는 스트림 이름은 실행할 때 바로 오류로 나온다.

| 항목 | 뜻 |
|---|---|
| `rig.mount` | 장착 모드. `wrist_flip` 과 순정 장착 데이터는 한 데이터셋으로 변환되지 않는다 |
| `data_root` | 에피소드가 쌓이는 곳. `--root` 로 덮어쓸 수 있다 |
| `session` | 태스크 이름(폴더 이름), 태스크 문장, 수집자. `--task`, `--text`, `--operator` 또는 UI 설정 페이지에서 바꾼다 |
| `streams.*.hz` | 기대 Hz. 이 값의 80% 아래면 "느림", 3주기 이상 조용하면 "끊김" |
| `streams.*.required` | `false` 면 없어도 녹화가 시작된다 (글러브, 아직 안 단 외부 카메라) |
| `streams.tactile_*.places` | 보드가 보고하는 모듈 이름 → 손의 위치(`index_tip` 등). 실제와 다르면 그 스트림은 오류로 멈춘다 |
| `streams.cam_*.rotation_deg` | 저장된 프레임을 바로 세우는 시계 방향 회전. 원본은 회전 없이 저장된다 |
| `dataset.time` | 스트림별로 어떤 시각으로 맞출지: `recv`, `src`, `respread` |
| `dataset.latency_ms` | 스트림별 지연 보정. 5절의 실측 뒤에 채운다 |

현장에서 맞춰야 하는 값 (**[현장 미검증]**): 팔 스트림의 `hz`, 촉각 `places`, 손목 카메라 `rotation_deg` (90 또는 270), 외부 카메라 `serial`.

## 4. 녹화

### 실행 순서

1. Robot PC: 지금처럼 `zenohd` 와 `omy_ai_wrist_flip` 을 띄운다.
2. User PC: Manus 노드를 띄운다.
3. User PC: 텔레옵에 옵션 하나를 추가한다.

   ```bash
   leap-teleop --source manus ... --record-udp
   ```

   `--record-udp` 는 틱마다 손·글러브 값을 `127.0.0.1:47800` 으로 보낸다. 받는 쪽이 없어도 텔레옵에는 영향이 없다.
4. User PC: **`realsense2_camera` ROS 노드는 끈다.** 녹화기가 카메라를 직접 연다. 둘이 동시에 같은 카메라를 열 수 없다.
5. User PC: 녹화기를 띄운다.

   ```bash
   cd recorder && source .venv/bin/activate
   tactile-rec record --config config/rig.yaml --task pick_cup --text "Pick up the cup" --operator hamin
   ```

6. 브라우저에서 `http://localhost:8800`. 기본은 이 PC에서만 열린다. 태블릿에서 쓰려면 `--host 0.0.0.0` 을 붙여 띄우고 `http://<User PC 주소>:8800` 으로 연다. 로그인이 없으므로 믿을 수 있는 네트워크에서만 한다.

### 화면에서 하는 일

| 상태 | 키 | 동작 |
|---|---|---|
| 대기 | `Space` | 녹화 시작. 점검에 걸리면 이유가 나오고 시작되지 않는다 |
| 대기 | `Z` | 촉각 영점 보정. 손에 아무것도 닿지 않은 상태에서 한다 |
| 녹화 중 | `Space` | 정지 |
| 녹화 중 | `M` | 표시 남기기 (예: 접촉 시작) |
| 녹화 중, 검토 | `D` | 버리기. 같은 번호로 다시 찍는다 |
| 검토 | `S` / `F` | 성공으로 저장 / 실패로 저장 |

- 시작 전 점검은 필수 스트림이 모두 정상인지, 텔레옵이 `live` 인지, 디스크 여유가 있는지를 본다.
- 녹화 중에 센서가 끊기면 소리가 세 번 나고 그 에피소드에 표시가 남는다. 검토 화면에 "주의"로 보인다. 다시 찍는 것을 권한다.
- 터미널로 쓰려면 `--ui terminal`. 키는 같고, 강제 시작은 `!` 다.

### 저장되는 곳

```text
<data_root>/pick_cup/2026-11-20_1430_hamin/ep_0001/
```

태스크나 수집자를 바꾸면 새 세션 폴더가 만들어진다.

## 5. 현장 테스트 체크리스트

실물이 준비되면 이 순서대로 한다. 각 단계는 앞 단계가 통과해야 의미가 있다.
결과는 `docs/field-test/YYYY-MM-DD-results.md` 에 숫자와 함께 적는다.

### 5.1 장치별 확인 (녹화기 전체를 띄우기 전에)

`check` 는 스트림 하나만 몇 초 돌리고 Hz, 간격, 빠진 수, 마지막 값을 보여 준다.

| 순서 | 명령 | 볼 것 | 통과 기준 |
|---|---|---|---|
| 1 | `tactile-rec check hand --config config/rig.yaml` | 텔레옵이 `--record-udp` 로 돌고 있을 때 | 약 50 Hz, `delay_ms` 중앙값 1 ms 안팎 |
| 2 | `tactile-rec check glove --config config/rig.yaml` | `nodes` 개수, `meta.node_names` | 약 50 Hz, 노드 이름이 나옴 |
| 3 | `tactile-rec check arm_state --config config/rig.yaml` | **[현장 미검증]** SDK 로 Jazzy 토픽 수신 | 값이 오고 Hz 가 측정됨 → 그 값을 설정의 `hz` 에 넣는다 |
| 4 | `tactile-rec check arm_action --config config/rig.yaml` | **[현장 미검증]** 리더를 움직이는 동안 | 값이 오고 `source_stamps` 가 있는지 확인 |
| 5 | `tactile-rec check tactile_a --config config/rig.yaml` | **[현장 미검증]** 센서 4개 동시 스트림 | Hz 측정, `missed` 0, `meta.layout` 의 모듈이 실제 배선과 같음 |
| 6 | `tactile-rec check cam_wrist --config config/rig.yaml` | **[현장 미검증]** `ts_domain`, `meta.usb` | 설정 fps 유지. `ts_domain` 이 0 이면 프레임 시각을 못 쓰므로 `dataset.time` 을 `recv` 로 둔다 |

막혔을 때:

- **3, 4 가 "open failed"**: `router` 주소와 `domain_id` 확인. 메시지 정의를 못 받은 것이면 인터넷 연결 후 다시 실행.
- **3, 4 가 연결은 되는데 0개**: SDK 가 만드는 키가 Robot PC 와 안 맞는 것이다. 이 경우 Robot PC 컨테이너에 중계 노드를 두는 쪽으로 바꾼다 (`streams/arm_zenoh.py` 한 파일만 교체).
- **5 가 "board modules do not match"**: 메시지에 실제 모듈 이름이 나온다. 설정의 `places` 를 그에 맞춘다.
- **6 이 "open failed"**: ROS 카메라 노드가 켜져 있거나 `serial` 이 틀렸다.

### 5.2 전체 띄우기와 짧은 녹화

1. `tactile-rec record --config config/rig.yaml` 로 띄우고 센서 페이지에서 모든 스트림이 "정상"인지 본다.
2. 녹화 페이지에서 손목 카메라가 바로 서 있는지 본다. 누워 있으면 `rotation_deg` 를 바꾼다 (다시 찍을 필요 없이 설정만).
3. 촉각 패널: 손가락을 하나씩 눌러서 화면의 같은 손가락·같은 마디가 반응하는지 본다. 다르면 `places` 가 틀린 것이다. 표시는 Paxini SDK 뷰어와 같은 방식이다 (힘이 클수록 진한 파랑과 큰 점, 아래는 합력 Fx / Fy / Fz). 센서를 끌면 회전하고 두 번 누르면 원래대로 돌아온다.
4. 10초짜리 에피소드를 하나 찍고 `tactile-rec inspect <에피소드>` 로 스트림별 Hz 와 최대 공백을 본다.

### 5.3 시간 차이 실측

사건이 뚜렷한 에피소드를 따로 찍는다 (태스크 이름을 `sync_test` 처럼 구분).

1. 가만히 있다가 손가락을 빠르게 쥔다. 1초 쉬고 반복, 5회 이상. → 글러브, 손 명령, 손 위치, 카메라 움직임
2. 손끝 센서로 책상을 톡 친다. 1초 쉬고 반복, 5회 이상. → 촉각 힘, 모터 전류
3. 실행:

   ```bash
   tactile-rec tap <에피소드> --ref hand.cmd          # 쥐기 기준
   tactile-rec tap <에피소드> --ref tactile_a.force   # 톡 치기 기준
   ```

읽는 법:

- `offset` 이 `+` 면 그 스트림이 기준보다 늦게 보인다는 뜻이다. 그 값을 `dataset.latency_ms` 에 넣으면 변환 때 상쇄된다.
- **물리적으로 원래 늦는 것은 보정하지 않는다.** 명령 → 위치(모터가 따라가는 시간), 글러브 → 명령(리타게팅)은 실제 지연이다.
- 보정 대상은 같은 순간이어야 하는 쌍이다: 촉각 힘 대 모터 전류, 손 위치 대 카메라 움직임.
- `spread` 가 크면(수십 ms) 그 스트림의 지연이 일정하지 않다는 뜻이다. 값 하나로 보정되지 않으므로 원인을 먼저 본다.

### 5.4 오래 돌려 보기

10분짜리 에피소드를 하나 찍는다 (`time_limit_s: 600`).

- 센서 페이지의 Hz 추이가 평평한지, 스트림 표의 "빠짐"이 늘지 않는지 본다.
- `inspect` 에서 카메라의 `write-dropped` 가 0 인지 본다. 0 이 아니면 디스크나 CPU 가 못 따라간 것이다.
- `top` 으로 녹화기 프로세스의 메모리가 계속 늘지 않는지 본다. 숫자 스트림은 메모리에 쌓이므로 조금씩 느는 것은 정상이고, 10분에 수백 MB 를 넘으면 기록해 둔다.

### 5.5 변환과 학습 확인

1. 태스크 폴더를 학습 서버로 복사한다 (`rsync -a`).
2. 6절의 명령으로 변환하고 `*.conversion_report.json` 에서 제외된 에피소드와 이유를 본다.
3. `tactile-rec replay` 로 원본을, LeRobot 시각화로 변환 결과를 눈으로 본다.
4. openpi 쪽에 우리 키를 pi0.5 입력에 연결하는 데이터 설정을 만들고, 정규화 통계 계산과 학습 몇 스텝을 돌린다. **이 설정 파일은 아직 없다.** 첫 실제 데이터셋이 나오면 만든다.

## 6. 변환

학습 서버의 openpi 환경에서 실행한다.

```bash
tactile-rec convert --config config/rig.yaml \
    --in /data/shape_up/pick_cup \
    --out /data/lerobot/shape_up/pick_cup \
    --repo-id shape_up/pick_cup
```

| 옵션 | 뜻 |
|---|---|
| `--in` | 에피소드, 세션, 태스크 폴더, 또는 데이터 루트. 여러 개를 줄 수 있다 |
| `--format npz` | `lerobot` 없이 에피소드당 `.npz` 로 낸다. 정렬 확인용, 우리 모델 학습용 |
| `--fps` | 데이터셋 fps (기본은 설정의 30) |
| `--image-mode video` | 영상으로 저장해 용량을 줄인다. 기본 `image` 는 openpi 예제와 같은 방식이다 |
| `--include-failed` | 실패로 표시된 에피소드도 포함 |
| `--include-flagged` | 끊김이 있었거나 값이 오래된 에피소드도 포함 |
| `--overwrite` | 출력 폴더가 있으면 지우고 다시 쓴다 |

- 기본으로 제외되는 것: 실패 표시, 녹화 중 끊김, 강제 시작, 어떤 값이 150 ms 넘게 오래된 에피소드.
- 출력 옆에 `<출력 이름>.conversion_report.json` 이 생긴다. 에피소드마다 스텝 수, 스트림별 "가장 오래된 값(ms)", 재사용된 프레임 수, 제외 이유가 있다.
- **쓰는 환경과 읽는 환경이 같아야 한다.** `datasets` 라이브러리 4.x 로 쓴 것을 3.x 로 읽으면 실패한다. openpi 환경에서 변환하면 맞는다.

데이터셋의 키와 차원은 확정안 문서의 4절 표와 같다.

## 7. 원본을 직접 읽기

```python
from tactile_rec.convert.load import Episode
from tactile_rec.tactile import decode_payload, to_newtons

ep = Episode("/data/shape_up/pick_cup/2026-11-20_1430_hamin/ep_0001")
hand = ep.arrays("hand")                 # t_recv_ns, t_src_ns, seq, src_seq, cmd, sent, pos, vel, cur, mode
tactile = ep.arrays("tactile_a")         # payload: 보드가 보낸 바이트 그대로 (90 Hz 전부)
forces = decode_payload(tactile["payload"], ep.layout("tactile_a"))
fz = to_newtons(forces["index_tip"]["distributed"])[:, :, 2]    # (샘플 수, 52) 뉴턴
frame = ep.frame("cam_wrist", 0)         # BGR, 회전 전
```

시각은 모두 녹화 PC 의 monotonic 시계(ns)다. `episode.json` 의 `start` 에 그 시계와 벽시계의 대응이 한 쌍 들어 있다.

## 8. 문제 해결

| 증상 | 확인 |
|---|---|
| "not ready to record" | 화면의 문제 목록을 본다. 스트림이 "없음"이면 장치·텔레옵이 안 뜬 것이다 |
| `hand` 가 "없음" | 텔레옵에 `--record-udp` 가 빠졌거나 포트가 다르다 (기본 47800) |
| "teleop is not live" | 글러브가 끊겨 손이 hold / release 상태다. 텔레옵 로그를 본다 |
| 촉각 스트림이 "오류" | 센서 페이지의 메시지를 본다. 모듈 불일치면 `places`, 포트 문제면 `/dev/ttyACM*` 권한과 번호 |
| 시험이 ROS 플러그인 오류로 시작도 못 함 | `env -u PYTHONPATH` 를 붙인다 |
| 변환이 "lerobot is not installed" | openpi 환경이 아니다. 확인만 하려면 `--format npz` |
| 변환에서 전부 제외됨 | 보고서의 `skipped` 이유를 본다. 지연 보정을 크게 넣었으면 "오래된 값" 기준에 걸릴 수 있다 |
