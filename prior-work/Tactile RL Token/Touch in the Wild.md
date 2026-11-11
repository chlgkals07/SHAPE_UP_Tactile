# Touch in the Wild

**Title:** Touch in the Wild: Learning Fine-Grained Manipulation with a Portable Visuo-Tactile Gripper

- **Venue:** NeurIPS 2025

- **arXiv submitted:** 2025.07.20

[Touch in the Wild: Learning Fine-Grained Manipulation with a...](https://arxiv.org/abs/2507.15062)

## 0. Takeway

cross attention으로 modality fusion

rebuttal에서는 하드웨어 만든 거를 좀 좋게 본 듯함.

메서드의 노벨티에 대한 지적이 있긴 함.

그럼에도 하드웨어 시스템을 설계하고, 실험을 통해서 성능 향상이 검증됨을 보인 거로 accept된 듯?

아니 이 정도도 accept이 돼? 하드웨어 제작 때문에 그런가…

## 1. Problem

tactile feedback은 정말 중요하다 when visual information is unreliable due to occlusion, poor lighting, dynamic backgrounds. 그렇지만 최근 존재하는 시스템들은 대부분 visiual sensing에만 의존하며, vision에만 의존하는 것은 시스템이 환경 변화에 취약하게 한다.

visuo-tactile data를 in the wild로 모으는 것은 어렵다.

1. Portable tactile hardware: tactile sensor 들고 다니기 어려움.

2. multimodal data: tactile이나 visual signal은 너무나 달라. 그래서 이들을 효과적으로 representation하는 것은 어려워.

→ present a Portable Visuo-Tactile System for large-scale data collection and multimodal policy learning in real-world settings

## 2. Contribution

1. make lightweight handhled visuo-tactile gripper

2. introduce a masked autoencoding that uses cross-attention

3. in the wild multimodal manipulation dataset

## 3. Novelty

### 3.1. Scalable multi-sensory data and learning

simulated data는 real world data와 gap이 큼.

large-scale data가 있으면 pretraining을 할 수 있어서 참 좋음.

그러한 점에서 in-the-wild로 데이터를 수집하면 좋은데, 기존 시스템은 vision-only가 일반적이었음.

그래서 우리는 portable handheld visuo-tactile system 및 그것으로 수집한 dataset을 제안함.

또한 3D-vitac의 경우 vision과 tactile을 unified 3D sapce에 직접적으로 합쳤는데, 우리는 cross-modal representation learning으로 이를 해결하고자 함.

### 3.2. Visuo-tactile manipulation

prior work는 optical tactile sensor를 많이들 사용함.

우리는 contact surface에서 force distribution을 측정하는 array-based sensor를 이용함.

또한 우리는 large-scale in-the-wild visuo-tactile dataset을 수집하고 공개함.

그리고 ViTaMIN이랑 우리가 하는 거 비슷한 목적인 거 인정하는데, 시스템 디자인, learning 전략, task 다르니까 이해해줘.

## 4. Method & Implementation

### 4.1. Visuo-Tactile Data Collection System

out of our interest.

### 4.2. Visuo-Tactile Representation and Policy Learning

#### 4.2.1. Stage 1: Visuo-Tactile Representation Learning

prior work는 contrastive learning으로 해서 fine-grained, geometry-sensitive 압축.

근데 우리는 masked autoencoding objective. encoder가 tactile-specific info를 retain하도록 하도록 objective 구성.

tactile encoder: 24x32 tactile image를 4x4 patch(6 x 8 patch grid)로 만듦. 그 다음 일부는 mask시킴. masked tactile input은 3-layer CNN으로 d-dimensional embedding으로 처리됨.

vision encoder:  CLIP encoder 사용. 그리고 CLS token을 visual embedding으로.

Cross-modal fusion: tactile과 visual feature에 대해서 서로 cross-attention하고 updated embedding을 concat.

Tactile Reconstruction Decoder: 2-layer MLP+sigmoid activation으로 tactile image를 recon.

#### 4.2.2. Stage 2: Policy Learning via Behavior Cloning

diffusion policy는 proprioceptive state와 encoder에서 나온 fused visuo-tactile embedding을 입력으로 함.

아키텍처 및 training은 기본적인 Diffusion Policy.

## 5. Experiment

- **Q1:** touch가 fine-grained manipulation에 도움 돼?

- **Q2:** visuo-tactile pretraining은 policy robustness에 도움 돼?

- **Q3:** pretraining의 variation이 task performance에 어떤 영향을 줘?

### 5.1. Evaluating the visuo-tactile representation

1. test cross-modal reconstruction.

   masked tactile and RGB input 주고서 missing tactile signal을 잘 recover하는지

2. final ViT layer의 attention map을 visualize

   model이 contact-relevant regions를 잘 attend하는 것인지 확인

### 5.2. Tasks

1. Test Tube Collection

   박스 안에 있는 tube를 집고서 test tube rack에 꽂아 넣기

2. Pencil Insertion

   연필을 연필깎이에 꽂기

3. Fluid Transfer

   스포이드로 fluid 옮기기

4. Whiteboard Erasing

   화이트보드 지우기

20 trials with moderate randomization of initial robot position and env conditions

### 5.3. Baselines

vision-only, w/o cross-attention, w/o pretraining, ours.

## 6. Result

task success rate가 너무 높은데,

training demo를 190개, 170개 이렇게 사용해서 너무 많이 사용한 거 아닌가 싶음.

또 20 trial도 너무 적은 거 아닌가 싶음

아 ablation에서 demo 숫자 줄여서 보여줬네. diffusion poilicy라서 demo가 많아야 할 것 같기도 하고

---

**Notion 원문:** https://app.notion.com/p/415be171a762808e98e4c702b5b76433
