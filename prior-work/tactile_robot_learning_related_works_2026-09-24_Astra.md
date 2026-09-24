# tactile_robot_learning_related_works_2026-09-24_Astra

This markdown was written by Astra. 

일단 아스트라로 찾아둔 목록 공유합니다~

# Tactile × Robot Learning / VLA: Related Works 조사

조사 기준일: 2026-09-24 · 대상: 촉각 연구를 시작하는 robot learning / VLA 연구팀

## 1. 요약과 범위

VLA는 필수 조건이 아니라 선호 분야로 두었다. 센서 모델, 수량, 장착 위치와 로봇 구성이 미정이므로 특정 제품이나 LEAP Hand 호환성을 전제로 논문을 제외하지 않았다. 핵심 문헌 21편, 2025년 말–2026년 후속 문헌 9편, 배경·인접 문헌 6편을 구분했다.

가장 먼저 읽을 조합은 **T-Dex → Reactive Diffusion Policy → Sparsh → AnyTouch → RoboPack → Tactile-VLA → VLA-Touch → OmniVTA**다. 다지 조작이 확정되면 Rotating without Seeing, DexTouch, HATO를 앞당긴다.

이번 문헌군에서 확인되는 흐름은 다음과 같다. 이는 전체 분야의 계량적 추세 분석이 아니라 아래 논문들에 근거한 종합이다.

- 개별 작업·센서에 종속된 표현에서 여러 센서·작업을 활용한 표현 사전학습으로 확장: Sparsh, UniTouch, T3, AnyTouch, TacX.
- 촉각을 단순 추가 입력으로 넣는 방식에서 실행 중 접촉 변화에 대응하는 정책으로 확장: RDP, ViTaL, VLA-Touch, ImplicitRDP.
- 관측된 접촉뿐 아니라 미래 접촉을 예측하고 제어에 연결: RoboPack, DreamTacVLA, OmniVTA, UniTacVLA, ForeTac-VLA.
- 촉각을 행동 입력뿐 아니라 언어 grounding, 사람 시연, 힘 목표, 학습 시 supervision으로 활용: Octopi, Tactile-VLA, FeelTheForce, FARM, HapticVLA.

**출판 관점의 결론:** ‘VLA에 tactile token 추가’, ‘느린 정책 + 빠른 촉각 제어’, ‘미래 촉각 예측’만으로는 충분한 차별점이 아니다. 센서 교체·다지 접촉·새 물성·실패 복구 등 명확한 조건에서 기존 접근과 구별되는 가설이 필요하다.

### 조사·검증 방식과 한계

키워드 검색 후 대표 논문의 관련 연구, 공식 proceedings, arXiv의 현재 버전 및 저자 프로젝트/저장소를 따라 확장했다. 주요 검색어는 tactile robot learning, visuotactile policy, tactile VLA, tactile foundation model, tactile dexterous manipulation, slow-fast policy, tactile world model, tactile sensor transfer였다.

이는 **1차 선별·비교 보고서**이며 모든 논문의 본문·부록·코드를 동일한 깊이로 정독하거나 재현한 결과는 아니다. 세부 방법·실험을 확인한 문헌과 초록·공식 소개 중심으로 확인한 문헌을 아래에 구분한다. 최신 문헌은 추가 정독 대상으로 제시한다. 검색의 완전성이나 연구 아이디어의 신규성을 보증하지 않는다.

게재 상태는 다음처럼 읽는다.

- 학회/저널 명시: 공식 proceedings 또는 원문/저자 공개 정보에서 확인. 저자 정보만 확인한 경우 별도 표시.
- Preprint: 공개 원문은 확인했지만 이번 조사에서 정규 게재를 독립적으로 확인하지 못함. ‘미게재’나 ‘reject’를 의미하지 않음.
- CoRL 2024 논문의 PMLR 발행연도는 2025로 표시되는 경우가 있다. 행사연도와 서지연도를 혼동하지 않는다.
- 인용 수는 일관된 출처에서 비교 가능한 값을 확보하지 못해 기재하지 않았다. ‘고인용 순위’가 아니라 주요 게재처, 문제 중요도, 직접 관련성으로 선정했다.
- ‘코드 링크 확인’은 설치·실행·재현 성공을 뜻하지 않는다. ‘공개 예정’과 실제 링크를 구분했다.
- 서로 다른 작업에서 보고된 성공률이나 상대 개선율은 통합 순위로 비교하지 않았다.

## 2. 무엇을 같은 연구로 묶으면 안 되는가

| 구분 | 의미 | 조사 시 주의 |
| --- | --- | --- |
| 국소 촉각 | 손끝/피부의 접촉 분포, 변형, 압력, 전단 등 | 센서 종류·장착 면적·접촉 범위가 중요 |
| 외력/힘·토크 | 보통 6축 force/torque 신호로 전달된 외력을 관측 | ForceVLA 같은 연구를 촉각 이미지 모델과 동일시하지 않음 |
| 촉각 표현학습 | 촉각을 유용한 latent로 변환 | perception benchmark 개선이 closed-loop 조작 개선을 자동 보장하지 않음 |
| 촉각 언어모델 | 접촉/물성의 언어 설명·추론 | 행동을 출력하지 않으면 그 자체로 VLA는 아님 |
| 촉각 정책 | 촉각 관측에서 행동 또는 보정량 생성 | IL/RL, 제어 주기, action space를 함께 비교 |
| 학습 시에만 촉각 사용 | reward, teacher, distillation, 보조 예측 | 실행 중 실제 촉각 피드백을 쓰는 정책과 별도 비교 |

‘sensor-agnostic’이라는 표현도 범위를 확인해야 한다. 여러 **광학식** 촉각 센서 간 전이가 압력 배열·자기식 센서까지 포함하는 것은 아니다. TacX의 여러 tactile modality 역시 여러 제조사 센서 전이와는 다른 개념이다.

## 3. 핵심 문헌 21편

### A. 정책 학습·다지 조작·접촉 제어

#### A1. Dexterity from Touch: Self-Supervised Pre-Training of Tactile Representations with Robotic Play — T-Dex

- **서지/선정:** Guzey et al., CoRL 2023. 다지 촉각 학습의 입문 우선순위가 매우 높다.
- **방법·근거:** 2.5시간의 robotic play로 촉각 encoder를 자기지도 사전학습하고, 소수 시연에서 시각·촉각을 결합한 non-parametric imitation policy를 구성한다. 5개 다지 작업에서 비교한다.
- **하드웨어:** 공식 저장소 기준 Allegro Hand + XELA + Kinova. LEAP Hand 직접 지원으로 해석하면 안 된다.
- **우리 팀의 읽기 질문:** 새 센서에서 짧은 play pretraining이 end-to-end policy보다 데이터 효율적인가? 손끝만 계측한 경우에도 같은 표현이 유효한가?
- **확인 수준/공개:** 공식 초록·저장소 확인. encoder 학습과 실제 배포 코드 및 데이터 안내가 있다. non-parametric 방법의 커버리지·일반화는 정독 대상.
- **출처:** [논문·공식 서지](https://proceedings.mlr.press/v229/guzey23a.html), [공식 코드](https://github.com/irmakguzey/tactile-dexterity).

#### A2. Rotating without Seeing: Towards In-hand Dexterity through Touch

- **서지/선정:** Yin et al., RSS 2023. 촉각만으로 다지 제어가 가능한 조건을 이해하는 기반 연구.
- **방법·근거:** 손바닥·손가락 링크·손끝을 덮는 이진 접촉 센서와 simulation RL을 사용한다. 학습하지 않은 물체의 실제 in-hand rotation으로 전이한다.
- **촉각의 역할:** 고해상도 이미지가 아니라 넓은 부위의 touch/no-touch 정보로 접촉 상태를 제공한다.
- **우리 팀의 읽기 질문:** 센서 해상도보다 커버리지가 중요한 작업은 무엇인가? 손끝 센서 몇 개만으로 재현 가능한가?
- **확인 수준:** 공식 학회 초록 확인. simulation observation, randomization, tactile ablation은 정독 대상.
- **출처:** [RSS 공식 페이지](https://rss2023.github.io/rss2023-website/program/papers/036/).

#### A3. DexTouch: Learning to Seek and Manipulate Objects with Tactile Dexterity

- **서지/선정:** Lee et al., RA-L 2024; arXiv에서 저널·DOI 확인. 시각 가림을 넘어 탐색과 조작을 촉각으로 수행하는 연구.
- **방법·근거:** 시뮬레이션 RL로 학습한 다지 정책을 실제 로봇으로 옮겨, 시각 없이 위치가 변하는 물체를 찾고 조작한다.
- **중요한 전제:** 원문은 prior information이 있는 상황임을 명시한다. 아무 prior 없이 완전 미지 환경을 푸는 일반 정책으로 확대 해석하지 않는다.
- **우리 팀의 읽기 질문:** tactile history가 탐색·접촉 확인·조작 사이에서 어떤 역할을 하는가?
- **확인 수준:** 원문 초록·게재 메타데이터 확인. 구체적인 센서 배치와 sim-to-real 조건 추가 정독 필요.
- **출처:** [논문](https://arxiv.org/abs/2401.12496), [저널 DOI](https://doi.org/10.1109/LRA.2024.3478571).

#### A4. Learning Visuotactile Skills with Two Multifingered Hands — HATO

- **서지/선정:** Lin et al., 2024 preprint. 다지·양팔 IL 프로젝트의 데이터 수집 및 시스템 설계에 직접 관련.
- **방법·근거:** HATO teleoperation 시스템으로 시각·촉각 시연을 수집하고 장기·정밀 조작을 학습한다. 데이터량·감각 모달리티·시각 전처리의 영향을 비교한다.
- **하드웨어:** 저자 프로젝트는 촉각이 있는 PSYONIC Ability Hands와 UR5e 관련 구성을 설명한다. LEAP Hand 전용 시스템이 아니다.
- **우리 팀의 읽기 질문:** 다지 retargeting, 손–팔 동기화, 촉각 시연 수집에서 실제 비용이 어디에 드는가?
- **확인 수준/공개:** 초록·프로젝트 확인. 코드·데이터 링크 존재. 양팔 구성을 그대로 복제할 필요는 없다.
- **출처:** [논문](https://arxiv.org/abs/2404.16823), [프로젝트·코드·데이터](https://toruowo.github.io/hato/).

#### A5. Reactive Diffusion Policy: Slow-Fast Visual-Tactile Policy Learning for Contact-Rich Manipulation — RDP

- **서지/선정:** Xue et al., RSS 2025. 이번 조사에서 정책 설계 우선순위가 가장 높은 논문 중 하나.
- **방법·근거:** 느린 latent diffusion policy가 action chunk를 생성하고, 빠른 asymmetric tokenizer가 실행 중 촉각/힘 피드백을 반영한다. TactAR는 시연 중 접촉 정보를 AR로 제공한다.
- **실험:** peeling, wiping, bimanual lifting 및 외란 조건; GelSight, MCTac, force sensor 구성을 비교한다.
- **핵심 해석:** 촉각 추가와 closed-loop 실행 구조 변경을 구분해서 봐야 한다. 네트워크의 1 ms 미만 추론 시간은 전체 로봇 루프가 1 kHz라는 뜻이 아니다.
- **우리 팀의 읽기 질문:** 고정 chunk 길이·짧은 chunk·temporal ensembling 대비 어떤 외란에서 이득이 발생하는가? 시연 품질 개선 효과와 policy 효과가 분리되는가?
- **확인 수준/공개:** 공식 proceedings와 저자 페이지의 방법·실험·ablation 확인. 코드·데이터·모델 링크 존재.
- **출처:** [공식 논문](https://www.roboticsproceedings.org/rss21/p052.html), [방법·실험·공개 자료](https://reactive-diffusion-policy.github.io/).

#### A6. Touch begins where vision ends: Generalizable policies for contact-rich manipulation — ViTaL

- **서지/선정:** Zhao et al., 2025 preprint 확인. CoRL 2025 workshop 공개본도 검색되지만 main-conference accept로 표시하지 않음.
- **방법·근거:** VLM은 대상 위치를 찾고, 지역적인 visuotactile BC + residual RL 정책이 정밀 접촉을 처리한다. end-effector 좌표계와 시각 배경 augmentation을 활용한다.
- **하드웨어/데이터:** 본문 기준 xArm 7, 2지 gripper, AnySkin, wrist camera. 작업당 32개 시연; 정책 학습·실행은 6 Hz로 설명된다.
- **우리 팀의 읽기 질문:** 환경 일반화가 촉각, 지역 좌표계, augmentation, RL 중 어디서 오는가? residual RL의 추가 로봇 시간은 얼마인가?
- **확인 수준:** 본문 방법·장비·baseline·실험 일부 확인. VLA end-to-end 모델이 아니라 계층적 VLM + local policy로 분류.
- **출처:** [논문 본문](https://arxiv.org/html/2506.13762), [프로젝트](https://vitalprecise.github.io/).

#### A7. RoboPack: Learning Tactile-Informed Dynamics Models for Dense Packing

- **서지/선정:** Ai et al., RSS 2024. 촉각을 dynamics/system identification과 연결하는 중요한 모델 기반 접근.
- **방법·근거:** 시각·촉각 history를 recurrent graph neural network에 넣어 물체 상태와 잠재 물리 정보를 추정하고 미래 상태를 예측한다. 이를 MPC에 사용한다.
- **하드웨어/평가:** Soft-Bubble sensor, non-prehensile manipulation 및 dense packing. 공식 초록은 작업당 평균 약 30분의 실제 상호작용 데이터를 보고한다.
- **우리 팀의 읽기 질문:** tactile latent가 단순 상태 추정보다 물성·동역학 추론에 실제 기여하는가? 새 물체에서 온라인 적응이 어떻게 일어나는가?
- **확인 수준:** 공식 proceedings의 초록·서지 확인. Soft-Bubble의 기하·순응성이 다른 센서에도 성립하는지는 별도 검증 필요.
- **출처:** [공식 논문](https://www.roboticsproceedings.org/rss20/p130.html).

#### A8. Feel the Force: Contact-Driven Learning from Humans — FeelTheForce / FTF

- **서지/선정:** Adeniji et al., 2025 preprint. 사람 시연에서 위치뿐 아니라 접촉력을 옮기는 데이터 수집 방향.
- **방법·근거:** tactile glove와 시각 기반 손 pose를 사용해 목표 힘을 학습한다. 로봇에서는 목표 힘을 추종하도록 gripper closure를 조정한다.
- **하드웨어:** AnySkin을 응용한 사람 glove와 Franka Panda gripper 센서. 본문에서 한쪽 gripper jaw의 센서를 사람 측 계측과 대응시킨다.
- **우리 팀의 읽기 질문:** 힘 추종의 이득과 사람–로봇 retargeting의 이득을 분리할 수 있는가? 다지 접촉 분포로 확장하면 어떤 대응 문제가 생기는가?
- **확인 수준:** 초록 및 데이터 수집·표현·실행 본문 확인. 현재 결과를 다지 사람→LEAP 전이의 실증으로 보지 않는다.
- **출처:** [논문](https://arxiv.org/abs/2506.01944), [프로젝트](https://feel-the-force-ftf.github.io/).

#### A9. Tactile-Conditioned Diffusion Policy for Force-Aware Robotic Manipulation — FARM

- **서지/선정:** Helmut et al., 2025 preprint. 촉각 입력뿐 아니라 action space를 바꾸는 연구.
- **방법·근거:** GelSight Mini가 달린 UMI형 인터페이스로 시연을 수집한다. diffusion policy가 pose, grip width, grip force를 함께 예측한다.
- **실험:** 큰 힘, 작은 힘, 동적으로 바뀌는 힘이 필요한 3개 작업.
- **우리 팀의 읽기 질문:** 단순 tactile feature fusion과 명시적인 force target 중 무엇이 중요한가? 보유 gripper/hand가 목표 힘을 안정적으로 추종할 수 있는가?
- **공개 상태 주의:** arXiv 초록은 공개를 언급하지만 조회한 프로젝트에는 ‘Code coming soon’과 공개 예정 문구가 있다. 즉시 재현 가능한 완전한 코드 공개로 판정하지 않는다.
- **출처:** [논문](https://arxiv.org/abs/2510.13324), [프로젝트·공개 상태](https://tactile-farm.github.io/).

#### A10. FBI: Learning Dexterous In-hand Manipulation with Dynamic Visuotactile Shortcut Policy

- **서지/선정:** Chen et al., 2025 preprint 기준. 다지 조작에서 dynamics-aware modality fusion을 탐색하는 후보.
- **방법·근거:** Flow Before Imitation은 motion flow와 촉각 사이의 표현을 학습하고 시각과 융합해 one-step diffusion policy를 구성한다.
- **중요한 구분:** 본문에는 Flow2Tactile로 dense contact를 예측하고 vision-only로도 작동하는 구성이 있다. 논문 제목만 보고 모든 실제 실험이 고밀도 실제 tactile sensor 입력을 쓴다고 해석하지 않는다.
- **우리 팀의 읽기 질문:** 실제 촉각, 예측 접촉, privileged simulated contact를 어떤 실험에서 쓰는가? 동역학 보조 목적 자체의 효과는 무엇인가?
- **확인 수준:** 초록 및 본문의 contact keypoint/Flow2Tactile 부분 확인. 센서·실험별 관측 정리는 추가 정독 필요.
- **출처:** [논문](https://arxiv.org/abs/2508.14441), [본문](https://arxiv.org/html/2508.14441v1).

### B. 촉각 표현·멀티모달 사전학습

#### B1. Sparsh: Self-supervised touch representations for vision-based tactile sensing

- **서지/선정:** Higuera et al., CoRL 2024 / PMLR 2025. optical tactile encoder baseline의 첫 출발점.
- **방법·근거:** 46만 장 이상 촉각 이미지로 masking/self-distillation 기반 표현을 학습하고 TacBench의 6개 과제로 평가한다.
- **왜 중요한가:** task-specific label 없이 사전학습할 수 있는 표현과 평가 프로토콜을 함께 제공한다.
- **우리 팀의 읽기 질문:** raw image encoder, ImageNet/vision pretrained encoder, Sparsh를 같은 policy와 데이터에서 비교하면 어떤가? perception metric과 실제 policy 성능이 일치하는가?
- **센서·공개:** vision-based tactile 대상. 공식 proceedings에 software 링크가 있다. 비광학식 센서에 바로 적용되는 모델로 간주하지 않는다.
- **출처:** [공식 논문](https://proceedings.mlr.press/v270/higuera25a.html), [프로젝트](https://sparsh-ssl.github.io/).

#### B2. Binding Touch to Everything: Learning Unified Multimodal Tactile Representations — UniTouch

- **서지/선정:** Yang et al., CVPR 2024; CVF 공식 서지 검색 확인, 내용은 arXiv 확인.
- **방법·근거:** 촉각 embedding을 이미 다른 모달리티와 연결된 visual embedding에 정렬하고 sensor-specific token으로 여러 optical tactile sensor를 다룬다.
- **왜 중요한가:** tactile–language 연결을 새로 처음부터 학습하는 대신 기존 멀티모달 공간을 이용하는 설계.
- **우리 팀의 읽기 질문:** 물성 의미를 잘 맞추는 embedding이 제어에 필요한 작은 변화·미끄러짐도 보존하는가?
- **분류/확인 수준:** representation·multimodal understanding 연구. grasp prediction이나 QA 결과를 end-to-end VLA 조작 성능과 동일시하지 않는다. 초록·서지 중심 검토.
- **출처:** [논문](https://arxiv.org/abs/2401.18084), [CVPR 서지](https://openaccess.thecvf.com/content/CVPR2024/html/Yang_Binding_Touch_to_Everything_Learning_Unified_Multimodal_Tactile_Representations_CVPR_2024_paper.html).

#### B3. Transferable Tactile Transformers for Representation Learning Across Diverse Sensors and Tasks — T3

- **서지/선정:** Zhao et al., CoRL 2024 / PMLR 2025. sensor–task transfer 및 실제 조작 encoder 활용의 주요 비교 대상.
- **방법·근거:** sensor-specific encoder, shared transformer trunk, task-specific decoder. FoTa는 13개 센서·11개 과제의 300만 개 이상 데이터 포인트를 모은다.
- **실험:** 센서–작업 조합 전이, 소량 fine-tuning, 실제 정밀 전자부품 삽입에서의 encoder 활용을 보고한다.
- **우리 팀의 읽기 질문:** 새 센서 adaptation에 필요한 supervision과 양은 얼마인가? policy는 고정한 채 encoder만 교체·적응할 수 있는가?
- **확인 수준/공개:** 공식 초록·프로젝트 확인. code, weights/dataset, Colab 링크 존재. 모든 미지 센서에서 zero-shot을 보장하지 않는다.
- **출처:** [공식 논문](https://proceedings.mlr.press/v270/zhao25c.html), [프로젝트](https://t3.alanz.info/).

#### B4. AnyTouch: Learning Unified Static-Dynamic Representation across Multiple Visuo-tactile Sensors

- **서지/선정:** Feng et al., ICLR 2025. 시간 정보와 센서 전이를 함께 다루는 핵심 문헌.
- **방법·근거:** tactile image/video의 static–dynamic 표현, masked modeling, multimodal alignment, cross-sensor matching을 통합한다. 4개 센서의 TacQuad를 제공한다.
- **실험:** perception/transfer 평가와 실제 pouring task.
- **우리 팀의 읽기 질문:** 같은 센서의 새 인스턴스, 새 형상, 완전히 다른 센서 종류를 어떻게 구분해 평가하는가? paired cross-sensor data가 필요한가?
- **확인 수준/공개:** 공식 proceedings·초록 확인. code, dataset, model 공개를 명시. policy 성능까지 포함해 Sparsh/T3와 비교할 가치가 있다.
- **출처:** [ICLR 공식 논문](https://proceedings.iclr.cc/paper_files/paper/2025/hash/4d893f766ab60e5337659b9e71883af4-Abstract-Conference.html), [원문](https://arxiv.org/abs/2502.12191).

#### B5. Tactile Beyond Pixels: Multisensory Touch Representations for Robot Manipulation — TacX

- **서지/선정:** Higuera et al., CoRL 2025. tactile pretraining을 이미지 밖으로 확장하는 연구.
- **방법·근거:** Digit 360의 image, audio, motion, pressure를 함께 자기지도 학습한다. 약 100만 contact-rich interaction을 활용한다.
- **실험:** imitation learning과 simulation-trained policy의 tactile adaptation, 물성 관련 추론.
- **우리 팀의 읽기 질문:** 새 센서가 어떤 채널을 제공하는가? 특정 채널이 없는 경우 표현을 재사용할 수 있는가?
- **주의/확인 수준:** 공식 초록·서지 확인. ‘4개 modality’를 ‘4개 서로 다른 센서에서 동일 정책 전이’로 해석하지 않는다. 데이터 단위도 이미지 장수와 구분한다.
- **출처:** [CoRL 공식 논문](https://proceedings.mlr.press/v305/higuera25a.html).

#### B6. Octopi: Object Property Reasoning with Large Tactile-Language Models

- **서지/선정:** Yu et al., RSS 2024. VLA-Touch의 semantic tactile feedback을 이해하는 선행 연구.
- **방법·근거:** GelSight tactile video와 물성 추론 annotation을 담은 PhysiCLeAR를 만들고, 촉각 표현과 large vision-language model을 연결한다.
- **핵심:** 중간 물성 예측을 활용하는 reasoning이며, 그 자체가 로봇 action policy인 것은 아니다.
- **우리 팀의 읽기 질문:** 언어 설명으로 촉각을 압축할 때 시간·힘·미끄러짐 정보가 얼마나 사라지는가? 설명의 정확도와 행동 개선을 별도로 검증하는가?
- **확인 수준/공개:** 공식 proceedings 확인. 데이터·코드 링크 제공. RSS 2025의 Octopi-1.5 demonstration과 원 논문을 혼동하지 않는다.
- **출처:** [RSS 공식 논문](https://www.roboticsproceedings.org/rss20/p066.html), [공식 코드](https://github.com/clear-nus/octopi).

#### B7. Touch2Touch: Cross-Modal Tactile Generation for Object Manipulation

- **서지/선정:** Rodriguez et al., 2024 preprint 기준. 센서 전이를 latent alignment와 다른 방식으로 접근.
- **방법·근거:** diffusion으로 GelSlim과 Soft Bubble 간 tactile signal을 번역한다. 원래 다른 센서에 의존하는 in-hand pose estimation 알고리즘을 생성된 신호에 적용한다.
- **우리 팀의 읽기 질문:** 생성된 촉각이 보기 좋다는 것과 접촉력/기하를 보존한다는 것을 어떻게 구분하는가? 센서 번역의 불확실성이 downstream control에서 증폭되는가?
- **확인 수준/주의:** 원문 초록 확인. pose-estimation transfer를 일반 정책의 cross-sensor transfer와 동일시하지 않는다. 후속 Cross-Sensor Touch Generation과 버전·계보 비교는 추가 확인 대상.
- **출처:** [논문](https://arxiv.org/abs/2409.08269).

### C. VLA 및 언어 조건부 접촉 조작

#### C1. Tactile-VLA: Unlocking Vision-Language-Action Model’s Physical Knowledge for Tactile Generalization

- **서지/선정:** Huang et al., 2025 preprint 확인. VLA의 물리 상식과 실제 촉각 grounding을 직접 연결.
- **방법·근거:** π0에서 출발해 vision, language, proprioception, tactile history를 융합한다. 위치와 힘 목표를 생성하고 hybrid position–force controller로 실행한다. 실패 원인에 대한 언어 supervision을 쓰는 reasoning variant도 제안한다.
- **실험 축:** 촉각 관련 instruction following, commonsense, feedback-based adaptation.
- **우리 팀의 읽기 질문:** VLM prior, tactile observation, force action space, controller 각각의 기여가 분리되는가? 언어 재표현이 아니라 물성 변화에 일반화하는가?
- **확인 수준:** 본문 architecture/controller/data collection 일부 확인. UMI형 장치에 촉각 센서를 더한 수집 구조이며, LEAP Hand 실증으로 보지 않는다.
- **출처:** [논문](https://arxiv.org/abs/2507.09160), [본문](https://arxiv.org/html/2507.09160v1).

#### C2. VLA-Touch: Enhancing Vision-Language-Action Models with Dual-Level Tactile Feedback

- **서지/선정:** Bi et al., 2025 공개; **RA-L 2026 accept는 저자 공식 저장소에서 확인**. 기반 VLA를 유지하면서 촉각을 접목하는 실용적인 비교 대상.
- **방법·근거:** Octopi 기반 촉각 언어 피드백으로 상위 planning을 돕고, diffusion-based controller로 VLA action을 촉각에 따라 보정한다.
- **중요한 구분:** ‘base VLA를 tactile로 fine-tuning하지 않는다’는 것이 전체 파이프라인이 무학습이라는 뜻은 아니다. 저장소에는 기반 VLA의 작업 적응 및 별도 controller 학습 절차가 있다.
- **우리 팀의 읽기 질문:** semantic feedback와 low-level correction 중 어느 부분이 필요한가? 새로운 작업·접촉 모드로 controller가 전이되는가?
- **공개 상태:** 코드·dataset/checkpoint 안내가 있으나 README에 추후 공개될 inference 부분도 명시된다. 완전한 turnkey 재현으로 판정하지 않는다.
- **출처:** [논문](https://arxiv.org/abs/2507.17294), [공식 저장소·게재 정보](https://github.com/clear-nus/vla-touch/blob/master/README.md).

#### C3. ForceVLA: Enhancing VLA Models with a Force-aware MoE for Contact-rich Manipulation

- **서지/선정:** Yu et al., NeurIPS 2025 Main Conference. 공식 proceedings 확인.
- **방법·근거:** 6축 force feedback과 pretrained vision-language feature를 force-aware MoE로 action decoding에서 통합한다. 5개 contact-rich task의 동기화 데이터를 제시한다.
- **분류:** 손끝 촉각 이미지가 아니라 외력/force–torque 기반 인접 연구. 센서가 같다고 가정하지 않는다.
- **우리 팀의 읽기 질문:** global wrench로 부족하고 local tactile distribution이 필요한 작업은 무엇인가? 단순 fusion 대비 gating/MoE의 역할은 무엇인가?
- **확인 수준/공개:** 공식 초록·서지 확인. proceedings는 code/data 공개 예정으로 표시하므로 즉시 이용 가능성을 보증하지 않는다.
- **출처:** [NeurIPS 공식 논문](https://papers.neurips.cc/paper_files/paper/2025/hash/8633b46e12cc5f2ee1f05a6ca2c65b38-Abstract-Conference.html).

#### C4. VTLA: Vision-Tactile-Language-Action Model with Preference Learning for Insertion Manipulation

- **서지/선정:** Zhang et al., 2025 preprint 확인. insertion, multimodal grounding, preference optimization을 잇는 후보.
- **방법·근거:** simulation에서 vision–tactile–action–instruction 데이터를 만들고, DPO를 사용해 정책을 학습한다. 새로운 peg shape 및 실제 peg-in-hole sim-to-real을 평가한다.
- **우리 팀의 읽기 질문:** DPO 개선과 tactile 개선이 분리되는가? simulation tactile과 실제 센서 사이의 gap을 무엇으로 줄였는가? 언어 지시의 다양성이 충분한가?
- **확인 수준:** 원문 초록 확인. 범용 VLA의 대규모 tactile 확장과 특정 insertion task 모델을 구분해야 한다. 정규 게재 상태는 이번 조사에서 발행사 페이지로 검증하지 못했다.
- **출처:** [논문](https://arxiv.org/abs/2505.09577).

## 4. 최신 경쟁 연구·후속 문헌 9편

아래는 아이디어 중복을 피하기 위한 필수 추적 목록이다. 원문 또는 저자 페이지를 확인했지만 전체 재현·정밀 비교를 완료한 것은 아니다. 특히 2026년 논문을 기존 기반 문헌보다 ‘더 검증된 결과’로 취급하지 않는다.

| ID | 논문·상태 | 확인한 내용 | 연구 설계에 주는 제약 |
| --- | --- | --- | --- |
| D1 | [Learning to Feel the Future: DreamTacVLA for Contact-Rich Manipulation](https://arxiv.org/abs/2512.23864), 2025-12; 2026-06 v4, preprint | tactile/wrist/global vision의 계층적 정렬, 미래 tactile world model, sim–real 혼합 데이터 | ‘VLA + tactile prediction’ 자체는 이미 존재 |
| D2 | [TacVLA: Contact-Aware Tactile Fusion for Robust Vision-Language-Action Manipulation](https://arxiv.org/abs/2603.12665), 2026-03; 2026-09 v4, preprint | 접촉이 감지될 때 tactile token을 선택적으로 활성화하는 contact-aware gating | ‘접촉 때만 tactile 사용’ 자체의 novelty는 약함 |
| D3 | [OmniVTA: Visuo-Tactile World Modeling for Contact-Rich Robotic Manipulation](https://arxiv.org/abs/2603.19201), 2026-03; 2026-08 v3, preprint | OmniViTac 데이터: 21,000+ trajectories, 86 tasks, 100+ objects라는 저자 보고; world model과 60 Hz reflex controller | 예측·피드백·대규모 데이터를 함께 다루는 직접 경쟁 연구. 공개 예정 문구와 실제 다운로드를 구분 |
| D4 | [HapticVLA: Contact-Rich Manipulation via Vision-Language-Action Model without Inference-Time Tactile Sensing](https://arxiv.org/abs/2603.15257), 2026-03; 2026-08 v2, preprint 기준 | tactile reward-weighted flow matching과 tactile distillation; 실행 때 센서 불필요 | 학습 시 촉각 supervision을 쓰는 연구도 이미 존재. 관측 불가능한 새 외란에서는 별도 평가 필요 |
| D5 | [TAP-VLA: Tactile Annotation Prompting for Vision Language Action Models](https://arxiv.org/html/2606.29089), 2026-06, preprint | tactile shear field를 RGB 이미지 위 vector로 표시해 기존 입력 형식 활용 | 아키텍처 무변경/무촉각 사전학습은 무fine-tuning과 다름. 단순하고 강한 fusion baseline 후보 |
| D6 | [UniTacVLA: Unified Tactile Understanding and Prediction in Vision Language Action Models](https://arxiv.org/html/2606.31723), 2026-06, preprint | tactile semantics·미래 latent 예측·빠른 residual correction을 결합. RealMan arm + DM-Tac W, 8개 작업 | 실제 센서와 예측 latent를 함께 쓰는 제어도 이미 존재. clean/recovery 데이터의 사용 조건 비교 필요 |
| D7 | [ViTaR: Visuo-Tactile Residual Adaptation for Foundation VLA Manipulation](https://arxiv.org/abs/2608.15816), 2026-08, preprint | frozen VLA 위에서 bounded residual을 선택·스케일링; outcome-grounded preference 활용 | frozen VLA + tactile residual 자체만으로 차별화 어려움 |
| D8 | [ForeTac-VLA: A Forecasting-Based Tactile-Vision-Language-Action Model for Contact-Rich Robotic Manipulation](https://arxiv.org/abs/2609.20980), 2026-09-17, preprint | history의 temporal encoding, multi-step tactile forecasting, 예측으로 전환하는 curriculum | 매우 최근 연구. forecast를 action conditioning에 쓰는 접근의 직접 비교 대상 |
| D9 | [ImplicitRDP: An End-to-End Visual-Force Diffusion Policy with Structural Slow-Fast Learning](https://implicit-rdp.github.io/), RA-L 2026은 저자 페이지 확인 | 비동기 visual/force token, causal structure, virtual-target regularization | 단순 계층형 RDP뿐 아니라 unified slow-fast 모델 및 modality collapse 대응과도 비교 필요 |

### 최신 원문을 읽을 때 발견한 검증 포인트

- UniTacVLA는 비교 모델을 π0.5 기반으로 재구현했다고 명시한다. 표의 성능을 원 논문 시스템 전체에 대한 직접적인 우열로 읽으면 안 된다. clean demonstration과 disturbance/recovery 데이터를 어느 모듈에 썼는지도 중요하다. [원문 방법·실험](https://arxiv.org/html/2606.31723)
- UniTacVLA의 related work가 TacVLA를 설명하는 방식과 현재 TacVLA v4의 중심 설명(contact gating)이 다르다. 모델 이름이 같아도 **비교 버전·재구현 정의**를 고정해야 한다. [TacVLA 현재 버전](https://arxiv.org/abs/2603.12665)
- Future tactile prediction의 정확도만으로 policy improvement의 원인이 입증되지는 않는다. encoder 용량, 보조 loss, 추가 데이터, controller 유무를 통제해야 한다. 이는 위 문헌을 읽고 제안하는 실험 원칙이다.

## 5. 배경·인접 문헌 6편

| 논문 | 역할 | 포함 이유와 경계 |
| --- | --- | --- |
| [DIGIT: A Novel Design for a Low-Cost Compact High-Resolution Tactile Sensor With Application to In-Hand Manipulation](https://ieeexplore.ieee.org/document/9018215), 2020 | 센서 기반 | optical tactile의 관측 형태·장착·in-hand 활용을 이해. policy 연구와 별도 분류 |
| [ReSkin: versatile, replaceable, lasting tactile skins](https://arxiv.org/abs/2111.00071), CoRL 2021 / PMLR 2022 | magnetic skin + learning | 센서 교체·제작 편차·시간에 따른 변화가 학습 문제라는 관점 |
| [AnySkin: Plug-and-play Skin Sensing for Robotic Touch](https://arxiv.org/abs/2409.08276), 2024 공개본 | 재사용 가능한 촉각 하드웨어 | 새 센서 인스턴스로 조작 정책을 옮기는 문제. ‘sensor replacement transfer’도 기존 연구가 있음 |
| [Touch and Go: Learning from Human-Collected Vision and Touch](https://touch-and-go.github.io/), NeurIPS 2022 Datasets and Benchmarks | 데이터셋 | 사람의 자연환경 탐색에서 시각·촉각 데이터를 수집. robot action demonstration 데이터와 구분 |
| [TACTO: A Fast, Flexible, and Open-source Simulator for High-Resolution Vision-based Tactile Sensors](https://arxiv.org/html/2012.08456v2) | 시뮬레이션 기반 | optical tactile rendering을 실험에 연결할 때 필요. rendering realism과 contact dynamics realism은 별개 |
| [Tac-Man: Tactile-Informed Prior-Free Manipulation of Articulated Objects](https://arxiv.org/abs/2403.01694), T-RO accept·DOI 확인 | 비학습/제어 인접 비교 | 관절체의 사전 기구학 모델 없이 접촉을 유지하는 접근. learned policy가 기존 tactile controller보다 왜 필요한지 묻는 baseline |

Tac-Man은 중심 robot learning 논문이 아니라 **학습이 필요하다는 주장에 대한 비교군**으로 포함했다. 센서 제작만 다루는 문헌은 이 배경 목록 이상으로 확장하지 않았다.

## 6. 우선 읽을 8편

| 순서 | 논문 | 읽고 나서 팀이 답할 질문 |
| --- | --- | --- |
| 1 | T-Dex | 적은 촉각 시연을 쓰기 위해 표현을 어떻게 먼저 학습하는가? |
| 2 | Reactive Diffusion Policy | tactile을 policy 입력에 넣는 것과 실행 중 반응하는 것은 왜 다른가? |
| 3 | Sparsh | 어떤 pretrained tactile encoder와 benchmark를 시작점으로 쓸 수 있는가? |
| 4 | AnyTouch | 시간 정보와 센서 domain shift는 어떻게 다루는가? |
| 5 | RoboPack | 촉각을 latent dynamics/system identification에 쓰면 무엇이 달라지는가? |
| 6 | Tactile-VLA | 언어 지식·촉각 관측·힘 목표·제어기가 어떤 역할을 분담하는가? |
| 7 | VLA-Touch | 큰 VLA를 고정하고 tactile feedback을 붙이는 설계의 장단점은 무엇인가? |
| 8 | OmniVTA | 현재 predictive tactile control의 직접 경쟁선과 데이터 규모는 무엇인가? |