# SHAPE_UP

LEAP Hand를 기반으로 adaptive grasping과 tactile/proprioceptive manipulation을 연구합니다.

현재 상태 (2026-10): OMY leader 그리퍼로 LEAP Hand v1을 텔레옵하는 데까지 실물 검증 완료 (10/09).
다음 단계는 손 입력을 Manus 글러브로 바꾸는 것입니다.

## 코드
- [`user_pc/`](user_pc/README.md): LEAP Hand 텔레옵 구현 (키보드 / OMY leader 그리퍼)
- `third_party/open_manipulator`: ROBOTIS OMY 서브모듈 (`git submodule update --init`)

## 문서
- 설계: [LEAP–OMY 텔레옵 spec](docs/superpowers/specs/2026-10-08-leap-omy-teleop-design.md), [plan](docs/superpowers/plans/2026-10-09-leap-omy-teleop.md)
- 실물 시험: [10/09 계획](docs/field-test/2026-10-09-omy-leap-field-test.md), [10/09 결과](docs/field-test/2026-10-09-results.md)
- 데이터 수집: [OMY 시연 runbook](docs/data_preparation/omy_demonstration_runbook.md), [수집 가이드](docs/data_preparation/omy_demonstration_collection_guide.html)

## 연구
- [촉각센서 하드웨어 사전 검토](research/README.md)
- [선행연구 정리](prior-work/README.md)
- [Tactile DUST-like 아이디어](research/idea/tactile_DUST-like_idea.html)
