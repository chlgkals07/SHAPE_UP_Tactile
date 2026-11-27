# AT-VLA

**Title:** AT-VLA: Adaptive Tactile Injection for Enhanced Feedback Reaction in Vision-Language-Action Models

- **Venue:** CVPR 2026

- **arXiv submitted:** 2026.05.08

[AT-VLA: Adaptive Tactile Injection for Enhanced Feedback Reaction...](https://arxiv.org/abs/2605.07308)

## 0. Takeaway

솔직히 baseline 비교가 좀 약하다고 생각하는데 어떻게 accept 된 것인지 정말 의문임.

게다가 cvpr인데 vision이랑 무슨 상관인 것이지……..

rebuttal 찾고 싶음.

아이디어는 심플하지만 중요하긴 함.

근데 intuition도 그냥 attn map이랑 task sr 비교인데 task sr을 보여주는 task도 되게 적은데….

흠흠흠흠

## 1. Problem

기존 VLA 모델은 tactile signal을 사용하지 않았고 또한 pretrained open-source dataset의 경우 tactile 정보를 가지고 있는 것이 드물다.

그래서 pretrained model에 new modality, tactile을 통합하려는 연구들 (multimodal alignment, representation learning, CoT) 등이 나왔음.

하지만 이렇게 tactile feedback을 model에 직접적으로 넣어버리는 것은 pretrained knowledge를 손상시킬 수 있음.

또한 상대적으로 느린 VLA의 inference speed는 high-freq tactile feedback에 반응하기가 어려움.

자기들이 처음으로 pretrained capa perserving과 tactile input integrating의 balance를 맞추면서도 rapid tactile feedback reaction을 한다고 주장.

## 2. Contribution

1. adaptive tactile injection, first attempt to balance pretrained knowledge with learning of newly tactile representation

2. tactile reaction dual-stream, leveraging high-freq tactile feedback

3. show good performance on contact rich task and maintain strong good performance even in the absence of tactile signals

## 3. Novelty

### 3.1. VLA

기존 vla의 fast stream으로 visual이나 point cloud를 사용하는 것과 다르게 우린 fast stream으로 high-freq tactile feedback을 사용.

### 3.2. Interaction Feedback Policies

RDP, TLA, TA-VLA,

이들은 대부분 model이 tactile feedback의 semantic meaning을 해석하는 것에 목적을 두었지, model의 original visual perception ability를 해치게 되는데, 우리는 이와 다르게 pretrained knowledge와 new tactile feedback balance를 맞춤.

그리고 기존 tactile gate works와는 다르게 우리는 pretrained VLA의 특성을 반영하여, tactile gate가 activated일 때 tactile feature를 통합함.

그리고 우리는 서로 다른 모달리티를 동일 freq로 통제하는 것이 아니라 각 modality에 맞게 처리함.

## 4. Method & Implementation

### 4.0. Motivation

fine tuning w/o tactile, fine tuning w/ directly incorporating tactile 비교 했음

tactile introduced finetunign의 경우에 task performance도 떨어졌으며 attn 분석했을 때 target object에 벗어나는 것을 확인할 수 있었음.

“We hypothesize that the addition of token sequences from newly introduced modalities can interfere with the pretrained model’s perceptual focus”

### 4.1. Adaptive Tactile Injection

vision 정보는 localization에 대한 contextual 정보를 제공하고 tactile 정보는 physical contact에 대한 detail한 feedback을 제공.

그래서 non-contact phase에서는 vanilla VLA의 capa를 유지하고자 하는 것이 핵심임.

**Tactile Gate**

Tactile gate는 tactile feedback이 필요할 때 자동으로 활성화.

MLP로 contact or non-contact를 indicate하도록 함. contact state를 나타내는 score를 output. training data에서 이 contact state에 대해서 manually annotation 진행. 그리고 BCE로 training.

**Adaptive Cross Attention**

vanilla VLA의 attention에서는 state token은 query, vision과 text token은 key, value임.

이때 우리는 tactile gate가 활성화 될 때는 state token을 tactile token으로 대체해서 사용함.

그래서 contact이 일어나면 model은 tactile feedback을 사용.

그래서 최대한 pretrained representation을 보존할 수 있음.

preserve pretrained representations to greatest extent.

### 4.2. Effective Tactile Reaction Dual-Stream

tactile gate가 켜졌을 때 model이 어떻게 효과적으로 respond할 것인가가 중요함.

1. rapid reaction (2) tactile understanding

Rapid Reaction을 위해서 two stream으로 나누어서 slow stream은 낮은 inference speed로 동작한다. 이는 visual, language input이 VLM backbone에서 처리되는 것.

fast stream은 high inference speed로 동작하며 tactile feedback을 interpret.

slow stream의 visual, lang은 chunk H step에 대한 conditioning을 담당

fast stream에서 action expert가 recent tactile feedback을 ㅣ이용한다. 즉 slow stream과는 다르게 주기적으로 update한다.

그래서 inference에서 어떻게 할 건데?

gr00t와 fast-in-slow에서 영감을 받아서 3:1 비율로 stream을 사용. 그래서 slow stream이 single inference하면 fast가 3번 inference.

## 5. Experiment

### 5.1. Hardware Setup

dual 7 DoF, gripper,

### 5.2. Tasks

30\~50 demo

15 eval per tasks

Contact: Unzip Bag, Stamp, Wipe Vase, Unscrew Lid,

UnContact: PnP, Open Drawer

### 5.3. Baselines

GO-1, pi05, VTLA, RDP,

## 6. Result

우리꺼 잘 해요

그리고 pnp, open drawer에서 tactile input을 inference에만 안 주는 식으로 하니까 pi나 go-1이랑 성능 거의 비슷하게 유지됨. 게다가 그 상태에서 tactile input 주면 tactile input이 필요한 stamp에서는 성능 개선도 됨.

---

**Notion 원문:** https://app.notion.com/p/425be171a76280368446fd8c661eb349
