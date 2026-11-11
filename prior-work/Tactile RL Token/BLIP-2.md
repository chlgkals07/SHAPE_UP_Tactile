# BLIP-2

**Title:** BLIP-2: Bootstrapping Language-Image Pre-training with Frozen Image Encoders and Large Language Models

- **Venue:** ICML 2023

- **arXiv submitted:** 2023.01.30

[BLIP-2: Bootstrapping Language-Image Pre-training with Frozen...](https://arxiv.org/abs/2301.12597)

## 1. Problem

most state-of-the-art vision-language models incur a high computation cost during pre-training.

it is the key to facilitate cross-modal alignment.

## 2. Contribution

1. bridge the modality gap using a Q-former pretrained.

2. BLIP-2 perform zero-shot image-to-test generation

3. BLIP-2 is more compute-efficient due to the use of frozen unimodels and lightweight Q-former.

## 3. Novelty

기존 cross-modal alignment 관련 연구들은 image-to-text generation loss(text modeling loss)를 사용하였는데, 이들은 이것이 modality gap을 제대로 처리하기엔 부족하다고 보았음. 그래서 vision-language representation learning 도입함.

## 4. Method & Implementation

two stage pipeline

1. vision-language representation learning

2. vision-to-language generative learning

### 4.1. Model Architecture

Q-former: bridge the gap between a frozen image encoder and a frozen LLM

extracts a fixed number of output features from the image encoder

1. image transformer that interacts with frozen image encoder

2. text transformer that can function as both a text encoder and text decoder

Query token은 pretraining task에 따라서 text에 어떻게 attention할 것인지 mask를 다르게 함.

self-attention layer는 BERT 사용하고 cross-attention layer는 random.

### 4.2. Vision-Language Representation Learning

three pretraining objective

#### 4.2.1. Image-Text Contrastive Learning

image와 text로 contrastive learning.

#### 4.2.2. Image-Grounded Text Generation

image를 보고 text를 generation. 따라서 mask의 경우 text만 query에 attend할 수 있음.

#### 4.2.3. Image-Text Matching

image text pair가 match인지 아닌지 predict.

## 5. Experiment

## 6. Result

---

**Notion 원문:** https://app.notion.com/p/414be171a7628007b575f068537c8cfc
