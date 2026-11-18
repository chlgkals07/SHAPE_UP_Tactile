# Lingbot-Touch

**Title:** Learning Heterogeneous Tactile Representation for General Dexterous Manipulation

- **Venue:** arXiv
- **arXiv submitted:** 2026.11.09

[Learning Heterogeneous Tactile Representation for General...](https://arxiv.org/abs/2611.12806)

## 0. Takeaway

좋은 encoder이고 범용적으로 쓸 수 있어 보임.

일단 논문만 보았을 때는 taxel 수에 큰 관련 없이 적용가능한 것 같아서 우리 모델에도 사용가능할 것으로 추정중.

다만 논문의 한계에서 언급했듯이 fingertip 위주로 진행했다고 함. 그래서 우리는 손가락 마디에도 센서가 있어서 그냥 사용하여도 될지는 약간 미지수이긴 하나 안 쓰는 것보다는 낫지 않을까하는것이 내 생각.

그리고 특히 5D RoPE를 적용하였는데 내가 처음에 했던 생각과 비슷한 아이디어이고 이것으로 잘 training하면 X, Y, Z 기반 RoPE도 효과를 볼 수 있긴 할 것 같음.

## 1. Problem

1. common input format이 없음.

   sensor type에 따라서 channel, layout, resolution, sampling rate가 다름.

2. large curated dataset이 없음.

3. 정형화된 tactile sensor representation recipe가 없음.

   tactile이 도움이 된다는 연구들은 존재하지만 sensor-specfic하거나 개별적인 task에 대한 것이며 shared representation으로 비교한 것이 없음.

## 2. Contribution

1. Lingbot-Touch: every sensor’s taxel을 canonical fiungertip space로 mapping해해서 모델이 sensor-specific array를 보는 것이 아니라 finger 내에서 position을 보도록.

2. JEPA 아키텍처로 training

3. 5000 hours corpus

4. outperform FTP-1 in real. RL on Lingbot-Touch feature better than task-specific CNM and w/o touch

## 3. Novelty

### 3.1. Tactile Sensing

다양한 측정 메커니즘의 센서들이 존재

ex) Paxini: hall-effect sensing

하지만 이러한 기술들은 결국 shared propertie of physical contact를 측정하고자 하는 것임. 하지만 channel semantics, spatial resolution, sampling rate, sensing layout 등이 너무나 다르고, 그래서 우리는 unified spatiotemporal contact representation으로 모델링함.

### 3.2. Tactile Representation Learning

Representation Learning: joint-embedding(DINO, SigLip), generative architecture(MAE), JEPA(JEPA-familiy)

Tactile Representation Learning: Sparsh, T3, UniTouch, AnyTouch, HTT, FTP-1

우리는 high sparsity, low SNR, multi-source heterogeneity을 다루고자 하며, multi-branch tokenizer를 활용하고자 함.

## 4. Method & Implementation

Formulation: Tactile Token - num of frames X total number of valid taxels X 3 (channel)

### 4.1. Touch at Scale: 5,000 Hours from Tactile Gloves and Robot Hands

### 4.2. Tactile-JEPA: Predicting Contact in Latent Space

valid position에 대해서 masked set과 visible set으로 나누고 visible set을 context encoder로.

target encoder는 전체 clip을 처리하고 predictor는 context encoder의 output을 가지고 target encoder의 output을 prediction.

**Canonical fingertip space and token addresses**

Taxel indices는 sensor-local oerdering을 처리하는 것이지 sensor간의 physical location(geometry)를 처리하지 않음.

그래서 tactile measurement의 continuous 3D coordinate와 finger identity를 모델링하고 every sensor의 coodinates를 하나의 canonical fingertip space에 mapping하고자 함.

복잡한 매핑을 거쳐서 5D address(temporal window index, finger index, 3D canonical position)를 만들고 5D address를 RoPE로 model에 주입.

그리고 JEPA로 학습

### 4.3. Layout-Agnostic Augmentation

canonical fingertip은 모든 센서의 taxel이 comparable coordinate를 가지게 하지만, 그것 만으로 encoder가 layout에 indifferent하게 하는 것은 아님.

### 4.4. Implementation Details

Lingbot-Touch-Tiny: 5.46M

Lingbot-Touch-Small: 21.76M

Both use 12 Transformer layers, with embedding dimensions of 192 and 384, respectively.

실험 내내 tokenizer와 encoder는 frozen으로 두고 진행

## 5. Experiment: Representation

- **Q1:** Does the representation expose the physics of contact, and does it do so on a sensor the model never saw?

- **Q2:** How does it change with more hours, more sensor types, and a larger model (scaling)

- **Q3:** Which design decisions matter, from the latent-prediction objective to masking and augmentation (JEPA vs MAE)

### 5.1. Evaluation Setup

V-JEPA eval protocol에 따라서 encoder feature를 linear probing 하는 형식으로 training하고 평가 진행

**Task**

- fingertip force recovery

- contact center estimation

- contact area estimation

- future force prediction

- tactile-to-video retrieval

**Baseline**

FTP-1 encoder

## 6. Result: Representation

### 6.1. Contact Physics from a Frozen Encoder: Probing the tactile Representation

FTP-1 encoder와 probing으로 비교했음.

FTP-1보다 월등히 좋은 성능 보임.

특히 unseen sensor에서 그 차이가 더 부각됨.

### 6.2. Scaling. Model, Data, Hours,

data의 total hours가 많아지니까 성능이 좋아졌으며, 여러가지 multi source sensor가 들어가는 것은 그렇게 중요하지 않았음. 따라서 encoder가 학습하는 것은 각 sensor의 특성이 아니라 contact physics를 학습하는 것임 .그렇기 때문에 우리도 우리가 나중에 deploy할 환경에서의 데이터가 아니라 human이 장갑끼고 수집한 데이터를 이용하게 된 동기이기도 하다라고 설명.

### 6.3. JEPA vs MAE vs VAE

training dynamics가 다르더라. 특히 JEPA가 달랐는데 JEPA 특성상 target encoder가 evolve하면서 나타나는 현상일 수 있음.

JEPA가 월등히 좋았음.

### 6.4. Ablation

### 6.5. What the Latent Space Encodes

Non-contact windows form one cluster, and contact windows form continuous structures that track the strengthening and weakening of the responses.

epresentation therefore preserves continuous variation within a contact episode

policy가 이러한 feature를 필요로 한다고 그러고 말함.

## 7. Experiment: Robot Learning

- **Q1:** Does adding the tokens improve imitation-learning and VLA policies on real hardware, and by how much more than adding the raw tactile signal

- **Q2:** Does it improve reinforcement learning in simulation, in final performance and in the stability of training

- **Q3:** And does representation quality, as measured by probing, carry over to the policy when we vary the pretraining data or swap in another tactile encoder

### 7.1. Setup and Implementation

trainable cross-attention readout으로 encoder의 output을 40 token per hand로 압축

그 다음 policy에 넣을 수 있는 dimension으로 projection

T-Rex, pi05, Lingbot-VA에 적용함.

Baselines

original policy, raw tactile-added policy, Ours-added policy

## 8. Result: Robot Learning

일단 policy간의 비교에서는 T-Rex에 넣은 것이 제일 잘 했음. 애초에 tactile modality를 처리하던 policy라서 결과도 좋게 나온 듯 하다

그리고 raw tactile을 보면은 아예 tactile 사용하지 않는 거랑 큰 차이가 없는 경우가 많음. 따라서 pretrained encoder를 사용하는 것이 확실히 좋고 그 token이 무언가 meaning을 가지고 있는 것 같음

추가로 simulation에서 PPO로도 실험 진행했음.

## 9. Limitations

Finally, the canonical geometry and pretraining layouts focus on the fingertips, leaving contacts on the palm and elsewhere along the fingers underrepresented. Extending layout coverage from the fingertips to the whole hand is an important next step.

---

**Notion 원문:** https://app.notion.com/p/41abe171a762804f8cabe65d97b41421
