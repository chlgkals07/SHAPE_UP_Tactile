[← 선행연구 목록](README.md)


# Tactile-VLA: Unlocking Vision-Language-Action Model's Physical Knowledge for Tactile Generalization



- 링크: https://arxiv.org/abs/2507.09160 , https://openreview.net/forum?id=uhB3pbJpRm

- 읽은 사람: 임세화

- 날짜: 26.09.26

- arXiv 25.07, ICLR 2026 reject 



# 내용



**해결하고자 한 문제**



(1) current VLA는 precise force control이 중요한 contact-rich setting 같은 fine grained decision에서 실패하는 경우 보임. 

(2) haptic을 robotic framework에 추가한 연구들이 존재하긴 하지만, 단지 perceptual modality를 추가한 것이지 policy의 action generation에 직접적으로 관여하지 않음. 
(기존 연구는 tactile 정보를 input 정도로만 받지만, 이 연구에서는 tactile 정보를 바탕으로 action generation에 직접적으로 연결하도록 모델을 개발하겠다는 것 같음. 그리고 language modality도 사용하는 paradigm의 robotic framework에 초점을 두는 것 같음.)


<br>

**선행 연구와 차별점**



(1) tactile과 force sensing을 VLA에 추가하는 연구들은 존재함. 하지만 이 연구들은 finetuning이나 modality-specific routing에 중점을 둠. Ours는 VLM이 physical interatction에 대한 knowledge를 이미 가지고 있으며 소량의 demo 만으로 tactile sensor를 연결해주면 zero-shot generalization이 가능해짐을 보였음. 

(2) tactile을 robot poliy에 사용하는 연구들은 다양한 방식으로 존재함. 하지만 language modality와 함께 사용하지 않아서 novel instruction, reasoning, commonsense knowledge 등에는 제한적임. Ours는 VLA의 semantic 능력과 world knowlege 사용. 

<br>


**방법론**

goal: unlock the physical knowledge inherent in VLAs by using tactile

(1) Tactile-VLA Architecture

token-level fusion approach

기본적으로는 pi0의 아키텍처를 그대로 사용. tactile signal에 대해서 MLP를 encoder로 사용. 그래서 concatenated history tactile을 single token으로 encoding. 

input token sequence는 VLM 통과한 후에 그 representation은 tactile-aware action expert로 들어감. 
tactile-aware action expert는 target position과 target contact force를 rediction. 

pi0 backbone 사용하고 action expert와 tactile encoder만 random intialization.

(2) Hybrid Position-Force Controller 

action exeprt가 예측한 target position과 target force를 low-level controller가 이용

strategy: 보통은 position이 dominant하며, contact phase에서는 force control이 필요해 precise kinematic motion이 중요함. 

target force와 measured target의 오차를 측정해서 그 오차가 크면 target position에 오차에 비례하게 integration해줌. 

(3) Tactile-VLA-COT: Reasoning-based adaptation

CoT 사용해서 tactile feedback으로 adaptive reasoning과 re-planning하도록 함. 

VLM의 pretrained decoder 이용해서 explicit하게 CoT trajectory(monologue) decoding.

그래서 failure event를 가지는 dataset을 만들었는데 이 dataset은 sensory stream, failure cause에 대한 language annotation도 가짐. 이 dataset으로 finetuning. 

CoT reasoning은 fixed interval마다 실행. 
prompt가 task의 success 여부를 묻고 model이 이에 답함. failure로 판단할 경우 model은 sensory feedback을 바탕으로 원인을 추론하고, 다른 force component가 필요함을 분석하고 guide 할 수 있는 새로운 instruction을 생성함. 

<br>

**결과**

(1) tactile과 관련된 language를 배웠고, "soft"와 "hard"라는 language instruction에 맞도록 force를 가했음. 

(2) training data에 없던 language expression에 대해서도 적용되었고 unseen task에도 적용됨. 

(3) VLM prior knowledge 덕분에 OOD 물체에 대해서도 물체의 property를 이해하고 적절한 force로 grasping함. 

(4) whiteboard에서 train 되고 blackboard에서 OOD test했을 때 CoT 사용하면 안 할 때보다 성능이 크게 개선됨. 즉 OOD에서 실패할 경우 CoT가 실패를 correction해주었음. 



<br>

**하드웨어**

data 수집할 때 UMI 이용했다고 함. human operator가 force feedback 이용하기 어려운 것을 보완하는 방법. 

arm:  7-DoF Franka arm

hand: Weiss WSG-50 parallel-jaw gripper

tactile sensor: 



# 우리 연구와의 연결

**한계** 

(1) 논문에 한계 언급 안 함. 

(2) 개인적인 한계들로는, ablation이 부족하지 않나. 또한 단순히 pi와 tactile-pi를 비교하는 것만으로 비교가 충분하지는 않다고 생각하긴 함. 기존 tactile 이용하는 policy와도 비교했어야 했을 것 같음. 

(3) 깃발꼽기 스타일의 논문답게 논문 자체가 굉장히 대충 적혀있음. model, data 관련 설명 부족. 

<br>

**감상** 

(1) visual observation과 tactile sensing의 frequency가 안 맞음. -> 이로 인한 문제는 없나? train data는 어찌어찌 맞춘다고 하더라도 real time control에서도 이게 잘 맞아 떨어질까? 

(2) 깃발 꼽기 스타일의 논문. 그래서 citation은 높다. ICLR reject 당할 만하다. ablation 더 빡세게 하긴 했어야 함. 

(3) 추후에 우리 실험에서 task 정도는 참고해도 좋을 것 같기는 함. 

(4) Reject 이유(GPT 요약): 

1. 비교 실험이 핵심 주장을 충분히 검증하지 못함
   촉각을 사용하는 방법이 촉각 없는 π₀보다 좋다는 결과만으로는, 제안 방식의 고유한 장점이 분명하지 않습니다.
   **기존 시각–촉각 정책**이나 **Reactive Diffusion Policy** 같은 방법과의 비교가 요구됐습니다.
   특히 “VLM에 내재된 물리 지식을 활용한다”는 주장을 뒷받침하려면, **사전학습 없이 학습한 정책**과의 비교도 필요하다는 지적입니다.
   
2. 무엇이 성능을 높였는지 분리하기 어려움
   리뷰어들은 다음 **대조 실험**을 요청했습니다.
   - 촉각 입력은 유지하고 위치 제어만 사용하는 경우
   - 정책에 촉각 입력을 주지 않고 위치·힘을 출력하는 경우
   - 촉각 없이 시각 기반 CoT만 사용하는 경우
   이런 실험이 부족해 촉각, 힘 제어, CoT, 사전학습 지식 각각의 기여를 판단하기 어렵다는 것입니다. 

3. 일반화 주장의 범위에 비해 실험이 제한적임
   실험은 삽입·파지·닦기 등 세 과제에 집중됐고, CoT는 닦기 과제에서만 검증됐습니다.
   특히 닦기 실패는 시각으로도 확인할 수 있어, 성공이 정말 촉각 기반 추론 때문인지 의문이 제기됐습니다.
   데이터에 대해서도 “전체 검증 규모가 작다”는 지적과 “상대적으로 단순한 과제에 약 100개 시연을 쓰는데 암기가 아닌가”라는 지적이 함께 나왔습니다.
   
5. 신규성과 기술적 설명이 부족함
   **위치–힘 제어기는 기존 제어 방식**에 가까워 독립적인 알고리즘 기여가 약하다는 평가가 있었습니다.
   여기에 촉각 인코더의 정렬 방식, 행동 공간, 학습·수집 세부사항이 충분히 설명되지 않았고, 동시기 tactile-VLA 연구 및 기존 힘 제어 연구와의 차별화도 부족했습니다.
   Area Chair도 이를 주요 우려로 정리했습니다.


