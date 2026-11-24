# OMNITacTune

**Title:** OMNITACTUNE: Policy-Agnostic Real-World RL for Tactile Residual Adaptation of Visual Policies

- **Venue:** CoRL 2026

- **arXiv submitted:** 2026.07.04

[OmniTacTune: Policy-Agnostic Real-World RL for Tactile Residual...](https://arxiv.org/abs/2607.03723)

## 0. Takeaway

method까지 읽었을 때는 flow model, motion tracker, keypoint extractor와 같은 model을 활용해 추출한 flow를 바탕으로 하여 policy에 tactile feedback RL을 적용할 때 flow를 이용해보자. 그리고 flow를 이용해서 reward를 tactile feedback을 잘 이용할 수 있게 모델링하자에 가까움.

flow를 활용한 모델링이 핵심인 것처럼 느껴짐.

자기네들 방식이 그리고 특정 policy나 tactile representation에 국한되는 것이 아닌 policy agnostic하다는 것을 강조하는 것 같음.

전반적으로 보았을 때 막 다른 주변 SoTA 방식들 가져와서 베이스로 두고 비교하지 않았고

자신들과 유사 메커니즘, 유사 방향성인 방법들 일부 가져와서 자기들의 방법이 없을 때보다 있는 것이 효과적임을 보인 정도. 다만 그 효과를 보일 때 각 메커니즘을 축으로 나누어서 각각의 축에 따라서 잘 보여준 것 같긴 함.

내가 생각하는 다른 점은 critic과 tactile encoder를 warm start로 미리 조금 training한다는 것?

정리하면 일반적인 visual policy에 residual RL할 건데 그 RL actor와 critic은 flow 정보, tactile 정보, base policy의 reference action을 받게 하겠다!

## 1. Problem

scaling visual data만으로는 contact-rich manipulation을 해결할 수 없다. visual policies는 physical interaction 동안 contact이나 force를 측정할 수 없고, 많은 failure가 이 contact에서 발생한다.

기존 tactile method는 particular sensor와 task-specific data에 의존적이었으며, tactile data를 scale하려는 시도가 존재하나 visual data에 비하면 한참 부족하며 visual data와 pair를 이루는 것은 더욱 부족하다.

→ vision provides broad, scalable supervision for task-level behavior, while touch provides local, residual feedback for the last mile of physical interaction

tactile feedback을 사용하는 것에 있어서 sim-to-real RL이나 DAgger 같은 human intervention 방식들이 있으나 sim-to-real은 sim에서 tactile modeling하는 것이 어렵다는 문제, DAgger는 결국 사람의 반복적인 demo가 필요하다는 문제가 있음

→ real-world RL

## 2. Contribution

1. 기존 visual policy에서 residual correction에 tactile adaptation

2. two stage real world RL pipeline w/ multi-sensory reward that combines generated object-centric guidance

3. 성능 좋더라\~. 특히 generalization across task, visual policy, tactile representation

## 3. Novelty

### 3.1. Visual Policy Learning from Robot and Human Data

visual policies still lack direct contact feedback, and we use them as frozen base policies while learning tactile residual corrections for contact-rich execution.

visual policy 다 좋은데 contact feedback 없어. 그러니까 frozen base policy 이용해서 tactile residual correction 배우게 하자.

### 3.2. Tactile and Multi-Sensory Robot Manipulation

Prior works incorporate tactile feedback

1. visuo-tactile sensory fusion

2. slow-fast architecture: RDP

3. tactile world model: LeTac-MPC

4. RL

**most existing visuo-tactile policy learning methods require paired, task-specific visuo-tactile demos to learn policies**

But, 우리는 visual policy 위에서 tactile feedback을 online으로 학습할 것이기 때문에 visuo-tactile policy를 scratch에서 학습할 필요가 없어.

### 3.3. Policy Adaptation for Contact-Rich Manipulation

Policy Adaptation은 additional interaction으로 policy 개선에 도움이 되긴 해

근데 DAgger-style은 repeated human intervention이 필요해.

real-to-sim-to-real은 real-world data collection을 줄이는데 좋기는 한데 contact-rich manipulation은 simulation 환경에 너무 sensitive해.

그래서 우리는 real-world RL할 것이고 adapts a visual base policy with newly introduced tactile feedback.

## 4. Method & Implementation

우리의 접근에 있어 일반적인 RL adaptation과는 다른 한 가지 bottleneck이 있는데 그것은 offline demonstration은 visual only feedback을 준다는 것이다.

warm-start policy가 on-policy data를 제공하지만 이를 이용해 critic을 bootstrap하거나 tactile encoder를 학습하기는 optimize하기 어렵다.

그래서 human and robot data collection, warm-start roll-out, residual RL with object-centric multi-sensory reward를 제안.

### 4.1. Data Collection

meta quest 끼고서 human demo 수집하고 이를 robot frame, robot-aligned traj, robot-frame hand pose로 transformation.

또한 teleoperation으로는 meta quest 끼고 human teleop을 robot pose로 retargeting해서 robot을 teleop 조종.

### 4.2. Learning Visual Base Policies

#### 4.2.1. Flow-based Policy

demonstration에서 object keypoint를 추출하고 motion tracker로 motion도 추출.

fine-tune a pretrained flow generator to predict a complete task-level object flow from the initial observation

그렇게 추출되고 생성된 flow를 바탕으로 하여 model이 action을 prediction하는 flow-based policy 사용

#### 4.2.2. Visual Base Policy

ACT, DP, pi05

teleop demo로 training

### 4.3. Real-World Tactile-Informed Residual RL Adaptation

#### 4.3.1. Stage 1: Warm Start

key challenge는 visuo-tactile offline deom 없이 tactule residual learning을 하는 것.

naive approach는 base policy rollout을 한 후에 SAC를 적용하는 것인데 이는 unstable expolartion을 이끔. random initiallization critic은 unreliable critic value를 만들 것이며 pretrained tactile encoder는 representation shift로 suffer임.

autonomous rollout으로 replay buffer를 채움과 함께 이거로 flow-tactile critic을 bootstrap함. 그리고 AnyTouch 2 pretrained tactile encoder를 사용하고 이는 critic과 함께 optimize됨.

추가적으로 trajectory-level tactile augmentation을 진행하여 tactile representation과 critic의 training을 향상시킴.

#### 4.3.2. Stage 2: Online tactile residual learning.

internal representation과 independent하기 위해서 residual actor는 two policy-independent input을 받음

구체적으로 보면 base action chunk, proprioception, flow representation, tactile representation,

### 4.4. Multi-Sensory Reward Design

multi-sensory reward that combines generated object-centric flow with tactile signal

reaching reward: end-effector가 object의 centeroid를 향해 가는지

grasping reward

flow reward: generated subgoal을 추적하며 할당됨.

safe reward: unsafe interaction을 하면 penalize

### 4.5. Implementation

## 5. Experiment

### 5.1. Hardware and Setting

xArm7 with a gripper mounted with GelSight Mini

### 5.2. Tasks

1. peg-in-hole

2. charger insertion

3. cap opening: tool using task, where the robot use a cap opener to open a bottle cap

4. box opening: tool using task, where the robot use a lever-type bottle opener to open the GelSight box

### 5.3. Baselines

Residual RL: PLD, PLD w/ flow-tactile, ViTAL(residual policy w/o warm-start

Visual Policy: human flow policy, teleop-based flow policy, teleop-based ACT, teleop-based DP, finetuned pi05. peg-in-hole에서만 eval함. 왜? 데이터 모으기 너무 어려웠어..

## 6. Result

### 6.1. Adapting Tactile Feedback with Residual RL

PLD는 unstable training. 왜냐면 scratch에서부터 학습해서. 그래서 bootstraping tactile encoder and critic 중요성 보임.

ViTAL은 scratch에서부터 학습하니까 sample inefficient함.

### 6.2. Adapting Tactile Feedback to Various Base Visual Policies

basline policy에다가 ours residual RL 방법을 추가적으로 적용.

주목할 점은 human flow가 다른 teleop based보다 잘 했다는 것인데 이는 telop data가 low-quality이고 contact-rich manipulation에서 impractical함을 보이는 것이기도 하다.

### 6.3. Comparison with Other Visuo-Tactile Robot Learning Methods

우리의 방법론과 visuo-tactile policy learning method를 비교.

ACT, DP, pi05에 visual과 tactile feature를 concat하는 방식을 활용하여 비교 진행.

공정한 비교를 위해 online training stage만큼의 teleop data를 수집해서 finetuning하여 사용함.

This shows online tactile residual refinement is more effective than learning a visuo-tactile policy from extra teleoperated demonstrations

### 6.4. Adaptation Across Different Tactile Representations

compatiablity를 보이기 위해 진행.

peg-in-hole, charger insetion taks에서

Anytouch 2, Sparsh, T3, 2 layer MLP,

우리의 방법론은 all tactile representation에 대해서 performace를 향상시켰음.

따라서 우리는 특정 세팅에 묶이지 않음.

## 7. Limitations

기본적으로 real world RL이라는 근본적인 한계 가짐.

---

**Notion 원문:** https://app.notion.com/p/421be171a7628063a577e90d3892219e
