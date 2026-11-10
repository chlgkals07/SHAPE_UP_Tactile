# ForceRFT

**Title:** ForceRFT: Refining VLA Actions through Force-Guided Residual Reinforcement Learning

- **Venue:** arXiv
- **arXiv submitted:** 2026.09.19
- **Paper:** https://arxiv.org/abs/2609.22840

## 0. Takeaway

Hz와 chunk horizon, executed horizon의 관계를 식으로 작성해줌.

진짜 별로다.

residual RL. wrench 정보 사용. SmolVLA backbone

그리고 굳이 따지면 human-intervention에 대해서 learning 시에 어떻게 할 지.

wrench 정보 쓰고 그러는 거는 사실상 ForceVLA랑 거의 같아서 노벨티 없고, human-intervention 그것도 큰 노벨티는 없는 것 같음. 접근이 매우 단순하고, 아니면 그것을 더 파서 체계화하던가. 이도저도 아닌 애매한 논문.

→ 우리는 그만큼 dexterous finger의 tactile을 어떻게 representation할 것인가가 중요한 것 같음

## 1. Problem

demonstration만으로 학습된 policy의 경우 recovery behavior가 fixed dataset에서만 학습된다.

그래서 Human-in-the-loop, intervention-in-the-loop, Reward-driven 등의 방법이 있었고, contact-rich manipulation에서 wrist feedback을 사용하여 policy를 만들게 되었다.

## 2. Contribution

1. introduce ForceRFT, force-guided residual RL. combines frozen, force-conditioned VLA prior with command-level residual corrections driven by wrist feedback.

2. formulate online residual learning → 이걸 contribution으로 볼 수 있나..?????? 누구나 할 수 있는거지 않나, 그리고 사실상 (1)에 포함되는 것이지 않나. method를 읽어보니 뭐 복잡하게 formulation을 적어두긴 했는데 결국 absolute/relative action format 때문에 나오는 formulation, residual이라 나오는 formulation이고 그리고 TD learning은 똑같고, 그나마 다른 거는 human intervention일 때는 value guided RL로 안 하고 human intervention에 대해서는 imitation으로 처리하고 그때 value도 끊어서 가겠다인데… 흠….

3. show higher suceess rate than baselines.

## 3. Novelty

### 3.1. VLA for Contact-Rich Manipulation

force-aware multimodal fusion(Force-VLA) 같은 것에다가 우리는 online RL correction 붙임.

### 3.2. Online RL for VLA

TORL-VLA는 measure, predicted wrench를 이용하여 action을 refinement.

Facet-0은 joint action wrench를 policy를 guide하기 위해서 사용

그래서 우리의 ForceRFT는 measured wrist feedback을 어떻게 online RL에 이용할 것인가.

## 4. Method & Implementation

### 4.1. Force-Conditioned Decoding

ForceVLA 방식대로 wrench encoder와 attention-based fusion module을 구성해서 SmolVLA의 action expert에 fused context를 제공.

이를 통해 force-conditioned prior VLA를 만듦.

### 4.2. Residual Adaptation

residual actor는 state, base motion, wrist load, its change를 입력으로 받아서 constant scaling tanh 합수의 입력을 생성하여 constant 만큼 bounded 되는 bounded actor가 됨.

### 4.3. Human-in-the-loop RL

## 5. Experiment

- **Q1:** force-conditioned action generation가 force input 없는 policy보다 좋아?

- **Q2:** value-based residual optimization이 imitation보다 좋아?

- **Q3:** online interaction하니까 점점 success 좋아져?

- **Q4:** decision-time wrist wrench가 residual adaptation에 기여해?

좀 애매하냐.

### 5.1. Tasks

Insertion, assembly, wiping

### 5.2. Evaluation

30 trials per task → 50번은 해야 한다고 생각함. rebuttal에서 20~30번 해서 지적받은 케이스 여러 봤음.

### 5.3. Baselines

- SmolVLA-SFT w/o force
- force-conditioned prior without residual correction
- residual imitation
- ForceRFT

## 6. Result

### 6.1. Main

whiteboard wiping에서 ForceRFT마저도 11/30 나왔는데, 이러면 이거 절대적으로 이들의 방법론이 문제인 것 아닌가…? 이렇게 낮게 나와도 될지 모르겠는데.

혹은 SmolVLA prior를 사용해서 그런 것 같다는 생각도 듦. 사실 그래서 더 연구의 신뢰성이 안 감. 왜 pi를 안 쓴 것인지.

> “showing that the gains on insertion and assembly do not yet extend to equally reliable cleaning and autonomous termination.”
