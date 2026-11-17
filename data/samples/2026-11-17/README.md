# 11/17 샘플 에피소드 (분석용)

11/17 첫 실물 시험(`docs/field-test/2026-11-17-results.md`)에서 녹화기로 찍은 에피소드 두 개다.
녹화기 원본 구조를 그대로 두었으므로 `tactile-rec inspect` 로 바로 열린다.

```bash
cd recorder
tactile-rec inspect ../data/samples/2026-11-17/sync_test/2026-11-17_2035_hamin
```

`*.npz` 는 git LFS 로 올렸다. 받은 뒤 파일이 작은 텍스트(포인터)로 보이면 `git lfs pull`.

| 에피소드 | 길이 | 내용 |
|---|---|---|
| `2026-11-17_2035_hamin/ep_0001` | 54.5 s | **깨끗함.** 팔 399.7 / 300.0 Hz, 손·글러브 49.1, 촉각 90.9, 카메라 30.0 Hz, 끊김 0 |
| `2026-11-17_1852_hamin/ep_0001` | 71.1 s | USB 랜 끊김 2번 (팔 공백 6.4 s, 3.1 s). 끊김 처리와 팔 추종 분석에 쓴다 |

공통: `task=sync_test`, `mount=wrist_flip` (LEAP 90° 장착 + `omy_ai_wrist_flip`), Paxini 보드 하나(`tactile_a`, 모듈 8개).
촉각 영점(Z)을 누르지 않았고(`tactile_zero` 비어 있음), 손가락에 닿은 것이 없어 힘은 0 이다.

## 빠진 것

- **손목 카메라 영상** `cam_wrist.mjpeg` (각 약 55 MB)는 올리지 않았다. 프레임 시각은 `cam_wrist.npz` 에 있다.
  원본은 User PC `jiwoo-950QDB` 의 `~/data/shape_up/sync_test/<세션>/ep_0001/` 에 있다.
- 짧거나 수정 전인 에피소드(`1749_hamin/ep_0001`, `2035_hamin/ep_0002·0003`)는 뺐다.

## 파일

| 파일 | 내용 |
|---|---|
| `session.json` | 녹화 당시 설정 전체 (`rig.yaml`), git commit |
| `ep_0001/episode.json` | 길이, 결과, flags (끊김 횟수 등), 스트림 메타 |
| `ep_0001/events.jsonl` | 녹화 중 이벤트 (mark, 끊김) |
| `ep_0001/<stream>.npz` | 스트림별 값과 시각 (`t_recv_ns`, `t_src_ns`, `seq`) |
