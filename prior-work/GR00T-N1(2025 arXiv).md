[← 선행연구 목록](README.md)

# GR00T N1: An Open Foundation Model for Generalist Humanoid Robots

- 링크: https://arxiv.org/abs/2503.14734 , https://research.nvidia.com/labs/gear/gr00t/
- 읽은 사람: 신지우
- 날짜: 26.10.08
- 학회/게재: arXiv 2025.03 (NVIDIA GEAR Team, Linxi "Jim" Fan & Yuke Zhu et al.)

---

# 내용

### 1. 해결하고자 한 문제
- 휴머노이드 로봇 및 복합 조작 플랫폼이 인간 환경에서 다양한 도구와 물체를 다루기 위해서는 다자유도 로봇 팔과 다지 핸드(Dexterous Hand)를 통합 제어할 수 있는 범용 로봇 파운데이션 모델이 필요함.
- 기존 모방 학습(Imitation Learning) 모델들은 단일 로봇 형태(Embodiment)나 좁은 도메인에 갇혀 있어, 복잡한 다지 조작 및 새로운 환경에 대한 적응력이 부족함.

### 2. 선행 연구와 차별점
- **이중 시스템 (Dual-System) 아키텍처**:
  - **System 2 (Thinking)**: 멀티모달 환경 해석 및 언어 지시어 분해를 담당하는 VLM (NVIDIA Cosmos / Eagle 백본).
  - **System 1 (Doing)**: 50Hz 이상의 실시간 유연한 모터 제어 액션을 생성하는 확산 트랜스포머(Diffusion Transformer, DiT).
  - 두 시스템이 엔드투엔드로 결합되어 실시간 제어와 고수준 의미 이해를 동시 달성.
- **다지 핸드(Dexterous Hand) 네이티브 지원**:
  - 20~22 DoF 수준의 고자유도 다지 핸드(Sharpa Wave 5지 촉각 핸드, Shadow Hand 등)를 고려한 액션 토크/위치 인터페이스 설계.
  - 대규모 인간 1인칭 비디오(EgoScale) 및 Isaac Teleop(MANUS 글러브 등) 데이터를 사전학습에 결합.

### 3. 방법론
- **데이터 파이프라인**: 실제 로봇 궤적 + 대규모 1인칭 인간 비디오 + Isaac Sim 기반 합성 데이터의 이종 혼합(Heterogeneous mixture) 학습.
- **다양한 로봇 형태 지원 (Cross-Embodiment)**:
  - Fourier GR-1 휴머노이드, Unitree H2 Plus(Sharpa Wave 다지 핸드 탑재) 등 실물 로봇 배포.
  - NVIDIA Isaac Lab을 통한 시뮬레이션 환경(Franka / Shadow Hand / Allegro Hand) 지원.

### 4. 결과
- 표준 시뮬레이션 벤치마크에서 기존 모방 학습 베이스라인들을 큰 폭으로 능가.
- Fourier GR-1 및 다지 핸드 로봇에서 언어 지시 기반 양손 조작(Bimanual Manipulation) 및 정밀 조작을 높은 데이터 효율성으로 성공.

### 5. 하드웨어 스펙
- **로봇 본체 / 팔**: Unitree H2 Plus, Fourier GR-1 휴머노이드, Franka Emika Panda 등
- **다지 핸드 (Hand)**: **Sharpa Wave (22-DoF 5지 촉각 핸드)**, Shadow Hand (20-DoF), Allegro Hand (16-DoF)
- **센서 구성**: Head/Wrist 카메라, 촉각 어레이(Sharpa Wave 통합형), 관절 상태

---

# 우리 연구와의 연결

### 1. 한계점 & 의문점
- NVIDIA Isaac 생태계(Isaac Sim, Isaac Lab, Omniverse)에 강하게 결합되어 있어 로컬 독립 환경에서 순수 파이썬/PyTorch 기반으로 가볍게 돌리기에는 인프라 요구사항이 높음.
- 파인튜닝 가중치 및 배포 파이프라인이 Physical Intelligence의 OpenPI 대비 상대적으로 무겁고 프레임워크 종속적임.

### 2. 우리 프로젝트(SHAPE_UP) 적용점 / 아이디어
- **아키텍처 비교 레퍼런스**: VLM을 Frozen하지 않고 System 1(DiT)과 결합하는 방식 vs OpenPI의 Flow Matching 방식을 비교 분석하는 데 중요한 기준점.
- **시뮬레이션 환경 활용**: 만약 Isaac Lab을 시뮬레이터로 사용할 경우, GR00T의 정책 가중치와 태스크 파이프라인을 다지 핸드(LEAP Hand) 시뮬레이션 학습의 베이스라인으로 활용 가능.
