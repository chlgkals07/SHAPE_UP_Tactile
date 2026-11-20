# 의도적 버그 목록 (고정)

구현 뒤 각 항목을 `audit/mutants/Mxx.patch` 로 만든다. 패치 하나를 적용했을 때 수락 테스트(`tests/acceptance`) 나
감사기 중 하나 이상이 실패해야 한다. 하나라도 전부 통과하면 평가 실패다. 패치는 항목에 적힌 동작만 바꾼다.

| id | 바꾸는 동작 |
|---|---|
| M01 | 정렬이 `t_obs_ns` 이하 샘플 대신 각 stream 의 `latest()` 를 쓴다 |
| M02 | 손 state 후보에서 `pos` 가 유한하지 않은 샘플을 거르지 않는다 |
| M03 | infer timeout 뒤 연결을 닫지 않는다 |
| M04 | `check_reply` 가 유한성(NaN/inf)을 보지 않는다 |
| M05 | 늦은 tick 에서 밀린 행을 모두 한꺼번에 보낸다 |
| M06 | 행 i 의 예정 시각을 채택 시각이 아닌 응답 도착 시각(`t_reply_ns`) 기준으로 잡는다 |
| M07 | chunk 에서 K 개가 아니라 H 개 행을 실행한다 |
| M08 | 손 UDP 에 rad 를 deg 로 바꾸지 않고 보낸다 |
| M09 | 카메라 프레임의 JPEG 왕복을 뺀다 |
| M10 | READY 상태에서도 tick 이 행을 보낸다 |
| M11 | 첫 행과 측정 상태 차이 검사를 뺀다 |
| M12 | 오래된 chunk(`chunk_max_delay`) 검사를 뺀다 |
