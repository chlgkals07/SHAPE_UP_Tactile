# tactile-rec

OMY 팔 + LEAP 손 + Manus 글러브 + Paxini 촉각 + RealSense 카메라를 한 시계로 녹화하고,
openpi 용 LeRobot v2.1 데이터셋으로 변환한다.

- 설계와 결정 이유: [`docs/data_preparation/2026-11-14-recorder-design.html`](../docs/data_preparation/2026-11-14-recorder-design.html)
- 사용법과 현장 테스트: [`docs/data_preparation/recorder_usage.md`](../docs/data_preparation/recorder_usage.md)

## 실물 없이 바로 돌려 보기

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[ui]'
tactile-rec record --config config/rig.fake.yaml     # http://localhost:8800
```

## 명령

| 명령 | 하는 일 |
|---|---|
| `tactile-rec record --config <rig.yaml>` | 허브와 녹화 UI 를 띄운다 (`--ui web` 기본, `terminal`, `none`) |
| `tactile-rec check <스트림> --config <rig.yaml>` | 스트림 하나만 몇 초 돌리고 Hz·간격·빠진 수를 낸다 |
| `tactile-rec inspect <경로>` | 저장된 에피소드 요약 |
| `tactile-rec tap <에피소드>` | 날카로운 사건으로 스트림 간 시간 차이를 잰다 |
| `tactile-rec replay <에피소드>` | Rerun 으로 원본을 본다 |
| `tactile-rec convert --config <rig.yaml> --in <경로> --out <출력>` | 원본 → LeRobot v2.1 (또는 `--format npz`) |

## 현장 미검증

장치 어댑터 세 개는 API 를 보고 작성했고 실물로는 아직 돌리지 않았다. 파일 맨 위에 `FIELD-UNVERIFIED` 로 적혀 있다.

| 파일 | 확인할 것 |
|---|---|
| `streams/arm_zenoh.py` | `zenoh-ros2-sdk` 로 Robot PC(Jazzy) 토픽이 오는지 |
| `streams/paxini.py` | 한 보드에 센서 여러 개일 때의 Hz, 스트림 중 영점 보정 |
| `streams/realsense.py` | 카메라 두 대 동시, 프레임 시각의 종류 |

## 시험

```bash
pip install -e '.[dev]'
env -u PYTHONPATH python -m pytest -q
ruff check src tests
```
