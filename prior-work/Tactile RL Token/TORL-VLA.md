# TORL-VLA

**Title:** TORL-VLA: Tactile Guided Online Reinforcement Learning for Contact-Rich Manipulation

- **Venue:** arXiv
- **arXiv submitted:** 2026.06.08
- **Paper:** https://arxiv.org/abs/2606.09337

## 0. Takeaway

이 저자들도 RLT를 읽고 거기서 확장해서 이거로 넘어온 것 같아 보임.

RLT, ForceVLA의 테크닉을 잘 섞고 intervention-censored critic만 추가한 정도의 연구.

실험이 그렇게 체계적인가라고 하면 그 정도는 아닌 것 같음.

해결하고자 하는 문제는 aware 뿐만 아니라 adapt하는 것이 중요하다는 것이고, 하고자 하는 얘기는 우리의 방식대로 aware하고 adapt하는 것이 좋다.

gripper에서는 wrench 정보만 있어도 충분할 것 같다는 생각을 했음. 왜냐하면 어차피 그리퍼 좌우 2개로만 물체를 잡는 거니까, wrench 정보만 있어도 됨.

근데 dexterous hand의 경우에는 지난번 리프핸드만 텔레옾 해보았을 때 보았듯이, 손가락 면 전체에 물체가 잘 접촉해서 잡는다기 보다는 손가락 면에서도 일부 지점만 접촉된다거나 하는 모습이 있었음. 그래서 단순히 센서의 평균적인 힘만 이용하기 보다 센서 내의 국소적인 정보도 중요한 것 같음. 또한 센서가 16개이고 센서간의 지오메트리도 중요할 것 같다고 생각함. 그래서 우리가 디자인할 때 센서로부터 wrench 정보만 사용하는 것이 아니라 tactile 정보를 전부 사용하고, dexterous hand의 각 지점의 지오메트리를 잘 엮어서 representation을 추출하면 좋지 않을까하는 생각을 함.

## 1. Problem

contact awareness를 높이기 위한 SFT-based Tactile-Enhanced VLA가 등장하고 있으나, contact awarness는 contact adaptation과 equivalent하지 않다. 대부분의 tactile-aware VLA는 static offlile policies이고, 따라서 current tactile feedback을 사용하는 능력이 부족하다.

→ aware뿐만 아니라 adapt하는 능력도 중요하다.

online RL에서 policy의 expolaration은 비싸고 real world에서는 safety 위험 또한 존재한다. 물론 이를 위한 human intervention RL이 존재하지만, human intervention은 value-learning에 bias를 준다.(로봇의 잘못된 행동이 좋았던 것처럼 bias가 낄 수 있음)

## 2. Contribution

1. propose TORL-VLA, a tactile-guided online reinforcement learning. use tactile-derived wrench-aware VLA and outputs refined action chunks through a lightweight actor-critic

2. introduce an intervention-censored critic for online RL

3. validate on real-robot long-horizon contact-rich manipulation

## 3. Novelty

### 3.1. Tactile-aware VLA

대부분의 tactile VLA는 supervised learning이나 offline imitation learning임.

→ 우리는 VLA action을 online으로 correct하기 위해서 tactile feedback을 사용하는 것을 타겟함.

### 3.2. Online RL for VLA

많은 online RL for VLA는 human intervention이 value learning bias를 일으킨다는 것을 잘 다루지 않음.

→ 우리는 intervention-censored value learning 도입해서 misleading credit propogation을 막음.

RLT는 reference-guided online refinement를 사용하지만 online refinement 동안 wrench input을 통합 안 하고 intervention-censored critic도 없다고 방어함.

## 4. Method & Implementation

### 4.1. Tactile-Aware VLA as an Action and Wrench Reference Model

**tactile representation**: raw $6 \times 8$ tactile array → compact 6D wrench. two fingers on gripper

6D wrench is mapped to force-torque space. vendor SDK가 $6 \times 8$ raw tactile array를 6D wrench로 estimate 해주어서 그 값을 사용.

temporal window를 정하고 window 내의 wrench sequence를 MLP로 single wrench token으로 mapping.

**Wrench-conditioned reference generation**: BLIP-2 방법을 따서, VLM에 wrench를 같이 넣기보다는, VLM에서 나온 representation을 wrench token과 concat해서 self-attention. 이를 통해서 pretrained knowledge 보존.

MoE-based fusion and adaptation에 따라서 soft router, elment-wise weighting fused feature를 만듦. routed feature에 다시 wrench token을 learnable scaling parameter로 weight해서 더해짐. 그리고 그 feature가 다시 action expert의 hidden state에 더해짐.

(ForceVLA의 fusion architecture랑 거의 똑같음.)

output head는 action chunk와 future wrench sequence를 함께 예측. action chunk는 motion reference로서 기능하고, wrench sequence는 expected contact guidance로서 기능.

### 4.2. Stage Specific Online Reference Adaptation

refines VLA action references using measured wrench feedback and predicted future wrench cues.

**Stage-specific wrench-conditioned action refinement:** frozen wrench-aware VLA predicts an H steps action chunk and future wrench sequence. executable horizon K.

online actor uses the context (visual-semantic tokens from VLA, proprioceptive state, current measured wrench, measured wrench histroy, predicted action chunk, predicted future wrench sequence)

stage estimator는 contact stage와 상응하는 stage-specific actor head를 선택. 선택된 actor head가 context 받아서 action 생성.

**Intervention-censored actor-critic learning:** human intervention이 일어나면, task critic은 policy-generated action chunk를 over-credit하게 됨. 그래서 task critic과 함께 추가적으로 intervention-censored critic을 추가.

### 4.3. Implementation

TORL-VLA w/o RL은 learend wrench-aware reference model을 직접적으로 실행.

base VLA는 자신들의 wrench-aware reference model로 하고 RLT, TORL-VLA, other ablation을 진행해서 비교했고 이를 통해서 wrench-context conditioning and intervention-censored value learning을 공평하게 비교했다고 함.

VLM에 바로 wrench token 넣기 보다는 late fusion strategy. 이 덕에 pretrained visual-semantic feature 보존했다고 함. 그리고 zero-initilized wrench-token bypass해서 학습 초기에는 영향 없고 adaptively 했다고 함. (근데 action expert에는 넣는데, 정말로 pretrained feature 보존했다고 할 수 있나…action expert에서 오는 signal 때문에 VLM knowledge 영향 받을텐데)

base VLA는 50 horizon 예측하고 actor는 10 step.

actor에 줄 compact VLA token 추출하기 위해서 lightweight token encoder 넣어서 special token 자리에 있는 거 사용. → RLT처럼 했다는 것 같음.

## 5. Experiment

- **Q1:** wrench-guided online refinement가 task 성능 향상시켜?

- **Q2:** wrench-aware reference model이 다른 physical feedback baseline보다 좋은 reference 제공해?

- **Q3:** wrench-context conditioning과 intervention-censored critic이 online adaptation에 필요해?

### 5.1. Tasks

- **Coffee Cup:** placing a cup into a tight holder inside the box with limited visibility

- **Latch:** gripping, flipping, and locking a mechanical latch

- **Egg:** fragile-object grasping and placement

## 6. Result

### 6.1. Baselines & Ablations

**Baselines:**

- pi05
- TA-VLA
- ForceVLA
- TORL-VLA w/o RL
- RLT

**Ablations:**

- w/o wrench histroy token
- w/o future wrench prediction
- w/o MoE
- w/o zero-initialized
- w/o wrench context
- w/o intervention-censored critic

### 6.2. Results

baseline들 보다는 잘 하긴 하는 것 같음.

ablation의 경우 근데 30번 trial만 했는데 자기들꺼는 30번 거의 모두 성공해서, 좀 신뢰가 안 가기는 함…

MoE 구조가 없을 때 성능이 많이 낮아져서, MoE 구조는 효과가 있긴 한 가봄.

Wrench context나 intervention critic 없을 때 27/30 정도인데 이게 유의미한 차이인지 잘은 모르겠음.
