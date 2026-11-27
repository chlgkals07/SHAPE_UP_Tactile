# TacForcing

**Title:** TacForcing: Streaming Action Generation with Execution‑Time Tactile Feedback

- **Venue:** arXiv
- **Submission:** ICLR 2027 (4, 2, 4)
- **arXiv submitted:** 2026.08.26

[TacForcing: Streaming Action Generation with Execution-Time...](https://arxiv.org/abs/2608.25798)

## 0. Takeaway

reactive를 다룬 최근 연구.

iclr 4, 2, 4로 accept이 예상됨.

2점 준 review의 경우에 novelty, contribution을 지적했음. 그리고 streaming schedule에 대한 분석이 부족하다고 지적함. 새롭게 들어온 tactile condition이 completion에 가까워진 action을 얼마만큼 modify하는 것인지, 그 정도에 대한 질문을 했음. 또한 real time responsive가 어느 정도로 나오는지에 대한 정량적 분석과 short-horizon policy와의 비교를 요구했음.

short-horizon policy와 비교 결과 그래서 report 했고 tacforcing이 더 좋았음. 그리고 추가적으로 real world 더 실험했움.

공통적으로 real world 실험의 statiscal reliability에 대한 질문이 있었음. 16 번 eval은 부족한가봄.

또한 4점 준 reviewer가 block size와 sampling step의 선택에 대한 질문도 함. 그에 대한 답변으로 경험적으로 골랐으며, 정량적인 분석을 하지는 않았다고 함. 그러면서, 각 로봇 플랫폼의 control freq를 언급하며 자신들의 값이 그 control freq에서 적당하며 극단적인 값으로 가버리면 로봇 컨트롤이 느려짐. 따라서 optimality에 따른 선택이라기 보다 practical한 선택이라고 언급.

## 1. Problem

tactile representation은 single action chunk 내에서 substantially 변화하지만, visaul representation은 거의 변화하지 않음.

따라서 고정된 tactile observation으로 만들어진 action chunk 내에서는 tactile input과 contact state 간의 temporal mismatch가 발생한다.

기존 방법들은 additional policy-specific components를 붙여서 architectural and training complexity가 높아지는 것을 문제로 보고, action generation에 직접적으로 tactile feedback을 통합하는 방향을 고안.

## 2. Contribution

1. introduce Tacforcing, streaming action generation framework that incorporate execution-time tactile feedback

2. adapt streaming action expert and EATA

3. show good performance and improvement

## 3. Novelty

### 3.1. Diffusion Models for Sequence Generation

position-dependent denoising

diffusion forcing

FASTER

Tacforcing도 이러한 streaming perspective를 따름.

### 3.2. Tactile‑Aware Policies for Contact‑Rich Manipulation

reactive method: T-Rex, RDP, At-VLA

predictive and predictive-reactive method: TacForeSight, ReTouch, TouchWorld

Tacforcing requires neither a separate reactive controller nor explicit tactile prediction to adapt actions

## 4. Method & Implementation

### 4.1. Streaming Action Generation via Block‑Wise Flow Scheduling

Streaming Action Expert that generates the action chunk progressively

앞부분 action이 먼저 완성되면 먼저 실행되고, 다른 이후 actions은 further refiment 진행. 이때 별도 controller 없이 same chunk 내에서 남은 action에 new tactile feedback으로 업데이트

N: total num of sampling steps

대신 flow time은 action chunk 내에서 공유되는 것이 아닌, position-dependent flow time 사용.

즉 chunk 내 step마다 별도의 flow step을 둠.

그래서 B개 action step을 하나의 block으로 하여 K개 block을 두고 이 K개 block이 하나의 chunk를 이룸.

그리고 각 K개 block은 순차적으로 S번의 sampling step을 거치고 K개의 S번 sampling step으로 N이 됨.

각 block 내의 action은 block flow time을 공유하며 sampling step의 경우 k th block은 k\*S 번 하게 된다.

(즉, 앞쪽 block이 총 sampling step(integration step)이 짧음)

action position i의 flow time은 현재까지 total sampling step/(block index \* block sampling step S)

완성된 block은 fixed되고, 순차적으로 준비되면 바로 실행된다.

### 4.2. Conditioning on Execution‑Time Tactile Feedback

chunk 내에서 instruction, observation input은 계속 사용.

tactile condition은 각각의 block을 execution 한 후에 refreshed.

(k-1)S \< n ≤ kS의 sampling step 동안에는 k-1 번째 tactile condition이 사용된다. 그리고 k번째 block이 실행되면 다시 새롭게 얻은 k 번째 tactile condition이 사용된다.

이 논문에서는 k-1 block이 실행된 후에 k-1 번째 tactile representation이 최신 contact state가 되고 이것은 k block과 temporal aligned라고 한다. 그런데 이것이 아직 끝나지 않은 다른 block도 condition해서는 안 된다고 주장함. 왜냐면 그들과는 또 다른 contact state를 가질 수도 있기 때문.

따라서 unrestricted attention은 every unfinished action token이 k-1 th representation에 attend하게 되는데, 이러면 unfinished block 입장에서는 이건 outdated 라고 함.

그래서 이러한 attention을 막기; 위해서 EATA를 도입하고, current tactile representation은 직접적으로 다음에 실행할 action block에만 condition을 줌

### 4.3. Training

임이의 progress 상태(생성 진행률) 선택

그것으로 k 번째 flow time을 고리고 각 block에 해당하는 noise와 action을 섞음.

그리고 그 상태에서 사용 가능한 tactile representation을 고르고 마스크도 앞서 정의한 대로 씌워줌 .

그리고 loss는 현재 p에 따라서 완성되지 않은, unfinised action에 대해서만 적용함.

### 4.4. Implementation Details

sim에서는 backbone으로 pi05, real world에서는 gr00t-n1.7 사용.

tactile encoder는 FTP-1의 encoder 사용했음.

block size는 5, chunk horizon은 50.

real에서는 chunk horizon은 40이며 block size는 동일하게 5.

sim은 task마다 100번 eval, real은 task마다 16.

그리고 sim에서는 50 demo로 15000 step 학습/

real world에서는 100 demo. 이때 어려운 task (close cap, close lid)는 150, 300개 사용.

학습은 15 epoch에 배치 256.

## 5. Experiment

### 5.1. Tasks

Simulation: UniVTac 6 tasks

Real world: Close Cap, Insert Battery, Close Lid, Transfer Liquid, Wipe Board, Stand Bottle

### 5.2. Baselines

pi05, ACT, FTP-1, RDP, GR00T-N1.7, T-Rex

pi05를 Sharpa real robot에 적용한 baseline report함.

## 6. Result

### 6.1. Main Table

sim에서는 tacforcing이 당연히 가장 잘 했고 그 다음은 FTP-1임

real에서도 당연히 tacforcing이 제일 좋았으며,

gr00t가 pi를 이김. → gr00t로 우리도 backbone 바꾸어야 하나?

### 6.2. Ablation

fixed tactile w/o EATA, tactile update w/o EATA, Tacforcing

EATA로 직전 tactile만 보게 하는 것이 좋다라는 결과가 나옴. 즉 이전 tactile을 누적해서 계속 보는 거보다 직전 것 딱 하나만 보는 것이 좋다.

---

**Notion 원문:** https://app.notion.com/p/424be171a76280c38899c6943d606d5b
