# 선행연구

## Leap Hand & Hardware — 최하민

- 자료를 추가할 때: [논문 또는 자료 제목](template.md) — 한 줄 메모


## Tactile Robot Learning — 임세화

- [Dexterity from Touch: Self-Supervised Pre-Training of Tactile Representations with Robotic Play](<T-DEX(2023 CoRL).md>) - pretrained tactile encoder로 적은 양의 tactile data 문제 해결
- [Reactive Diffusion Policy: Slow-Fast Visual-Tactile Policy Learning for Contact-Rich Manipulation](<RDP(2025 RSS).md>) - tactile 정보 도입해서 Action Chunking의 문제 해결
- [Sparsh: Self-supervised touch representations for vision-based tactile sensing](<Sparsh(2024 CoRL).md>) - multi sensor datase and pretrained encoder. compare different types of SSL mechanism
- [AnyTouch: Learning Unified Static-Dynamic Representation across Multiple Visuo-tactile Sensors](<AnyTouch(2025 ICLR).md>) - multi modal multi sensor dataset and pretrained encoder. propose MAE modeling and alignment
- [RoboPack: Learning Tactile-Informed Dynamics Models for Dense Packing](<RoboPack(2024 RSS).md>) - learning "dynamics model" using tactile sensing
- [Tactile-VLA: Unlocking Vision-Language-Action Model's Physical Knowledge for Tactile Generalization](<Tactile-VLA(2025 arXiv).md>) - VLA에 tactile sensing 통합. tactile 정보와 VLM의 prior knowledge, semantic understanding 이용.
- [VLA-Touch: Enhancing Vision-Language-Action Models with Dual-Level Tactile Feedback](<VLA-touch(2026 RA-L).md>) - dual level로 tactile 이용. planning과 refinement controller.


- Canonical Representation and Force-Based Pretraining of 3D Tactile for Dexterous Visuo-Tactile Policy Learning(2025 ICRA) - LEAP hand + Paxini. Paxini tactile sensor representation 연구 
- Adaptive Visuo-Tactile Fusion with Predictive Force Attention for Dexterous Manipulation(2025 IROS) - vision과 tactile의 attention을 어떻게 할까에 대한 연구
- FTP-1: A Generalist Foundation Tactile Policy Across Tactile Sensors for Contact-Rich Manipulation(2026 CoRL) - pi05 + Tactile Expert. Pretraining Tactile VLA policy이고 최근 추세로는 tactile VLA 연구에서 baseline으로 많이 사용. 
- OmniVTLA: Vision-Tactile-Language-Action Models With Semantic-Aligned Tactile Sensing(2026 RA-L) - clip처럼 tactile도 align해서 encoder 만들고 vla에 사용.

  
기록용(전부 읽진 못한 논문들. abstract, figure 등은 확인. ) 
- TacForcing: Streaming Action Generation with Execution‑Time Tactile Feedback(2026.09 arXiv) - high frequency tactile input에 대해서 temporal alignment하기 위해서 action expert의 denoising 및 chunking을 streaming 방식으로 변형. 
- TouchWorld: A Predictive and Reactive Tactile Foundation Model for Dexterous Manipulation(2026.07 arXiv) - WAM + Future Tactile Prediction 
- DexTac: Learning Contact-aware Visuotactile Policies via Hand-by-hand Teaching(2026 IEEE T-SE) - 손가락에서도 어느 부위에 접촉하는지 그 local한 작은 영역을 따서 policy를 학습하는 느낌? VLA는 아니고, 좀 더 HW, dexterity, physics에 가까운 논문인듯.  
- FARM: Tactile-Conditioned Diffusion Policy for Force-Aware Robotic Manipulation(2026 ICRA) - Policy가 gripper의 force도 예측. 
- N0-VTLA: Scaling Vision–Tactile–Language–Action Model with Latent Tactile Tokens(2026.07 arXiv) - predictive tactile latent를 예측하고 그것을 action expert가 사용. LeJEPA 스타일과 비슷하다고 함. 
- Contact-Grounded Policy: Dexterous Visuotactile Policy with Generative Contact Grounding(2026 RSS) - future tactile과 robot state를 예측하고, 그것으로 실제 contact이 어떻게 될 지 매핑해서 최종적인 predicted target robot state를 예측(계산). 흥미로워 보임.  


## VLA & Foundation Models on Dexterous Hands (팔 + 다지 핸드) — 신지우

- [DexVerse: A Modular Benchmark for Multi-Task, Multi-Embodied Dexterous Manipulation](<DexVerse(2026 arXiv).md>) - 3개 팔과 6개 다지 핸드(LEAP Hand 포함) 지원. $\pi_{0.5}$를 다지 핸드에 파인튜닝/벤치마킹한 대표 연구
- [VisForce: Visual Grounding of Current and Desired Forces for Goal-Conditioned Dexterous Manipulation](<VisForce(2026 arXiv).md>) - UR10 팔 + Inspire 5지 핸드 조합. $\pi_{0.5}$에 손가락 끝 3축 힘 정보를 시각적 큐로 주입하여 섬세한 힘 제어 파지 성공
- [GR00T N1: An Open Foundation Model for Generalist Humanoid Robots](<GR00T-N1(2025 arXiv).md>) - NVIDIA의 휴머노이드 VLA 모델. Sharpa Wave 5지 촉각 핸드(22 DoF) 등 다지 핸드 네이티브 지원 및 50Hz 실시간 제어


## Teleoperation & Data Collection Pipeline (데이터 수집) — 신지우

- [ROBOTIS OMY + LEAP Hand 텔레오퍼레이션 및 데이터 수집 파이프라인 검토](teleoperation_pipeline_review.md) - 리더암(OMY-L100) 손목 체결 + 마누스 글러브, IK 방식 비교 및 촉각(PaXini)/LeRobot 동기화 아키텍처
