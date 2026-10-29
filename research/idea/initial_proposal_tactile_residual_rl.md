# Initial Proposal: Base VLA + Tactile-Reactive Residual RL for Dexterous Manipulation

**작성일:** 2026-10-29  
**상태:** 팀 논의를 위한 초기 연구 제안 / 모델·태스크·알고리즘·수치는 후보이며 확정된 결과가 아님

## 0. 제안 요약

시각·언어·proprioception을 이용하는 기존 VLA를 base policy로 재사용하고, **base의 action 계획과 최신 분산 촉각을 함께 관측하는 경량 residual policy**를 붙여 다지 손의 접촉 행동을 개선한다. Base는 필요한 embodiment/task 적응 후 고정하고, residual은 **실제 로봇의 상호작용을 이용한 RL**로 학습하는 방향을 우선 검토한다.

Residual은 single-step 또는 짧은 action chunk를 출력한다. **길이 1이나 5는 고정 설계가 아니라 ablation 대상**이며, single-step이 항상 좋다거나 short chunk가 반드시 필요하다고 가정하지 않는다. 예측 길이와 실제 실행 후 피드백을 다시 받는 간격을 구분한다.

핵심 연구 질문은 다음과 같다.

> 기존 VLA의 행동 prior를 활용하면서, 손가락·마디의 접촉 상태를 이용한 residual RL이 제한된 실물 경험으로 dexterous contact-rich manipulation을 개선할 수 있는가? 이때 미래 행동 계획, 촉각의 공간·시간 정보, residual 실행 horizon은 각각 어떤 역할을 하는가?

**포지셔닝:** Frozen VLA, residual RL, slow–fast 제어, 짧은 RL chunk, 실물 온라인 RL은 각각 선행연구가 존재한다. 따라서 현재 구성을 최초의 구조로 주장하지 않는다. 분산 촉각과 행동 계획을 이용한 다지 손의 접촉 보정이 언제 필요한지, 어떤 설계가 실물 데이터 효율성과 반응성을 개선하는지를 검증하는 것이 초기 목표다.

## 1. 배경과 문제 설정

일반적인 vision-language 기반 VLA에는 tactile 입력 경로가 기본적으로 포함되지 않은 경우가 많다. 접촉 후에는 영상만으로 파악하기 어려운 미끄러짐, 국소 하중 변화, 접촉 상실이 발생하며, 긴 구간을 새 관측 없이 실행하면 이러한 변화에 늦게 반응할 수 있다.

FTP-1과 T-Rex는 촉각 데이터와 학습 구조를 통해 이 문제에 접근한다. 특히 T-Rex는 데이터 구축뿐 아니라 비동기 tactile refinement도 다룬다. 따라서 기존 tactile VLA를 모두 느린 단일 경로 모델로 취급하지 않는다. [R5, R6]

본 연구의 동기는 **VLM이 촉각을 원천적으로 학습할 수 없다는 주장**이 아니다. 시각·언어 사전학습만으로 실제 센서 신호와 접촉 행동의 대응이 자동으로 확보되는 것은 아니므로, 기존 VLA의 지식을 유지하면서 접촉 적응을 별도로 학습하는 접근의 효율성을 확인하려는 것이다.

다지 손에서는 같은 전체 힘이라도 손가락별 접촉 분포가 다를 수 있다. 또한 동일한 접촉 변화라도 물체를 유지·회전·놓으려는 의도에 따라 적절한 행동이 달라질 수 있다. **미래 행동 계획과 분산 촉각을 함께 제공할 근거**는 여기에서 찾는다. 이는 검증할 가설이다.

## 2. 현재 연구 범위와 미정 사항

| 항목 | 현재 방향 | 남은 결정 |
| --- | --- | --- |
| 로봇 | OMY 기반 다지 손 조작 | 최초 실험에 사용할 손·팔 조합과 action interface |
| 촉각 | 손가락 및 마디에 부착한 분산 센서 | Paxini Gen3 등 센서 모델, 배치, 출력 채널, 실제 유효 주기 |
| 시각 | 가용 RealSense D435i 2대 활용 가능 | 카메라 배치 및 base 입력 구성 |
| Base VLA | π 계열, GR00T, SmolVLA 후보 | 다지 손 action을 지원·적응시킬 비용을 확인해 1개부터 선정 |
| Base 학습 | 필요한 BC/SFT 후 residual RL 중 freeze | 적응 데이터 양과 업데이트할 파라미터 범위 |
| Residual 입력 | Base action 정보 + tactile | Proprioception, history, 실행 phase의 포함 범위 |
| Residual 출력 | Single-step 또는 짧은 보정 chunk | 예측 길이, 실행 길이, 손/팔 보정 범위 |
| Residual 구조 | MLP 또는 lightweight Transformer | Temporal encoder 또는 GRU 대조군 포함 여부 |
| RL | 실제 로봇에서 actor–critic 학습 | PPO와 off-policy 계열 중 구체 알고리즘·학습 예산 |
| 초기 범위 | Contact-critical phase와 전체 task 평가 | 첫 태스크, 성공 판정, reset 절차 |
| 후속 확장 | PLD motivated 개선 가능성 | 메인 방법 검증 후 별도 검토 |

**플랫폼 전제:** 사전학습 VLA를 연결하는 것만으로 우리 손의 관절 공간이 지원되는 것은 아니다. Base의 embodiment 적응과 action mapping을 먼저 검증한다. 촉각 sensor sampling rate, 정책 갱신률, actuator 명령 주기와 실제 추종 대역폭은 각각 측정한다. 위 표의 센서 성능·제어 주기는 아직 확정하지 않는다.

## 3. 모델 구성 후보

### 3.1 Base policy

Base는 이미지, 언어 지시, 로봇 상태를 받아 nominal action chunk를 생성한다.

$$
A_k=\pi_{\mathrm{base}}(I_{t_k},\ell,q_{t_k})\in\mathbb{R}^{H\times d}.
$$

- 초기 후보: π₀.₅ 등 π 계열, GR00T, SmolVLA.
- Base가 task의 접근·파지 등 기본 동작을 수행하도록 필요한 BC/SFT를 진행한다.
- 주 실험에서는 residual RL 동안 base를 고정해 학습 대상을 분리한다.
- 여러 backbone 비교는 최초 결과 이후 확장한다. 지원 가능한 구조와 동일 residual 가중치의 전이는 구분한다.

### 3.2 Residual policy

Residual의 초기 입력 후보는 다음과 같다.

| 입력 | 후보 표현 | 확인할 필요성 |
| --- | --- | --- |
| Base action 계획 | 현재 action, 짧은 미래 구간, 남은 chunk, full chunk | 행동 의도·미래 계획 정보 |
| Tactile | 현재 관측 또는 최근 history | 접촉 분포와 시간적 변화 |
| Proprioception | 손 관절 위치·속도, 필요 시 팔 상태 | 실제 자세 및 nominal trajectory와의 차이 |
| 실행 정보 | Chunk index, 생성 후 경과 시간, 유효 구간 mask | 오래된 계획·이미 실행한 action의 구분 |
| 이전 실행 행동 | 실제 보낸 명령 또는 이전 residual | 상태 변화의 해석과 시간적 연속성 |

$$
\Delta A_t=\pi_{\theta}(\mathcal{P}(A_k,i_t),T_{t-L+1:t},q_t,\phi_t)
\in\mathbb{R}^{C\times d_r}.
$$

여기서 $\mathcal{P}$는 사용할 base action 구간, $L$은 tactile history 길이, $C$는 residual 예측 길이, $\phi_t$는 실행 phase와 timestamp 정보다. 모든 입력이 처음부터 필수라는 뜻은 아니며, 제거·축소 실험으로 확인한다.

실행 시 대응하는 nominal action과 residual을 합성한다.

$$
a^{\mathrm{exec}}_{t+j}=\operatorname{Compose}(A_k[i_t+j],\Delta A_t[j]).
$$

초기 구현에서는 손 관절 명령의 bounded residual이 후보이며, 팔 보정은 별도 범위로 결정한다. 위치·속도·증분 action의 단위와 좌표계를 일치시키고, 회전은 사용 표현에 맞게 합성한다. 단순 덧셈이 모든 action 표현에 적용된다고 가정하지 않는다.

### 3.3 Residual architecture 후보

| 구조 | 구현 후보 | 비교 목적 |
| --- | --- | --- |
| MLP | 고정 길이 tactile history와 action 정보를 concatenate | 가장 단순한 기준선 |
| Lightweight Transformer | 센서 위치·시점·action step을 token으로 표현 | 접촉 분포와 행동 계획의 상호작용 |
| GRU/temporal encoder | Tactile history를 작은 temporal state로 압축 | Transformer의 이득이 단순한 temporal memory 때문인지 확인 |

센서 위치·손가락·마디 identity를 유지하는 표현을 우선 후보로 둔다. Model size뿐 아니라 end-to-end latency, online 학습 비용을 함께 비교한다. 접촉량이 작을 때 residual을 억제하는 gate와 residual 크기 제한은 선택적 설계이며, gate가 항상 유리하다고 가정하지 않는다.

### 3.4 Prediction horizon과 feedback interval의 분리

| 기호 | 정의 |
| --- | --- |
| $H$ | Base가 한 번에 예측하는 action 수 |
| $B$ | Base 계획을 갱신하기까지 실행하는 action 수; $B\le H$ |
| $C$ | Residual이 한 번에 예측하는 보정 action 수 |
| $E$ | Residual을 다시 추론하기 전에 실행하는 action 수; $E\le C$ |
| $f_a$ | Action 실행률 |

이상적인 일정에서는 residual feedback interval이 $E/f_a$다. 실제 반응 지연에는 센서·통신·계산·구동 지연이 추가된다. $C$가 짧아진다고 action의 시간 간격 자체가 짧아지는 것은 아니다.

예를 들어 $H=B=50$, $C=E=5$이면 base forward 1회에 residual forward 10회를 수행한다. 이는 설명용 예시다. $C=E=1$, $C=5,E=1$ 등도 동일하게 실험 후보이며, 아직 최적값을 가정하지 않는다.

Base가 새 chunk를 생성하면 남은 residual과의 정렬을 갱신한다. 초기 구현에서는 base 경계에서 residual을 다시 계산하거나 유효한 구간까지만 실행하도록 명시한다. 로그에는 base chunk ID, 생성 시각, 실행 index, 실제 실행한 residual prefix를 기록한다.

## 4. 학습 계획 후보

### 4.1 초기 pipeline

1. **센서·행동 정렬:** Tactile, proprioception, camera, command timestamp를 동기화한다.
2. **Base 적응:** 필요한 demonstration으로 BC/SFT를 진행하고 base-only 성능을 측정한다.
3. **초기 데이터 확보:** Base rollout과 필요한 demonstration/개입 데이터를 수집한다. Base SFT와 replay warmup은 별도 과정으로 기록한다.
4. **Residual online RL:** Base를 고정하고 실물 상호작용으로 actor–critic을 학습한다.
5. **고정 checkpoint 평가:** 학습을 중지한 정책으로 표준 조건·외란·미학습 조건을 평가한다.

첫 실험은 상태를 재현하기 쉬운 contact-critical phase에서 시작한다. 이후 base가 앞 단계를 수행한 전체 task에서 평가해, 수동 reset 상태에서만 성공하는 정책인지 확인한다.

### 4.2 RL 알고리즘과 초기화

- Actor–critic은 알고리즘 계열이며 PPO는 그중 한 후보다. 서로 다른 범주의 선택지로 표현하지 않는다.
- PPO를 후보로 유지하되, 실물 데이터 재사용을 위해 replay 기반 off-policy 방법도 비교·검토한다.
- Residual을 0에 가깝게 시작하는 초기화, demonstration 기반 residual BC, base action 근처의 탐색을 후보로 둔다.
- Base warmup용 BC/SFT와 residual 자체의 BC 초기화는 서로 다른 ablation이다.
- Residual bound와 base 근접 정규화는 안정적인 탐색을 도울 수 있지만 큰 회복 행동을 막을 수도 있어 확인한다.

### 4.3 Reward 및 데이터 후보

우선 task success를 공통 기준으로 정의하고, 필요할 경우 접촉 손실·과도한 압력·물체 손상·residual 크기 등의 항을 검토한다. 모든 태스크에서 접촉력을 작게 만드는 것이 정답은 아니므로, tactile 값을 최소화하는 보상을 그대로 사용하지 않는다. Reward에 tactile을 쓰는 효과와 actor 입력에 tactile을 쓰는 효과는 분리한다.

사람의 개입을 학습에 사용하는 경우 개입 시점·명령·시간을 기록하고, 방법 간 예산을 맞춘다. 평가 시 개입을 성공으로 계산하지 않으며 별도 지표로 보고한다.

### 4.4 Chunk RL에서 필요한 정합성

서로 다른 $E$를 비교할 때 제어 step 기준 reward와 시간 기준 discount를 일치시킨다. 실제 $e$ steps를 실행한 전이에 대한 multi-step TD target의 기본 형태는 다음과 같다.

$$
y_t=\sum_{j=0}^{e-1}\gamma^j r_{t+j}
+\gamma^e(1-d_t)V_{\bar\psi}(s_{t+e}).
$$

이는 선택한 알고리즘의 세부 target을 대체하는 공식이 아니라 전이 시간을 맞추기 위한 기준이다. Terminal과 time-limit truncation을 구분한다. $E<C$일 때 실행하지 않은 action까지 실행한 것으로 학습하지 않는다. Critic의 action 정의를 실제 실행 prefix와 맞추고, base reference와 phase도 상태에 포함할지 검토한다. Chunk 길이에 따라 reward scale, entropy/regularization scale, update-to-data ratio가 달라지는 혼입을 통제한다.

## 5. Related work와 연구 포지셔닝

아래는 공개 방법 설명·논문·코드에서 확인한 내용이다. 모든 연구가 동일 플랫폼·센서에서 검증된 것은 아니며, 구조적 차이와 성능 우열을 구분한다.

| 연구 | 관련 내용 | 본 연구에 주는 의미 |
| --- | --- | --- |
| **FIRe** [R1] | Frozen VLA + force-aware residual RL + 매 실행 단계 보정. Simulation 학습과 실물 전이 | 가장 직접적인 구조 비교 대상. Real RL·다지 손·분산 촉각·계획 conditioning의 추가 효과를 검증해야 함 |
| **RL Token / RLT** [R2] | VLA representation을 압축한 RL token, reference-action conditioning, 짧은 RL chunk, 실물 online RL | 실험 설계뿐 아니라 직접 비교 대상. Short chunk와 action conditioning만으로는 새로운 기여가 아님 |
| **DSRL** [R3] | Frozen diffusion/flow policy의 latent noise를 RL로 선택 | Action-space residual과 다른 적응 방식. 구현 및 계산 예산이 허용하면 비교 |
| **Reactive Diffusion Policy** [R4] | 느린 latent planning과 빠른 tactile feedback | Slow–fast tactile control 자체가 선행됨 |
| **T-Rex** [R5] | Temporal tactile 표현과 비동기 tactile refinement | 다지 손의 tactile reactivity 비교 대상. 단순한 dataset 연구로 취급하지 않음 |
| **FTP-1** [R6] | 다양한 센서·embodiment의 tactile policy pretraining | 대규모 tactile pretraining을 활용하는 접근과의 비교 축 |
| **ViTaR** [R7] | Frozen VLA 위의 tactile-conditioned residual 선택·조절 | 촉각을 execution modulation으로 쓰는 발상도 선행됨 |
| **VT-Bridge** [R8] | 기존 VLA 위의 경량 residual adapter를 실행 주기에 적용 | 모듈형·경량 tactile adaptation과 중복. 이번 확인은 공개 초록 범위이며 상세 구현은 추가 확인 |
| **PLD** [R9] | Residual specialist 학습, rollout 수집, base로 SFT | 최초 영감과 후속 확장에 해당. 메인 방법의 필수 단계는 아님 |

### 5.1 FIRe와의 구체적 관계

확인한 FIRe 공개 구현은 residual과 현재 base action을 출력 단계에서 합치며, residual 입력에 full future chunk를 직접 제공하지 않는다. 손목 force와 로봇 상태를 사용하며 공개 배포 기본 제어율은 15 Hz다. 같은 action 실행률에서 single-step FIRe보다 $E>1$인 본 방법이 더 자주 feedback을 받는다고 주장할 수는 없다. FIRe에는 recurrent network 설정도 있어 단순 memoryless force controller로 가정하지 않는다. [R1]

본 연구는 **분산 촉각을 이용한 손가락 협응, 미래 계획 정보, 실물 학습 효율성**에서 추가 기여를 찾아야 한다. 다지 손으로 플랫폼을 바꾸거나 PPO/SAC를 바꾸는 것만으로 충분한 노벨티가 확보된다고 가정하지 않는다.

### 5.2 RL Token과 DSRL에서 참고할 실험

RLT는 reference chunk에 조건화하고 base 근처로 정규화한 **최종 action chunk**를 출력한다. 고정된 additive residual parameterization과 동일하지 않다. Critical-phase와 full-task 평가, throughput, 동일 데이터 예산 비교를 참고한다. 또한 single-step ablation에서는 encoder도 바뀌므로 결과를 chunk 길이만의 효과로 해석하지 않는다. 본 연구는 tactile encoder와 입력을 유지해 길이를 비교한다. [R2]

DSRL은 작은 정책이 latent noise를 선택해 base의 action 생성을 유도한다. 본 연구의 action-space 보정과 탐색 범위·계산 지연이 다를 수 있다. 같은 성공률에서 필요한 실물 데이터와 속도를 비교하고, 모델 forward 횟수도 기록한다. 사용자가 언급한 “DS-RL”은 이 DSRL을 가리키는 것으로 잠정 정리한다. [R3]

### 5.3 검증할 기여 후보와 주장 범위

1. **촉각의 정보 기여:** 손가락·마디의 공간적 접촉 분포가 합력·손끝 관측으로 해결하지 못하는 실패를 줄이는가?
2. **계획과 접촉의 결합:** 현재 행동만으로 부족한 상황에서 미래 계획 정보가 적절한 접촉 보정을 선택하게 하는가?
3. **시간 규모의 선택:** 예측 horizon과 feedback interval이 학습 효율성·반응 지연·성공률 사이에 어떤 관계를 만드는가?
4. **실물 학습 효율성:** 기존 VLA를 유지하면서 제한된 실제 경험으로 의미 있는 개선을 얻는가?

모두 가설이다. Base freeze는 파라미터를 보존할 뿐 결합 정책의 기존 능력 보존을 보장하지 않는다. 비접촉 구간과 base가 이미 성공하는 조건의 성능 저하도 측정한다.

## 6. 실험 질문 Q1–Q8

원래 실험 질문을 유지하되, Q2는 실행 구조의 필요성, Q8은 그 구조 안에서의 길이 선택으로 분리한다. Q3는 action 정보를 제공할 필요성, Q7은 어느 범위의 action 정보가 필요한지 다룬다.

| 질문 | 비교·측정 후보 | 주요 통제 및 해석 |
| --- | --- | --- |
| **Q1. Dexterous contact-rich task를 잘 해결하는가?** | Base SFT, base RL, no-tactile residual, tactile residual 및 가까운 related methods | 성공률·시간·학습 곡선을 동일 초기 checkpoint와 실물 예산에서 비교 |
| **Q2. Reactive 실행 구조가 필요한가?** | Base와 같은 느린 갱신 vs 짧은 주기의 tactile 갱신. 예측 길이를 고정하고 실행 간격 변경 | 최신 tactile을 자주 반영하는 효과를 확인. Short chunk가 필수라고 전제하지 않음 |
| **Q3. Residual에 base action 입력이 필요한가?** | No action conditioning vs action conditioning | 둘 다 같은 base action에 residual을 더함. 입력 정보 제거와 base 자체 제거를 구분 |
| **Q4. 실제 reactivity가 개선되는가?** | 예측 불가능한 외란, tactile delay/dropout, 접촉 변화 | Event-to-command 및 event-to-motion latency, 회복률, slip/접촉 손실 측정 |
| **Q5. 어떤 residual architecture가 적절한가?** | MLP vs lightweight Transformer; 필요 시 GRU | 같은 history·입력·데이터 예산, 모델 크기와 latency를 함께 보고 |
| **Q6. Base warmup SFT가 얼마나 필요한가?** | 호환 가능한 무추가-SFT base vs 소량·증가된 SFT | Embodiment 적응과 task 추가 SFT를 구분. 각각 residual 학습 전 base 성능도 측정 |
| **Q7. 현재 action과 future/full chunk 중 무엇이 필요한가?** | 현재 1개, 가까운 미래 $K$개, 남은 chunk, 원래 full chunk + phase | 표현 크기·padding/mask·encoder capacity의 혼입을 통제 |
| **Q8. Residual 길이는 어떻게 선택해야 하는가?** | $C,E\in\{1,2,5,10\}$ 등 가능한 후보 | $C=E$ sweep과 $C$ 또는 $E$ 고정 비교를 구분. 값은 예시이며 실측 주기에 맞춰 조정 |

### 6.1 Q2·Q8을 구분하는 작은 실험 행렬

| 비교 | 예시 조건 | 분리해서 볼 효과 |
| --- | --- | --- |
| Single-step vs short-chunk 전체 효과 | $(C,E)=(1,1),(5,5)$ | 계획 길이·피드백 간격·학습 horizon이 함께 바뀐 시스템 효과 |
| 예측 길이 효과 | $(1,1),(5,1)$ | 같은 feedback interval에서 미래 sequence 예측의 효과 |
| 실행 간격 효과 | $(5,1),(5,5)$ | 같은 prediction horizon에서 feedback 빈도의 효과 |
| 긴 open-loop 기준선 | $C$를 같게 두고 $E$를 충분히 크게 설정 | 접촉 중 최신 관측을 받지 못하는 비용 |

위 비교는 실행 인터페이스만 바꾸면 끝나지 않는다. 실제 실행 prefix에 맞는 critic·replay 정의와 부록 수준의 학습 설정을 함께 맞춘다. Base 갱신 간격 $B$는 우선 고정하고, base도 더 자주 갱신하는 비교는 별도로 수행한다.

### 6.2 추가 tactile ablation 후보

- No tactile / 현재 tactile / tactile history.
- 전체 분포 / 가능한 경우 합력·통계량 요약 / 손끝만 / 마디 포함.
- Actor의 tactile 입력 유무 × reward의 tactile 사용 유무.
- Proprioception 포함/제거.
- Residual magnitude bound 또는 정규화 강도.

센서 출력만으로 물리적인 합력을 계산할 수 없다면 임의의 합을 합력이라고 부르지 않는다. “요약 통계”와 실제 force sensor 대조군을 구분한다. Tactile 제거·시간 교란만으로 인과 효과를 단정하지 않으며, 동일 설정으로 재학습한 대조군과 배포 시 정보 손상 실험을 구분한다.

## 7. Baseline 구성과 비교 예산

초기에는 모든 선행연구를 재현하지 않고, 가설을 분리하는 최소 비교부터 시작한다.

| 우선순위 | Baseline | 목적 및 범위 |
| --- | --- | --- |
| **P0** | Base-only SFT | Residual 전의 출발점 |
| **P0** | 동일 RL residual, tactile 제거 | 개선이 촉각 때문인지 추가 RL 때문인지 구분 |
| **P0** | Tactile residual, action conditioning 제거 | 계획 입력의 기여 |
| **P0** | 동일 tactile residual의 느린 feedback | Reactive 실행의 기여 |
| **P1** | Residual BC 또는 추가 demonstration SFT | RL 상호작용과 추가 지도 데이터의 효과 비교 |
| **P1** | FIRe-inspired step residual | 같은 손·관측·실물 예산에서 가까운 구조와 비교; 원 FIRe 재현으로 표기하지 않음 |
| **P1** | RLT 또는 RLT-inspired action refinement | Reference-conditioned 실물 RL과 비교; 공식 모델·센서 차이를 명시 |
| **P1** | Base policy RL | Full update/action-head update/adapter update를 구분해 가능한 범위를 선정 |
| **P2** | DSRL | Latent-noise steering과 action-space residual 비교 |
| **P2** | T-Rex/FTP-1/RDP 계열 | 촉각 통합 및 pretraining 접근. 손·센서 호환성과 구현 비용 확인 후 선정 |

**공정성 원칙:** 같은 task split, action space, base 초기 checkpoint, demonstration, 온라인 환경 시간, 성공 판정을 가능한 한 맞춘다. 관측 modality, pretrained tactile data, 사람 개입이 다르면 별도 축으로 표기한다. 미리 정한 실물 예산에서 비교하고, 계산 비용이 다른 방법은 학습 시간·메모리·inference latency도 병기한다. Base RL을 구현하지 못했다면 비교하지 않은 것으로 명시한다.

## 8. Task·지표·평가 프로토콜 후보

### 8.1 Task families

| 후보 task family | 검증할 능력 | 초기 실험 조건 |
| --- | --- | --- |
| 파지 유지와 slip recovery | 순간 외란에 대한 접촉 회복 | 반복 가능한 외란 방향·크기·시점 |
| In-hand reposition/rotation | 여러 손가락의 접촉 전환과 협응 | 작은 범위의 자세 변경부터 시작 |
| 순응성 물체의 유지·조작 | 과도한 국소 압력과 파지 안정성의 균형 | 변형·손상 판정을 객관화 |
| 다지 파지 상태의 삽입·회전 조립 | 손과 팔의 역할 분담 | 손 보정만/팔 포함 범위를 명확히 설정 |

최초 task는 reset 재현성과 base의 기본 수행 능력을 기준으로 선정한다. 물체를 처음부터 잘못 선택하거나 잡지 못하는 실패와 접촉 단계의 실패를 구분한다. 공간적 촉각이나 미래 계획을 사용해야 해결되는 조건이 없다면 해당 기여를 주장하지 않는다.

### 8.2 Metrics

| 범주 | 지표 |
| --- | --- |
| 수행 성능 | End-to-end success, critical-phase success, 접촉 도달 후 조건부 성공률 |
| 시간 | 성공 시 완료 시간과 실패를 포함한 timeout 처리 결과; 처리량 |
| 반응성 | 외란 시점→명령 변화, 외란 시점→실제 교정 움직임, 접촉 회복 시간 |
| 접촉 품질 | Slip/접촉 상실, 국소 압력·힘 peak 및 기준 초과 시간; 센서에서 측정 가능한 항목만 사용 |
| 데이터 효율 | 실제 상호작용 시간·episode 수 대비 성능, 사전 정의한 목표 성능 도달 비용 |
| 운용 비용 | Reset·사람 개입·demonstration을 포함한 전체 실험 시간 |
| 계산 비용 | Base/residual forward 횟수, inference 지연의 중앙값·상위 분위수, 모델 크기 |
| 보존·일반화 | 정상 조건 성능 저하, 미학습 물체·마찰·접촉 위치·외란 조건 |

처리량을 보고할 때 reset 포함/제외 정의를 명시한다. 성공한 episode만의 속도가 빨라지고 실패율이 증가하는 경우를 별도로 해석한다. 목표 성공률에 도달하지 못한 학습 run은 미도달로 보고한다.

### 8.3 Evaluation design

- **Critical-phase 평가:** 접촉 직전의 표준 상태와 작은 초기 randomization에서 비교한다.
- **Full-task 평가:** Base가 앞 단계를 수행한 실제 상태 분포에서 residual의 효과를 확인한다.
- **Reactivity 평가:** 외란 시점이 chunk 경계와 우연히 일치하지 않도록 무작위화하고, 센서 이벤트와 실제 움직임을 공통 clock으로 기록한다.
- **일반화 평가:** 물체·표면 조건의 train/validation/test 분리를 미리 정한다.
- **반복성:** Pilot으로 효과 크기와 분산을 확인해 본 평가 trial 수를 정한다. 이항 성공률 신뢰구간을 보고하고, 가능한 경우 독립 학습 run도 반복한다.
- **Checkpoint 선택:** Test 성공률을 보고 최적 checkpoint를 선택하지 않는다. 고정 예산 또는 validation 규칙을 사용한다.
- **실험 순서:** 조건·방법의 순서를 교차해 센서 drift, 물체 마모, 장비 온도와 방법의 효과가 섞이지 않도록 한다.

## 9. 단계별 실행 계획과 판단 기준

| 단계 | 수행할 작업 | 다음 단계로 넘어갈 근거 |
| --- | --- | --- |
| **0. 플랫폼 확인** | 센서 mapping·timestamp·명령률·추종률 확인, base action interface 연결 | Tactile event와 행동을 시간적으로 연결해 분석 가능 |
| **1. 최소 실험** | 1개 base·1개 손·1개 재현 가능한 task, base-only와 작은 residual 구현 | Base가 접촉 구간에 도달하고 학습·평가 loop가 동작 |
| **2. 핵심 가설** | P0 baseline, action conditioning, tactile, feedback 비교 | 단순한 추가 RL 외의 이득이 있는지 판단 |
| **3. 구조 선택** | Q5–Q8의 소규모 sweep | 성공률·지연·실물 데이터 효율성을 보고 후보 축소 |
| **4. 외적 검증** | 복수 task, full-task, 미학습 물체·외란, 가까운 related methods | 한 task의 특수한 보정을 넘는지 확인 |
| **5. 확장** | 다른 backbone, shared residual 또는 PLD | 메인 결과가 충분한 경우에만 진행 |

**방향을 수정할 신호:** Tactile을 제거해도 성능이 같다면 task나 관측 활용 방식을 재검토한다. Future chunk가 현재 action보다 낫지 않다면 미래 계획의 필요성을 주장하지 않는다. Single-step이 가장 좋다면 그 결과를 채택하고 short chunk를 억지로 유지하지 않는다. 기존에 성공하던 조건을 망친다면 residual 크기·개입 조건·학습 분포를 분석한다.

## 10. PLD motivated 확장: 메인 연구와 분리

후속으로 residual이 만든 성공·회복 rollout을 수집해 base에 SFT하는 방향을 고려할 수 있다. 다만 촉각을 보는 teacher와 촉각 없는 base의 관측 정보가 다르므로, tactile-dependent correction이 모두 증류된다고 가정하지 않는다. [R9]

후보는 (a) 시각·상태로 예측 가능한 개선을 base에 학습시키고 residual을 유지하거나, (b) student에도 tactile 입력을 제공하는 것이다. 두 방향은 다른 연구 범위를 갖는다. Base를 갱신하면 residual이 보던 nominal 행동 분포도 바뀌므로 재평가해야 한다. 현재 initial proposal의 필수 구현·성과 목표에는 포함하지 않는다.

## 11. 첫 팀 회의에서 결정할 항목

- [ ] 첫 다지 손과 촉각 센서 배치, 실제 사용할 채널.
- [ ] Base VLA와 손 action mapping, 필수 embodiment 적응 범위.
- [ ] 재현 가능한 첫 contact-rich task 및 성공·실패 정의.
- [ ] Hand-only residual인지 arm+hand residual인지.
- [ ] Tactile history와 proprioception의 초기 기본 구성.
- [ ] 실제 주기에 맞춘 $H,B,C,E$ 후보와 base/residual scheduling.
- [ ] RL 알고리즘, demonstration·online interaction·개입 예산.
- [ ] Q1–Q4를 검증할 최소 baseline과 담당자.
- [ ] 결과 기록 양식, checkpoint 선택 규칙, held-out 조건.

## 참고문헌 및 공개 근거

아래 링크는 2026-10-29 확인 기준이다. 프로젝트 페이지의 방법 설명, 공개 코드, 논문을 구분하며, 프로젝트의 공개 상태가 최종 학회 채택을 뜻하지는 않는다.

- **[R1] FIRe — Force-Informed Residual Policy for Contact-Rich Manipulation with Vision-Language-Action Models.** [프로젝트](https://rcilab.khu.ac.kr/FIRe/) · [코드](https://github.com/RCILab/FIRe) · [실행 전략](https://github.com/RCILab/FIRe/blob/main/fire_deploy/src/FIRe/fire_core/src/fire_core/strategies.py) · [관측/행동 정의](https://github.com/RCILab/FIRe/blob/main/fire_deploy/src/FIRe/lerobot_robot_fr3/src/lerobot_robot_fr3/tasks/forge/forge.py). 공개 페이지·코드를 비교 근거로 사용; 페이지상 RA-L 제출 상태.
- **[R2] RL Token: Bootstrapping Online RL with Vision-Language-Action Models.** [논문 v2](https://arxiv.org/html/2604.23073v2). 특히 III–V 및 VI-B의 chunk 정의, 학습·평가·ablation 설정 참고.
- **[R3] Steering Your Diffusion Policy with Latent Space Reinforcement Learning (DSRL).** [CoRL 2025 논문](https://proceedings.mlr.press/v305/wagenmaker25a.html) · [프로젝트](https://diffusion-steering.github.io/).
- **[R4] Reactive Diffusion Policy: Slow-Fast Visual-Tactile Policy Learning for Contact-Rich Manipulation.** [RSS 2025](https://roboticsconference.org/2025/program/papers/52/) · [프로젝트](https://reactive-diffusion-policy.github.io/).
- **[R5] T-Rex: Tactile-Reactive Dexterous Manipulation.** [논문](https://arxiv.org/html/2606.17055v1) · [프로젝트](https://tactile-reactive-dexterous.github.io/).
- **[R6] FTP-1: A Generalist Foundation Tactile Policy Across Tactile Sensors for Contact-Rich Manipulation.** [논문](https://arxiv.org/abs/2606.13102) · [프로젝트](https://ftp1-policy.github.io/).
- **[R7] ViTaR: Visuo-Tactile Residual Adaptation for Foundation VLA Manipulation.** [논문](https://arxiv.org/html/2608.15816v1).
- **[R8] VT-Bridge: Bridging Pretrained Foundation VLAs to VTLAs via Lightweight Residual Adaptation.** [공개 초록](https://arxiv.org/abs/2609.22606). 초록에서 구조적 중복을 확인했으며, 상세 학습·구현은 추가 확인 대상.
- **[R9] Self-Improving Vision-Language-Action Models with Data Generation via Residual RL (PLD).** [논문](https://arxiv.org/html/2511.00091v1).
