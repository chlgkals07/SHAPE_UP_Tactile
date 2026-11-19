# VTT

**Title:** Visuo-Tactile Transformers for Manipulation

- **Venue:** CoRL 2022

- **arXiv submitted:** 2022.09.30

[Visuo-Tactile Transformers for Manipulation](https://arxiv.org/abs/2210.00121)

## 0. Takeaway

우리랑 컨셉은 꽤 비슷. multimodal fusion 잘 하고 그것을 RL에 적용하자

다만 tactile signal이 적고, gripper이고 vla prior 안 사용하고, encoder 구조도 단순해서 발전시킬 여지가 너무나 많음.

그렇기 때문에 더더욱 이러한 단순히 transformer에 넣는 encoder가 아니라 더 나은 novel good encoder가 필요해보임.

## 1. Problem

high dimensional observation spaces에서 learning하는 것은 어려움. 특히나 data가 부족한 robotics에서는 이것이 더욱 한계로 다가온다.

그래서 최근 representation learning 흐름은 “compact latent representation”을 만드는 것이다. 그리고 이 compact representation은 policy와 함께 학습되어 policy 학습에서 stability, sample-efficiency를 제공한다.

그러나 visuo-tactile representation learning은 적다. 물론 기존 방법들이 있긴 하나 attention사용하는 것은 없었다. 또한 in-contact, out-of-contact 같은 fine detail 같은 거는 이미지로 만은 한계가 있다.

## 2. Contribution

1. vision과 touch로부터 multimodal feedback을 반영하는 VTT

2. spatially-aware attention on visual task feature using tactile feedback

3. cross-modal attn이 spatially distributed latent를 만들고 그 결과 4 sim, 1 real에서 잘 하더라.

## 3. Novelty

### 3.1. RL

high dimensional obs space를 compact representation space로 학습. latent dynamics model.

그 후에 이를 이용해 planning이나 model-based RL 진행.

다만 존재하는 works은 visual feedback에 의존. 우리는 visuo-tactile로 multimodal 진행.

### 3.2. Visuo-Tactile Representation Learning

Making sense of vision and touch: Self-supervised learning of multimodal representations for contact-rich tasks

Making sense of vision and touch: Learning multimodal representations for contact-rich tasks

이 두 논문의 encoder를 basekine으로 사용.

차이점은 VTT(ours)는 attention 이용해서 multimodal latent heatmap을 학습. VTT의 spatially-aware cross attn이 훨씬 효과적일 것이다라는 것이 이들의 가정임.

### 3.3. Transformer

transformer와 ViT를 visuo-tactile로 확장.

## 4. Method & Implementation

1. fusing visuo-tactile inputs with self and cross-modal attention mechanisms

2. learned contact, alignment, position/modality embeddings

**Modality Patches**

vision token은 ViT 방식으로 tokenized.

tactile은 reaction force와 torque로 patch되고 linear projection

**Attention**

just bidirectional attention

**Learned Embedding**

contact embedding: contact state를 구별. single token이고 contact embedding은 final layer에서 head 통과하고 loss 계산됨.

alignment embedding: modality가 temporally align되어 있는지 아닌지로 loss 계산.

position/modality embedding: added embedding. pos랑 mod 합쳐서 single token임.

**Discussion of Compressed Representation Head**

transformer 통과한 모든 token을 전부 다 쓰면 high dimension인까 일단 MLP 통과해서 각 토큰의 dimension을 낮추고, dimension을 잘 돌려서(concat을 잘 해서?) single token으로 만들어 버림.

**RL**

visual occlusion과 high level의 tactile perception uncertainty 때문에 POMPD로 formulation.

Stochastic Latent Actor Critic(SLAC) 사용. 얘가 high stochasticiy 수용하고 effective baseline임.

model-learning part와 policy-learning part가 존재.

model-learning part는 VAE로 구현하고,  prior model은 action에 따른 latent dynamics가 propagete됨.

posterior은 observation을 누적.

loss는 visual input recon과 inferring reward, KL loss, 그리고 VTT loss.

policy-learning part는 SAC이용.

## 5. Experiment

### 5.1. Baselines

fusion method: (1) concat, (2) product of expert

### 5.2. Tasks

pushing, door-open, picking, peg-insertion

84x84x3 RGB image, 1x6 wrist reaction wrench

## 6. Result

sim 결과에서 training 빠르고 SR도 좋았음.

lack of contact and alignment losses can cause miscorrelation of images and tactile feedback.

둘 중에서도 contact loss가 더 중요했다고 함.

하나의 latent로의 압축 정도는 적당히가 좋았음.

attention vis에서 contact 없을 때는 vision attn 비중이 높앗고 contact하니까 vision에선 contact한 곳의 attn이 커지고 tactile attn의 비중도 커졌음.

## 7. Limitations

6 dim wrench 사용. signal이 low dimensional.

---

**Notion 원문:** https://app.notion.com/p/41dbe171a76280109c98f2b93f325557
