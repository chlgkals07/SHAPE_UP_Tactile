# VLA Architectue and Using Tactile in Vla

**VLA architecure**

<br> 

diffusion policy: https://arxiv.org/abs/2303.04137 : 엄밀히 말하면 vla는 아니지만 최근 vla 아키텍처의 시초임. 

pi0: https://arxiv.org/abs/2410.24164v4

pi05: https://arxiv.org/abs/2504.16054

gr00t: https://arxiv.org/abs/2503.14734 : pi와 gr00t는 아키텍처 차이는 거의 없고 vlm을 frozen 하는지 안 하는지 차이가 있음. report 되는 논문들 보면 pi가 gr00t보다 성능이 일반적으로 좋긴 함. 하지만 무조건 pi를 사용할 필요는 없고 무엇을 쓰든 우리 방법론이 효과적이다라는 것을 보일 수만 있으면 됨. 그래서 무조건 vla를 사용할 필요는 없음. 

<br> 

위 논문 4개는 모든 내용을 읽어볼 필요는 없고, 
데이터 구성, 모델 input output, 모델 아키텍처, Finetuning 어떤 식으로 하는지 등만 보아도 될 거 같아. 
그냥 최근 robot learning 쪽에서는 이런 식으로 모델을 짜고 로봇을 제어하는구나 공부하는 정도. 

<br> 

**Using Tactile in VLA**

<br> 

tactile-vla: https://arxiv.org/abs/2507.09160 : tactile을 vla에 거의 처음으로 적용한 논문이고 pi에 적용. 

FTP-1: https://arxiv.org/abs/2606.13102 : tactile pretrained expert를 pi와 결합한 pretrained tactile vla. dexterous hand 사용.

Canonical Representation and Force-Based Pretraining of 3D Tactile for Dexterous Visuo-Tactile Policy Learning: https://arxiv.org/abs/2409.17549 : 하민이가 처음에 알려준 논문. vla는 아니지만 우리 세팅이랑 유사해서. 

<br> 

**Finetuning VLA on Arm + Dexterous Hand (팔 + 손 조합)**

<br>

- [DexVerse (arXiv:2607.08751)](<DexVerse(2026 arXiv).md>) : 3개 팔과 6개 다지 핸드(**LEAP Hand 포함**)를 지원하는 벤치마크. $\pi_{0.5}$를 다지 핸드 환경에 직접 파인튜닝/평가한 핵심 레퍼런스.
- [VisForce (arXiv:2609.25785)](<VisForce(2026 arXiv).md>) : **UR10 팔 + Inspire 5지 핸드** 조합. $\pi_{0.5}$에 손가락 끝 3축 힘 정보를 카메라 영상에 시각적으로 그라운딩(Visual Grounding)하여 섬세한 파지(계란, 치약) 및 페그 삽입 성공.
- [GR00T N1 (arXiv:2503.14734)](<GR00T-N1(2025 arXiv).md>) : NVIDIA의 휴머노이드 VLA 파운데이션 모델. **22-DoF Sharpa Wave 다지 촉각 핸드**, Shadow Hand, Allegro Hand 등 다지 핸드를 네이티브 지원하며 DiT 기반 실시간(50Hz) 액션 생성.
- **실무 파인튜닝 파이프라인 (OpenPI + 우리 팀 구성: ROBOTIS OMY + LEAP Hand)**:
  - **우리 팀 하드웨어 구성**: **ROBOTIS OMY (6 DoF 팔)** + **LEAP Hand (16 DoF 다지 핸드)** = **총 22 DoF 액션 공간**.
  - **생태계 시너지**: OMY(DYNAMIXEL-Y)와 LEAP Hand(DYNAMIXEL XC330)가 모두 **DYNAMIXEL 프로토콜**을 기반으로 하므로, 제어 인터페이스(DYNAMIXEL SDK / `ros2_control`) 통합 및 동기화가 매우 용이함.
  - **OpenPI 매핑**: OpenPI의 기본 최대 액션 차원(32차원)에 22차원(OMY 6 + LEAP 16)이 네트워크 구조 변경 없이 제로 패딩(10차원)으로 즉시 매핑 가능.
  - **데이터 수집 및 배포**: OMY의 ROS 2 Jazzy (`ros2_control`, 최대 400Hz) 인터페이스와 LEAP Hand의 텔레오퍼레이션(RIO/LeRobot) 파이프라인을 연동하여 $\pi_{0.5}$ 파인튜닝 데이터 구축에 유리.
