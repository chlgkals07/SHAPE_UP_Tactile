# VTAO-BiManip

**Title:** VTAO-BiManip: Masked Visual-Tactile-Action Pre-training with Object Understanding for Bimanual Dexterous Manipulation

- **Venue:** IROS 2025

- **arXiv submitted:** 2025.01.07

[VTAO-BiManip: Masked Visual-Tactile-Action Pre-training with...](https://arxiv.org/abs/2501.03606)

## 0. Takeaway

encoder에 multi modal 넣고 fusion한다, 그리고 fusion token을 RL policy에 주겠다는 것은 우리의 연구와 같은 방향성이지만

해결하고자 하는 문제가 다르고, 이제는 좀 oudate 된 느낌이고, task도 하나밖에 안 했고, 여러모로 아쉽다

나중에 related work로는 쓸 수 있겠다

## 1. Problem

dexterous manipulation의 recent work는 single-hand scenario라고 깔고 감. 2025년에 올라왔는데 이때만 해도 이랬다니…

기존 visual-tactile pretraining은 constrained task setup임.

1. kinematic coordination limitation: vision과 binary tactile sensing은 single hand finger에는 도움이 되지만 inter-hand에 관한 거는 어려움.

2. object-state decoupling: real time handling이 잘 안 됨. object pose

3. sub-skill composability: 여러 process를 consistent하게 처리하지 못함.

## 2. Contribution

1. visual-tactile-action pretraining with obejct underdstanding for multi modal perception and curriculum RL

2. augment pretraining with object pose and size estimation forcing the encoder to learn geometry-aware representation. object의 pose와 dimension을 recon하는 방식으로 학습

3. two-stage curriculum RL: 처음에는 object를 table에 fix 해두고, 그 다음에는 fix 안 하고.

## 3. Novelty

### 3.1. Multimodal Pretraining for Robotics

action modality와 함께 pretraining하는 것은 end-effector를 위주로 햇고 dexterous 안 함.

visuo-tactile fusion의 효과는 이미 여러 강조 되었으나 bimanipulation은 아직 잘 안 다루어짐.

그래서 우리는 bimanipulation에 하고자 함.

### 3.2. Robotic Bimanual Manipulation

challenges such as retargeting errors and motion retargeting latency limit their practical use.

sim-to-real approaches들이 있었는데 이들은 single dexterous hand나 dual-gripper에 적용.

Multimodal data도 dual gripper나 single dexterous에서나 했음

우리의 work은 multimodal sensing을 dual dexterous hand에 적용하고자 함.

## 4. Method & Implementation

### 4.1. Masked VTAO Transformer for Pre-Training

encoder-decoder architecture

#### 4.1.1. Encoder

multimodal encoder는 visual, tactile, current action input을 받아서 각각을 latent token으로 projection. 그리고 encoder 내에서 attention함.

그 다음 decoder가 original sensor modality는 recon, action은 future action을 prediction하고 obejct state도 estimate.

각 modality 별로 tokenization을 진행하는데

tactile을 binary로 하는 것에 대한 이유는

“This binarization follows the design in \[6\], aiming to reduce the sim-to-real gap and eliminate the need for precise calibration across taxels” 라고 함. → 결국 네트워크 한계이니까, 더 잘 representation learning하면 해결된다는 얘기네.

#### 4.1.2. Decoder

recon image, recon tactile, recon current action, predict future action, recon 6D pose and 3D size of object

### 4.3. Curriculum RL for Dexterous Bimanual Manipulation

encoder의 fusion token과 hand의 proprioception의 MLP 태운 거를 policy가 받음

RL은 첫 stage에서는 bottle body를 table에 fix해두고 진행.

두번째 stagr에서는 bottle을 table로부터 떼어내고 진행.

### 4.4. Hardware and Implementation Details

tactile signals are binarized with aλ = 0.4V threshold → binary tactie 사용함 → 끝끝끝

시뮬레이션 RL임… .sim-to-real 했음. 근데 메인은 sim-to-sim 평가고 sim-to-real 된다라는 것만 보여준 정도임

## 5. Experiment

결과는 안 보겠음.

## 6. Result

---

**Notion 원문:** https://app.notion.com/p/416be171a76280f38d4ad3efbadade31
