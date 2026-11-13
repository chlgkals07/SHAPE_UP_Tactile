# SHAPE_UP

LEAP Hand를 기반으로 adaptive grasping과 tactile/proprioceptive manipulation을 연구합니다.

현재 상태 (2026-11-13):
- Manus 글러브 → LEAP Hand 텔레옵 약 80% (LEAP 90° 장착 + `omy_ai_wrist_flip`). 남은 것은 리타겟팅/IK 보정과 엄지.
- 손목 카메라 D405, Paxini 촉각 센서 연동 확인 (11/12).
- 다음: 팔·손·촉각·카메라를 같은 시간축으로 기록하는 자체 녹화 프로그램 (LeRobot 형식). Cyclo는 보류.

**현장 절차는 [all-in-one 가이드](docs/manus_teleop_guide.html)** (같은 내용 [md](docs/manus_teleop_guide.md)).

## 코드
- [`user_pc/`](user_pc/README.md): LEAP Hand 텔레옵 구현 (키보드 / OMY leader 그리퍼 / Manus 글러브)
- [`third_party/paxini`](third_party/paxini/README.md): Paxini GEN3 촉각 센서 SDK (커뮤니티 래퍼)
- `third_party/manus`: Manus SDK와 ROS 2 노드
- `third_party/open_manipulator`: ROBOTIS OMY 서브모듈 (`git submodule update --init`)

## 문서
- 설계: [LEAP–OMY 텔레옵 spec](docs/superpowers/specs/2026-10-08-leap-omy-teleop-design.md), [plan](docs/superpowers/plans/2026-10-09-leap-omy-teleop.md)
- 실물 시험: [10/09 계획](docs/field-test/2026-10-09-omy-leap-field-test.md), [10/09 결과](docs/field-test/2026-10-09-results.md), [11/03 결과](docs/field-test/2026-11-03-results.md), [11/12 결과](docs/field-test/2026-11-12-results.md)
- 데이터 수집: [OMY 시연 runbook](docs/data_preparation/omy_demonstration_runbook.md), [수집 가이드](docs/data_preparation/omy_demonstration_collection_guide.html)

## 연구
- [촉각센서 하드웨어 사전 검토](research/README.md)
- [선행연구 정리](prior-work/README.md)
- [Tactile DUST-like 아이디어](research/idea/tactile_DUST-like_idea.html)
