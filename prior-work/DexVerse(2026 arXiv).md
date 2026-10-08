[← 선행연구 목록](README.md)

# DexVerse: A Modular Benchmark for Multi-Task, Multi-Embodiment Dexterous Manipulation

- 링크: https://arxiv.org/abs/2607.08751 , https://dexverse-benchmark.github.io/
- 읽은 사람: 신지우
- 날짜: 26.10.08
- 학회/게재: arXiv 2026.07 (UNC-Chapel Hill, HKU, UC Berkeley)

---

# 내용

### 1. 해결하고자 한 문제
- 기존 로봇 조작 벤치마크는 단일/고립된 태스크에 치우쳐 있거나, 엔드이펙터(그리퍼 등) 다양성이 부족하고 시각적 변화(조명, 텍스처, 시점) 제어가 어려움.
- 범용 다지 핸드(Dexterous Hand) 제어 정책을 구축하고 평가하기 위해서는 다양한 로봇 팔 및 다지 핸드 조합(Multi-Embodiment), 복합 시각 조건, 장기(Long-horizon) 태스크를 포괄하는 표준 벤치마크가 부재함.

### 2. 선행 연구와 차별점
- **대규모 태스크 스펙트럼**: 파지, 물체 재배치, 관절형 물체 조작, 도구 사용, 양손 협동, 접촉 풍부(Contact-rich) 행동 등 100개 태스크 지원.
- **다양한 로봇 팔 및 핸드 지원**: 3개 로봇 팔과 **6개 다지 핸드(LEAP Hand, Allegro Hand, Shadow Hand, Inspire Hand, Sharpa Wave, WUJI Hand)** 지원.
- **최신 VLA 파운데이션 모델 벤치마크**: Diffusion Policy (DP), DP3, OpenVLA뿐만 아니라 **Physical Intelligence의 $\pi_{0.5}$**를 포함하여 다지 핸드 환경에서 직접 파인튜닝/평가 진행.
- VR 기반 텔레오퍼레이션 인터페이스를 통해 수집된 3,180개의 고품질 다중 모달 시연(RGB, Depth, Point cloud, Proprioception) 제공.

### 3. 방법론
- **모듈러 아키텍처**: 로봇 팔(Arm)과 다지 핸드(Hand) 조합을 자유롭게 스왑 가능한 시뮬레이션 환경 구축.
- **$\pi_{0.5}$ 파인튜닝 파이프라인**: 
  - OpenPI 기반 $\pi_{0.5}$ 백본(PaliGemma 3B + Flow Matching Action Expert)을 사용.
  - 고자유도 핸드(LEAP Hand 16-DoF 등) 액션 공간을 Flow Matching 헤드에 매핑하여 언어 지시어 기반 다지 조작 정책 학습.
  - 다양한 텍스처, 조명, 카메라 뷰포인트 변화를 주어 시각운동(visuomotor) 일반화 성능 평가.

### 4. 결과
- $\pi_{0.5}$와 같은 대규모 VLA 모델이 단순한 2지 그리퍼 대비 다지 핸드(LEAP, Allegro 등)의 복합 접촉 태스크에서 여전히 상당한 일반화 격차(Generalization Gap)와 시각적 강건성 한계를 보임을 규명.
- 다지 핸드 고유의 높은 자유도와 미세 접촉 제어를 성공시키기 위해 정밀한 상태 피드백 및 도메인 적응 기법이 필수적임을 실험적으로 증명.

### 5. 하드웨어 스펙
- **로봇 팔 (Arm)**: Franka Emika Panda, UR10, xArm 등 3종
- **다지 핸드 (Dexterous Hand)**: **LEAP Hand (16-DoF)**, Allegro Hand (16-DoF), Shadow Hand (20-DoF), Inspire Hand, Sharpa Wave, WUJI Hand (총 6종)
- **센서 구성**: Wrist/Front RGB-D 카메라, Point Cloud, 관절 위치/속도 센서

---

# 우리 연구와의 연결

### 1. 한계점 & 의문점
- 벤치마크 위주의 연구이므로 시뮬레이션 환경에서의 대규모 태스크 평가에 집중되어 있으며, 실물(Real-world)에서의 미세 촉각(Tactile) 피드백 통합은 다루지 않음.
- $\pi_{0.5}$의 액션 출력(Chunking)이 복잡한 접촉 천이(Contact Transition) 상황에서 반응 지연(Latency)을 유발할 수 있음.

### 2. 우리 프로젝트(SHAPE_UP) 적용점 / 아이디어
- **직접적인 벤치마크 참조점**: 우리가 사용하려는 **Arm + LEAP Hand** 조합에 $\pi_{0.5}$를 적용한 대표적인 레퍼런스로, OpenPI 코드베이스와 액션 공간 매핑 방식을 그대로 참고 가능.
- VR 텔레오퍼레이션 데이터셋 및 태스크 정의(Contact-rich manipulation)를 우리 실물 실험(PaXini 촉각 센서 장착 LEAP Hand) 태스크 설계에 직접 활용 가능.
