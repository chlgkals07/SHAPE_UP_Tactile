[← 선행연구 목록](README.md)

# VisForce: Visual Grounding of Current and Desired Forces for Goal-Conditioned Dexterous Manipulation

- 링크: https://arxiv.org/abs/2609.25785
- 읽은 사람: 신지우
- 날짜: 26.10.08
- 학회/게재: arXiv 2026.09 (Jung-Woo Lee, Soo-Chul Lim)

---

# 내용

### 1. 해결하고자 한 문제
- VLA(Vision-Language-Action) 모델을 다지 핸드(Dexterous Hand) 조작에 적용할 때, 접촉력(Contact Force)을 단순한 독립 상태 벡터(Vector)로 입력하면 힘의 공간적 위치(어느 손가락 끝에서 어떤 힘이 작용하는지)를 모델이 명시적으로 인식하기 어려움.
- 그 결과, 계란이나 치약 튜브처럼 깨지기 쉽거나 변형 가능한 물체를 섬세하게 다룰 때 필요한 정밀한 힘 조절(Force-conditioned Grasping)에 실패함.

### 2. 선행 연구와 차별점
- **시각적 힘 그라운딩 (Visual Force Grounding)**: 현재 힘(Current Force)과 목표 힘(Desired Force)을 별도 숫자 벡터가 아닌, 손목 카메라(Wrist Camera) 영상 속 실제 손가락 끝 위치에 시각적 큐(Visual Cue, 화살표/마커 등) 형태로 직접 렌더링.
- **$\pi_{0.5}$ 기반 VLA 확장**: $\pi_{0.5}$ 계열 VLA 아키텍처에 시각화된 힘 정보를 Goal-conditioned Cross-Attention으로 결합하여, VLM 백본의 사전 지식을 유지하면서 힘 제어 행동을 생성.
- 별도의 복잡한 촉각 인코더 아키텍처 추가 없이 표준 비전 백본을 그대로 활용 가능.

### 3. 방법론
- **Visual Grounding Pipeline**:
  - Wrist 카메라 이미지와 Task-specific Goal 이미지 상의 손가락 끝 좌표에 측정된 3축 힘/목표 힘을 시각적 화살표로 렌더링.
  - VLA 모델이 시각-공간적 관계(Spatial correspondence)를 자연스럽게 학습하도록 유도.
- **Goal-Conditioned Cross-Attention**:
  - 현재 시각 관측(힘 정보 포함)과 목표 상태(원하는 힘 상태 포함)를 교차 어텐션으로 매핑하여 힘 인식형 액션(Force-aware action) 예측.

### 4. 결과
- **힘 비례 파지(Force-conditioned Grasping)**:
  - 계란(Egg) 파지 및 들어올리기: 성공률 70%
  - 치약 튜브(Toothpaste tube) 파지: 성공률 80%
  - 원하는 목표 힘이 증가함에 따라 손가락 끝 파지력이 선형적으로 정밀하게 비례 증가함을 확인.
- **복합 조작 태스크**:
  - 컵 꽂기 / 병 따르기 (Cup insertion / Bottle pouring): 70%
  - 집게 활용 빵 전달 (Tong-assisted bread transfer): 55%
  - 슬립 조절 페그 인 홀 (Slip-modulated peg-in-hole): 40%

### 5. 하드웨어 스펙
- **로봇 팔 (Arm)**: UR10 6-DoF 협동 로봇 팔
- **다지 핸드 (Hand)**: Inspire RH56F1 (5지 다지 핸드)
- **센서 구성**: Wrist RGB 카메라, 손가락 끝 3축 힘/촉각 센서

---

# 우리 연구와의 연결

### 1. 한계점 & 의문점
- 힘 정보를 2D 이미지 평면에 렌더링하는 방식이므로, 손가락이 물체 뒤로 가려지는 심한 오클루전(Occlusion) 상황에서 시각적 큐가 어떻게 동작하는지 추가 검증 필요.
- 촉각 어레이의 고차원 분포(예: PaXini의 8개 센서, 수십 개 Taxel)를 모두 화살표로 그리기에는 시각적 복잡도가 올라갈 수 있음.

### 2. 우리 프로젝트(SHAPE_UP) 적용점 / 아이디어
- **강력한 아이디어**: 우리 팀이 준비 중인 PaXini 3축 촉각 센서의 분산 힘 벡터를 $\pi_0 / \pi_{0.5}$에 입력할 때, 별도의 복잡한 Tokenizer 대신 **손목 카메라 뷰에 힘 벡터 히트맵/화살표를 프로젝션하는 방식**을 매우 효과적인 대안으로 벤치마킹할 수 있음.
- 팔(Arm) + 다지 핸드(Inspire) 조합에 $\pi_{0.5}$를 미세조정하여 섬세한 파지/조작을 실물에서 성공시킨 최신 핵심 레퍼런스.
