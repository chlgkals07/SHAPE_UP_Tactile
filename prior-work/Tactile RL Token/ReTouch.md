# ReTouch

**Title:** ReTouch: Empowering Contact-Rich Dexterous Manipulation with Online-Refined Tactile Prediction

- **Venue:** ECCV 2026 DexHand Workshop
- **arXiv submitted:** 2026.08.03
- **Paper:** https://arxiv.org/abs/2608.01824

## 0. Takeaway

Dexterous Tactile의 중요성과 Tactile-enhanced VLA의 동향 참고하기 좋음.

chunk 내에서 high-frequency로 refinement하고자 하는 것은 우리의 연구와 align되어 있음.

다만 online이라고 해서 RL은 아니고 방법론 자체는 Tacforcing처럼 SFT로 online refinement를 이끌어내겠다는 접근.

## 1. Problem

tactile-aware policies를 dexterous manipulation에 적용하는데 있어 어려움이 있다.

1. dextrous hand는 dense tactile observation을 주는데, task-relevant signal 자체는 sparse하고 specific finger regions에 국소적임.

   일반적인 방법은 tactile signal을 flatten해서 사용하는데, 그렇게 되면 finger의 spatial 구조가 없어지고 policy가 fine-grained한 finger 조작을 contat 변화와 얼라인 시키지 못함.

2. contact state는 매우 빠르게 변화함. 그래서 chunk 내에서 후반부로 가면 초기에 사용한 tactile signal이 안 맞음. 그래서 특히 future tactile prediction의 경우에 high-rate로 재추정하지 않고 그래서 잘못된 가이드를 주게 됨.

## 2. Contribution

1. introduce an online tactile-prediction refinement mechanism that jointly updates future tactile predictions and action chunks

2. tactile-Patch Encoder for dexterous hands that preserves finger identity and local contact structure

3. build dataset with 7 dexterous contact-rich manipulation on XHand-UR7e

## 3. Novelty

최근 future tactile을 action chunk를 생성할 때 함께 prediction하고, 혹은 action chunk를 refinement하기 위해서 fast feedback을 사용한다. 하지만 이는 predictive reference(predicted future tactile을 말하는 것 같음)을 high-rate tactile updata와 함께 re-estimate하지는 않는다.

→ 우리는 topology-aware, finger-wise tactile representations를 고안하고, future tactile latent를 recursive하게 maintain하는 구조를 제안한다.

## 4. Method & Implementation

### 4.1. Structured Tactile Patch Encoding

Tactile Patch encoder partitions the 120 3D force taxels on each finger into five functional patches.

Patch-Informed Tokenizer projects these local responses and adds finger-identity and patch-position embeddings

aggregates the five patch features of each finger into a compact patch-informed finger token, resulting in five tokens.

three prediction heads를 달아서 다시 원래 정보로 recovery할 수 있도록 encoder를 pretraining.

### 4.2. Learning Action-Relevant Tactile Latents

high-dimensional taxel-level signal을 recon하지 말고 future tactile latents를 학습

**Hindsight Action Expert (HAE):** GT future tactile로부터 supervision target을 구성

**Foresight Action Expert (FAE):** context로부터 corresponding latents를 예측

HAE는 GT tactile로부터 action을 generation 하는 것으로 training 되며 이후에 HAE의 특정 layer의 feature가 FAE를 위한 target으로 쓰인다.

FAE는 future tactile query tokens를 넣고 걔한테 predictive 정보가 담기도록 HAE에서 오는 feature랑 alignment. (similar to REPA)

### 4.3. Online Tactile Prediction Refinement

multi-rate asynchronous execution

VLM process at 9Hz and caches context

Foresight Action Expert runs at 36 Hz and is invoked multiple times between consecutive VLM updates. cached semantic context과 chunk가 시작할 때의 robot state는 재사용하고 tactile context는 updated된다.

FAE의 each call마다 tactile query token은 predicted feature로부터 updated되어 다시 FAE의 input으로 들어간다. 그리고 FAE는 action과 future tactile latent를 refine한다(re-generation)

→ allows the Foresight Action Expert to update tactile predictions and actions without rerunning the VLM.

### 4.4. Implementation Details

16 action chunk horizon

vlm at 9 Hz, action expert at 36 Hz.

Tactile-Patch Encoder는 20K 학습했고, 이후 policy는 모든 task에 대해 joint하게 80K 학습.

training 동안 chunk 내에서 intermediate step으로 {4, 8, 12}를 sampling해서 사용.

## 5. Experiment

### 5.1. Tasks

1. Pipette Press

2. Bottle Grasp: grasping transparent water bottles with different weight

3. Cob Grasp: pinching orange cobs at different height

4. Sponge Wipe: wiping on a whiteboard

5. Button Press, pressing small buttons at different heights. (→ critical한지 모르겠네)

6. Cabinet Retrieval,

7. Liquid Transfer

### 5.2. Baselines

ViTacFormer, RDP, Tactile-VLA, pi0, pi05, pi0+Tactile, pi05+Tactile

### 5.3. Details

**Hardware:** XHand-UR7e. XHand는 내장 tactile sensor를 가지는 것 같고 finger마다 120개의 3 dimesnional taxel.

## 6. Result

### 6.1. Main

단순 grasping task보다는 wiping board나 cabinet retrieval, liquid transfer처럼 contact state가 빠르게 변하거나, occlusion 등으로 visual 정보가 가려져서 tactile에 의존해야 하거나 하는 task에서 다른 baseline보다 확실히 gain이 있었음.

단순 grasping task에서는 향상이 있긴 했지만 위의 태스크에서 더 부각.

### 6.2. Tactile Encoding

encoding된 것을 다시 recon해서 GT랑 비교 진행.

dense taxel 입력을 single token per finger로 압축했을 때 효과적인 것으로 보여줌.

### 6.3. Refinement of Tactile Prediction

**One shot variant:** ReTouch(ours)처럼 남아있는 action을 re-generation하기는 하지만 이때 새롭게 들어오는 tactile을 사용하는 것이 아닌 chunk의 시작에서 들어왔던 tactile을 다시 사용.

MSE로 eval해서 one shot variant보다 자기들 방식이 더 좋았다고 보임.
