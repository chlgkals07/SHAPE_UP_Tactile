# RL Token

**Title:** RL Token: Bootstrapping Online RL with Vision-Language-Action Models

- **Venue:** 2026 CoRL (oral)
- **arXiv submitted:** 26.04.24
- **Paper:** https://arxiv.org/abs/2604.23073

## 1. Problem

RL은 error에 sensitive하고 demonstration만으로 배우기 어려운 task를 향상시키기 좋다. real world RL adaptation은 budget이 한정적이다.

**그런데 VLA의 RL adaptation(SimplerVLA-rl, Gr-rl, pi06)은 매우 비효율적이다. 반면에 data-efficient real world RL adpation은 small model를 training하기 때문에 빠른 시간 내에 가능하지만 generalization capabilities가 떨어진다.**

**Main Question:** 어떻게 VLA의 generalization capability를 활용하면서도 efficient하게 RL adaptation을 할 수 있을까?

## 2. Contribution

1. introduce RL Token, a compressed representation
2. introduce sample efficient RL to train a lightweight actor and critic with anchoring the VLA action
3. show the performance about tasks that can require millimeter or sub-millimeter precision, especially the largest gain appear in the critical phase.

## 3. Novelty

1. VLA: demonstration data만으로 training한 VLA는 precision-critical tasks에서 어렵고, 그러한 task는 teleoperation data도 noisy하고 inconsistent하다.

2. real world RL: human intervention을 포함하는 off-policy 방법이 효과적임을 보였지만 small policy with pretrained vision encoder 에 국한됨. 그래서 rich prior가 없음.

   → RLT는 이러한 gap을 frozen VLA로 채움.

3. RL of VLA: pi06, simplervla-rl, pi_RL 같은 연구 존재함. 하지만 그러한 on-policy method는 real-world로 확장하기 어려움. lightweight method(ConRFT, Policy Decorator, PLD, GR-RL, DS-RL)등은 RLT와 full model RL을 하지 않으면서 pretrained VLA를 향상시키고자 하는 목표는 공유하지만, RLT의 경우 (1) RL Token, compact representation을 도입했고, (2) chunked actions에 얼라인 되어 있으며, (3) VLA의 reference action에 directly conditioned하고 regularize하여 good VLA prior 이용.

## 4. Method & Implementation

1. trains VLA to expose RL token, a compressed representation that makes task-relevant pretrained knowledge accessible.

2. uses a sample-efficient online RL algorithm to train the small actor and critic networks that use the RL token representation with regularizer to anchor the actor to VLA action

### 4.1. RL Token

summarizes VLA’s knowledge into single vector.

Encoder-decoder fashion.

VLM final-layer embedding(stop-gradient)과 learnable embedding(RL token)을 concat하고 encoder에 넣음.

decoder는 AR하게 encoder의 output을 reconstruction.

small task-specific demonstration으로 encoder-decoder training. 그리고 선택적으로 VLA는 SFT.

### 4.2. Online RL to refine VLA action chunks

freeze VLA and RL Token, train lightweight actor and critic.

**Critic input:** state (RL token, proprioceptive states)

train the critic with standard off-policy TD learning on action chunk sampled the replay buffer.

**Actor input:** state (RL token, proprioceptive states), VLA action chunks

train the actor to maximize critic value while regularizing toward reference actions

reference-action을 단순 copy하는 문제를 막기 위해서 reference action dropout(replace with zeros)

### 4.3. Implementation

- **Action chunk horizon $H$:** 50 corresponding to 1 second of control.

- **Execution:** prefix of this chunk open loop before re-planning from a new observation

- **Reward:** sparse binary reward from human evaluator

- **Actor / critic:** operate over action chunk $C$ ($C < H$) for more reactive policy

- **Off-policy learning:** replay buffer from VLA policy, RL actor, human teleoperated intervention

1. replay buffer에 VLA reference policy를 돌려서 Warmup data 채우기.
2. rollout 동안 VLA가 reference chunk H 만들고 RL actor가 C개 만듦. optionally, human이 intervention할 수 있으며 actor의 output을 overwrite한다. 또한 VLA reference action도 바꾼다.
3. time-efficient를 위해 rollout과 learning을 async로 진행했고, two critic updates for each actor update
4. critical phase 이전까지는 base VLA가 하고, critical phase 부터 actor가 함. rollout 때에는 human이 이 timing을 조절. test time을 위해서는 VLA를 짧게 finetuning해서 vla가 언제 rl actor 호출할지 control하도록 할 수도 있고, 혹은 그냥 human이 관여할 수 있음.

## 5. Experiment

| Question | RLT | TRLT에 대응하는 질문 |
| --- | --- | --- |
| Q1 | RLT가 base VLA보다 잘 하니? | TRLT가 base VLA or base TVLA보다 잘 하니?  |
| Q2 | RLT가 다른 RL보다 잘 하니? | TRLT가 RLT 혹은 tacilte RL보다 잘 하니?  |
| Q3 | each component가 유효하니? | same |
| Q4 | RLT가 더 나은 전략을 찾기도 하니? | same |

### 5.1. Tasks

각 tasks는 30-120 초 정도 걸림. critical phases는 precision이 중요한 시점으로 정의하고 이 phase는 5~2-초 정도임.

#### 5.1.1. Screw Installation

sub-millimeter alignment

**Why difficult?**

screw가 항상 똑바로 되어 있는 것이 아님. end-effector의 각도가 grasping 포인트와 screw의 tip 위치에 따라 달라짐, critical visual cues의 경우에 반대쪽 팔의 wrist camera에 의존하게 됨

#### 5.1.2. Zip Tie Fastening

**Why difficult?**

wrist camera로부터 tip과 slot의 위치를 잘 추론해야 함

#### 5.1.3. Ethernet Insertion

**Why difficult?**

position과 angle의 정확한 alignment가 필요함.

#### 5.1.4. Charger Insertion

**Why difficult?**

centimeter-level alignmen가 필요함. 작은 에러도 반복적인 시도 혹은 실패가 됨.

### 5.2. Critical-Phase Evaluation

our method는 critical phase를 해결하게 위해 고안되었기 때문에, critical phase에서 초점을 맞춤.

epsiode는 critical phase가 시작하기 직전의 어느 정도 task가 수행된 상태에서 시작함.

이때 약간의 randomized initial configuration을 사용.

50 episode per task

### 5.3. Full-Task Evaluation

more realistic setting.

start from home position.

earlier stage에서는 base policy만 실행하고 critical phase에서는 actor까지. 이 덕분에 base policy에 의한 state variation 하에서 critical phase 돌입 가능.

그래서 full-task training을 위해서 우선 critical phase에서만 RL training하고서, 그것을 가지고 full-task training으로 확장.(여기에서 critical phase detect도 학습했을듯).

### 5.4. Details

#### 5.4.1. Hardware

additional proprioceptive state의 경우 task에 따라서 조금씩 다르게 사용.

robot control frequency: 50 Hz

14-dimensional per-timestep action (bimanual 7 DoF), 140-dimensional chunked action for RL actor

#### 5.4.2. Training and Data

1~10 hours teleoperated demonstraion for each task

finetuning VLA model while training RL token for 2000~10000 steps

run RL 400~1000 episodes depending on the task difficulty

For sample efficiency, 수집된 action들에서 stride 2로 chunk를 sampling.

## 6. Results

### 6.1. Baselines & Ablations

**Other RL methods:** HIL-SERL, PLD, DSRL, DAgger

**Ablations:**

- w/o RL token (replace with ResNet)
- w/o chunk (single-step)
- w/o BC regularizer
- w/o Pass-Through (== w/o reference action)

### 6.2. Results

주목할점은 단순한 success rate와 throughput(success rate/10 min)을 report함. 그리고 success rate 자체는 base와 비슷하더라도 RLT 적용하니까 throughput이 많이 좋아진 경우도 있었다고 함.

base VLA는 contact 근처에서 반복적으로 probing하려는 행동을 보였으나, RLT는 그런 것 없이 부드럽게 수행함. 또한 demo에는 없던 전략을 보이기도 했는데, 힘으로 우겨 넣는 모습도 보임.
