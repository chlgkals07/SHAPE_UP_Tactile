# HTT

**Title:** Heterogeneous Tactile Transformer

- **Venue:** CoRL 2026

- **arXiv submitted:** 2026.06.29

[Heterogeneous Tactile Transformer](https://arxiv.org/abs/2606.29948)

## 0. Takeaway

related works에서 aligning tactile data with vision modality에 대한 연구 4가지 나열 해줬는데, 찾아보니 tactile encoder를 학습할 때 vision이랑 align되도록 하거나, 혹은 아예 CLIP 처럼 contrastive로 각 modality의 encoder를 만들거나, 그냥 policy에 넣은 후에 policy 학습과 함께 policy 통과한 feature가 서로align되게 학습.

그래서 순수 representation learning을 위한 연구도 있고, downstream task(QA, manipulation 등)을 위한 learning도 있었음.

MAE로 shared trunk를 통과한 representation이 각 sensor-decoder로 recon 되도록 각 sensor 정보가 shared에서도 보존 되도록 함과 동시에 cross-modal JEPA로 서로 다른 sensor representation을 align함.

우리의 vision과 tactile, 이 두 서로 다른 modality에 대한 것으로 확장해볼 여지가 있을듯?

그리고 논문 자체는 깔끔하게 잘 적힌 느낌. 실험도 딱딱 있고. okay paper

## 1. Problem

tactile sensor의 heterogeneity

optical tactile: detailed spatial and geometric information from elsatomer deformation

array-based tactile: high-rate temporal signals and direct force or pressure

sensor간의 mismatch는 resuable tactile representation, sensor-agnostic policy를 만들기 어렵다.

최근 tactile representation learning에는 많은 연구들이 존재했지만, 대부분은 optical tactile sensor에 집중해있음. 이러한 연구들은 MAE 기반으로 좋은 성능을 보였지만 다른 종류의 sensor signal을 처리하지 못함.

## 2. Contribution

1. Heterogeneous Paried Tactile Dataset(HPT): optical tactile sensor와 array tactile sensor의 paired data

2. Hetergeneous Tactile Transformer(HTT): combine MAE-style masked recon with bidirectional cross-sensor prediction

3. tactile perception tasks, simulated manipulation tasks, real-world robot experiments

## 3. Novelty

### 3.1. Tactile Sensors

optical sesnror: contact properties from images of deformable contact surface. but limited by camera frame rates and sensor-to-sensor variation

array-based sensor: convert physical stumuli into electrical signals. high-rate force or pressure-sensitive measurement. but lower spatial resol.

따라서 두 complementary 특징이 representation learniong에 동기가 됨.

### 3.2. Tactile Datasets for Robot Learning

대부분 public tactile dataset은 optical tactile sensor임.

To our knowledge, large-scale dataset of temporally paired optical and array sensor는 없음.

그래서 우리는 low-cost data collection method 및 large-scale paried dataset 제안

### 3.3. Heterogeneuous Tactile Representation learning

대부분 tactile representation learning method는 optical tactile sensor에 focusing.

또는 tactile data를 non-tactile data such as vision, lang, audio랑 align.

그래서 hetero tactile sensor learning은 많이 없음.

몇 개 있긴 하지만 general representation이라기 보다는 task-specific setting, ome-way mappin, non-vision tactile sensor 간의 shared representation임.

그래서 우리는 self-sup representation across optical and array-based tactile sensor via paried data.

## 4. Method & Implementation

core objective

1. enable each sensor to extract robust feature from its raw signal

2. leverage pareid cross-sensor data to align disparate modalities within shared latent space

### 4.1. HTT Architecture

MAE comprising sensor-specific encoders and decoders, shared transformer trunk, corss-modal predictors.

fixed 0.2s temporal interaction window

sensor-specific tokenization

optical-based sensor는 ViT

array-based sensor는 self-attention transformer. high-freq multi-dim time series가 non-overlapping temporal patch로 tokenized.

이때 모델에 넣기 전에 raw tactil signal에 대해서 non-contact reference frame을 빼서 처리.

Shared Trunk: unified transformer that process tokens in shared latent

Decoder: Sensor-Specific Decoder that masked recon

Predictionrs: cross-attn that predict masked tharge embeddings from source embeddings and visible target embeddings.

### 4.2. HTT Pretraining

#### 4.2.1. MAE

sensor-specific encoder와 shared trunk가 visible token을 처리하고 sensor-specific decoder가 masekd token을 recon.

이를 통해 encoder-trunk system이 retain high-fidelity localized details를 retain함.

#### 4.2.2. Cross-Modal Alignment

JEPA-style

이때 source embedding과 target embedding이 서로 다른 tactile sensor에 해당됨.

#### 4.2.3. Joint Pretraining

joint로 진행하고 jepa loss의 weight는 time-dependent하게 가는데 처음에는 0으로 하고, 이후에 0.1까지 상승.

jepa loss는 predictor와 shared trunk만을 update함. encoder는 mae loss에 의해서만.

## 5. Experiment

- **Q1:** HTT pretraining은 useful representation 만드니?

- **Q2:** HTT representation은 distinct task에 transfer 돼?

- **Q3:** cross-sensor alignment가 도움이 되는게 맞아?

- **Q4:** HTT가 contact rich policy에 도움 돼?

- **Q5:** HTT가 pretraining에 못 본 new sensor에 적용 돼?

### 5.1. Tasks

Object Classification

Force estimation and slipt detaction

real-world robot experiments and ManiFeel Simulation tasks

robot experiments with unseen sensor

### 5.2. Baselines

Scratch: sensor- and task- specific transformers with MLP head

T3: pretrained oprical tactile w/ real world data

SITR:pretrained optical tactile w/ synthethic data

AnyTouch: stastic-dynamic represerntation from optical tactile image and video

SPH: train HTT’s encoders and shared trunk on downstream supervision only w/o pretraining

MAE: only MAE w/o JEPA

HTT: ours.

For each tasks, we finetuine pretrained encoder and shared trunk with task-specific head or policy.

## 6. Result

### 6.1. Object Classification Across Heterogeneous Sensors

obkect classification task에서 MAE와 HTT가 전반적으로 제일 좋은 성능을 보였고 Xela sensor 이외에는 HTT가 제일 좋았음.

저자들은 이에 대해서 information umbalance btw sensor 때문이라고 말하는데, optical sensor에서는 array sensor로부터 오는 complementary force cures가 alignement(JEPA) 덕분에 도움이 된다라고 하면서, 대신에 array based signal에서는 coarse해서 그러한 improvement room이 작을 수 있다라고 함. 그리고 그러다보니 representation이 optical sensor의 representation으로 mildly drift 했을 수 있다고 함.

### 6.2. Transfer to Force and Slip Perception

### 6.3. Shared-Space Analysis

orthogonal map을 fitting했고 episode가 matching되는 diagonal entry가 similairt가 크게 나왔음.

정량적 분석.

### 6.4. HTT for Robot Manipulation

camera 없이 proprioception state와 tactile sensing만 이용하여 policy가 robot control

toy screw 20 demom, tofu lift 50 demo.

잘 하더라\~

## 7. Limitations

HPT pairs sensors in time and contact but not in geometric space: explicitly modeling which spatial patches of a optical sensor correspond to which taxels of an array sensor will be a future step for finer-grained cross-modal supervision.

---

**Notion 원문:** https://app.notion.com/p/422be171a762802cb6f4cf4a2bd84ce4
