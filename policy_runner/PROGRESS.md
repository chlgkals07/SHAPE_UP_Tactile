# policy_runner 진행 상황

## 현재 (2026-11-21, `feat/policy-runner`, merge 전)

- Stage A (관측 정렬), Stage B (가짜 서버·dry-run·UI·CLI) 구현 완료. `leap_teleop --source policy` 와 Control Hub "정책" 페이지까지 구현했다.
- 고정 평가 통과: 수락 테스트 83, leap_teleop 170, 의도적 버그 12/12. control_hub 1 실패는 Linux 전용 `/proc` 테스트다(main 과 동일). [결과](../docs/results/2026-11-21-policy-runner-eval.md)
- 실제 프로세스로 확인한 것: 가짜 rig + 가짜 서버 60 s (고장 주입 포함) 감사기 0 위반, 손 UDP → leap_teleop dry-run 의 live/hold/release, Hub iframe 화면.

## 다음 할 일

1. Ubuntu User PC 에서 `./audit/run_all.sh` 와 60 s soak 를 다시 돈다. tmux 테스트와 tick 정밀도가 이 Mac 과 다를 수 있다. late 비율과 예정 대비 지연 p99 를 결과 문서에 추가한다.
2. Stage C1: 실제 π0.5 지연 측정. 지금 `probe` 는 우리 rig 모양의 요청(state 22, cam_wrist/cam_ext)만 보낸다. 그래서 ALOHA checkpoint(`--env ALOHA`) 서버에는 맞지 않는다. 방법은 둘이다. `probe --example aloha` 를 추가하거나, 서버 쪽 openpi 의 `examples/simple_client` 로 잰다. 어느 쪽인지 정해야 한다.
3. Stage C2: openpi-RLT 에 `OmyLeapInputs/Outputs`, `pi05_omy_leap`. serving 할 때 policy metadata 에 `manifest` 를 넣어야 한다(runner 가 시작할 때 대조한다).
4. 실물 손 모드 전에 정할 것: 정책 모드의 `--release-timeout`·`--safe-pose`.

## 미해결

- 팔 명령 경로 (follower topic, zenoh publisher) 미정. `mode: hand` 는 손만 보낸다.
- 11/17 재생의 손 state 불일치 수는 테스트가 기준(5% 미만)만 확인한다. 실제 수는 출력하지 않는다.
- 이 Mac 의 백그라운드 대기 오차가 p50 약 9 ms 다. jitter 한도 10 ms 에 가까워서 late 가 3.7% 났다.

## 시도했다가 바꾼 것

- chunk 시작 시각을 실제 깬 시각으로 잡았다. 그러자 행 간격이 dt − jitter 보다 짧아졌다(23.318 ms). 격자 시각으로 바꿨다 (`9b73f4a`).
- 지터 대응으로 행 번호를 반올림했다. 격자 기준으로 바꾸면서 필요 없어져 되돌렸다.
- 고정 동일성 테스트의 latency 경우가 아직 도착하지 않은 프레임을 요구했다. 도착한 프레임 기준으로 바꿨다 (`0060e86`).
