# policy_runner 진행 상황

## 현재 (2026-11-21, `feat/policy-runner` + `feat/policy-runner-server-smoke`, merge 전)

- Stage A (관측 정렬), Stage B (가짜 서버·dry-run·UI·CLI) 구현 완료. `leap_teleop --source policy` 와 Control Hub "정책" 페이지까지 구현했다.
- 동작 검사(첫 행–측정 상태, 행 사이 차이)로 chunk 를 거부하던 것을 뺐다. 관절 범위·속도 제한은 LEAP 드라이버(clip·slew)가 맡는다. [결정](../docs/superpowers/plans/2026-11-20-policy-runner.md)
- 오래된 chunk 거부(`chunk_max_delay_ms`)와 늦은 행 한도(`tick_jitter_ms`)도 뺐다(openpi 예제와 같게). 재연결할 때도 manifest 를 비교하고, UI 상태 읽기를 lock 안으로 넣고, `probe` 가 서버 오류에서 traceback 대신 한 줄로 끝나게 했다.
- 정책 페이지에 LEAP 손 상태(live/hold/release, feedback 나이, LEAP 가 줄인 양, 명령–실측 차이)와 arm 뒤 tick 집계(보냄·late·hold)를 띄운다.
- 평가 통과: 수락 테스트 79, leap_teleop 170, 의도적 버그 10/10 (M11·M12 삭제). 가짜 서버 10 s soak 감사기 0 위반, late 0. control_hub 1 실패는 Linux 전용 `/proc` 테스트다(main 과 동일). [결과](../docs/results/2026-11-21-policy-runner-eval.md)
- 실제 프로세스로 확인한 것: 가짜 rig + 가짜 서버 60 s (고장 주입 포함) 감사기 0 위반, 손 UDP → leap_teleop dry-run 의 live/hold/release, Hub iframe 화면.
- Stage C 서버 연결: openpi-RLT `feat/omy-leap` 에 `OmyLeapInputs/Outputs` 와 `pi05_omy_leap` (metadata 에 manifest) 를 추가했다. 학습 안 한 pi05_base 로 serving 하고 GPU 서버 안에서 `probe`·`run` 으로 연결을 확인했다. manifest 일치, 응답 601/601 정상, 감사기 0 위반, RTT p50 74 ms, 첫 요청 JIT 36 s. chunk 는 학습 안 한 가중치라 모두 첫 행 검사로 거부됐다. [결과](../docs/results/2026-11-21-server-smoke.md)

## 다음 할 일

1. Ubuntu User PC 에서 `./audit/run_all.sh` 와 60 s soak 를 다시 돈다. tmux 테스트와 tick 정밀도가 이 Mac 과 다를 수 있다. late 비율과 예정 대비 지연 p99 를 결과 문서에 추가한다.
2. User PC 에서 ssh 터널로 `probe` 를 돌려 망 지연을 잰다. User PC 에 GPU 서버 ssh key 가 필요하다.
3. 영상이 있는 실데이터 수집 → norm stats → 학습. checkpoint 를 바꾸면 서버의 `OMY_LEAP_CHECKPOINT_ID`/`OMY_LEAP_NORM_STATS_ID` 와 실행기 manifest 를 같이 바꾼다. 그 뒤 실제 센서 dry-run(C3).
4. 정책 모드 LEAP 는 Hub 에서 `--release-timeout 5 --safe-pose fist` 로 띄운다(연속 timeout FAULT 3066.7 ms 보다 늦게 풀리게). 실물 미검증. 손이 hold·FAULT 에 어떻게 반응할지는 LEAP 제어기에서 다시 정한다(사용자 예정).
5. 정책 페이지 후보: 카메라 미리보기(Cyclo Intelligence 는 카메라 grid 와 3D action 미리보기를 띄운다).

## 미해결

- 팔 명령 경로 (follower topic, zenoh publisher) 미정. `mode: hand` 는 손만 보낸다.
- 11/17 재생의 손 state 불일치 수는 테스트가 기준(5% 미만)만 확인한다. 실제 수는 출력하지 않는다.
- 이 Mac 의 백그라운드 대기 오차가 p50 약 9 ms 다. jitter 한도 10 ms 에 가까워서 late 가 3.7% 났다.

## 시도했다가 바꾼 것

- chunk 시작 시각을 실제 깬 시각으로 잡았다. 그러자 행 간격이 dt − jitter 보다 짧아졌다(23.318 ms). 격자 시각으로 바꿨다 (`9b73f4a`).
- 지터 대응으로 행 번호를 반올림했다. 격자 기준으로 바꾸면서 필요 없어져 되돌렸다.
- chunk 를 첫 행–측정 상태(0.15 rad)·행 사이(0.05 rad) 한도로 거부했다. 한도가 데이터 근거 없이 정한 값이었고 11/17 시연이 자주 넘어서, 정상 동작을 막을 수 있었다. 거부를 빼고 장치 제어기에 맡겼다.
- 고정 동일성 테스트의 latency 경우가 아직 도착하지 않은 프레임을 요구했다. 도착한 프레임 기준으로 바꿨다 (`0060e86`).
