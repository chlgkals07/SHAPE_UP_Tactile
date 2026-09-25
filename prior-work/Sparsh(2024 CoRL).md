[← 선행연구 목록](README.md)


# Sparsh: Self-supervised touch representations for vision-based tactile sensing



- 링크: https://arxiv.org/abs/2410.24090

- 읽은 사람: 임세화

- 날짜: 26.09.05

- CoRL 2024



# 내용



**해결하고자 한 문제**



(1) tactile sensor를 바탕으로 하는 robot task에는 tactile input에 대응하는 state(label)을 estimate하는 것이 있음. 기존 연구들은 labeled data를 이용하는 custom model을 train해야 했음. 그래서 다른 task나 다른 sensor에 transfer가 되지 않아서 매우 비효율적임. 

-> existing dataset을 curating해서 하나의 massive tactile images dataset으로 만들고 SSL로 pretrained model을 training.

<br>

**선행 연구와 차별점**



(1) MAE, finetuning CNN, NN over pretrained representation(T-DEX, etc) 들이 존재했지만 이들은 특정 task나 sensor에 specific함. 

(2) alignment of visual and tactile modalities in latent space. 하지만 이는 tactile and visual property에만 초점을 맞추므로 dexterous manipulation에 필수적인 contact force같은 physical 정보는 무시하게 됨. 

위와 같은 문제를 해결하고자 하는 것임. 

(3) 또한, Sparsh와 비슷한 연구로 T3와 UniT가 있음. 

T3는 MAE objective와 labeld task-specific data로 supervision 줌. UniT는 GelSight Mini sensor에만 적용. 

Sparsh(Ours)는 SSL 기반이고 세 종류의 tactile sensor에 적용. 또한 우리는 benchmakr도 만들었음. 


<br>


**방법론**



(1) training SSL pretrained encoder model 

pixel reconstruction, latent reconstruction, clustering 방식을 비교. 

DIGIT와 Gelsight Mini에 대해서 background subtraction 해서 사용했고, 그 결과 no-contact에 대한 reference를 주고 generalize도 잘 되었음. 

(2) curating datasets

tactile domain에는 labeled and unlabeled data가 한정적이라서 존재하는 datasets이랑 새로운 datasets 잘 모아다가 큰 거로 만듦.

(3) TacBench: Tactile sensing benchmark

touch-centric tasks and labeld datasets for evaluation 

force estimation, slip detection, pose estimation, grasp stability, textile recognition, bead maze 

freeze pretrained Sparsh encoder and train decoder to produce output

<br>


**결과**



(1) benchmark evalution 내에서 pretrained encoder를 사용할 때 소량의 downstream data로도 합리적인 performance를 보였음.
 
(2) 전반적으로 JEPA나 Dino 계열이 우수했고 textile recognition에서는 pixel-level feature에 의존성이 강해서 MAE가 좋았음 

(3) Sparsh (DINO): physics-based tasks like force and pose estimation, Sparsh (IJEPA): touch semantic understanding

(4) Bead Maze 같은 robot manipulation에서는 high precision, error recovery 등으로 task를 완전히 해결하는데 한계 존재하였음. 


<br>

**하드웨어**



arm: Mecca Robot Arm 

hand: parallel jaw gripper

tactile sensor: DIGIT, GelSight, GelSight Mini


<br>

# 우리 연구와의 연결

**한계** 

(1) representation 학습할 때 tactile image의 history lengh ablation 안 했음. 

(2) bead maze task의 경우 task를 완전히 성공하여 끝내지는 못했음. 

<br>

**감상** 

(1) dataset이랑 pretrained encoder는 추후 우리 실험에서도 필요하다면 사용해볼 가치가 있을듯. 
특히 encoder가 있으니까 learning 쪽으로 활용할 가능성이 클 거 같음. 

(2) BehaviorVLA(ICML 2026 spotlight) 논문이 있는데 이 논문에서 vision, proprioceptive state history를 각 time step에 맞게 서로 align하면서 Mamba 구조로 update 해서 history를 관리하는 논문이 있음. 왜 그렇게 하냐면 camera로 받는 vision 정보랑 proprioceptive state가 temporal mismatch가 나는 것이 문제라고 하였음. 
여기에 tactile sensor 정보도 포함하면 더 좋아지지 않을까하는 생각이 들었음. 

(3) Bead Maze task 추후에 참고. 

(4) Bead Maze task를 완전히 설공한 경우가 없는 이유는 error 누적이나, recovery 능력 부족 등임. 이 논문에서는 pretrained encoder를 만들었다가 메인이라 그런 것을 해결할 필요가 없음. 
따라서 pretrained encoder 잘 이용해서 contact-rich and hard task를 잘 해결할 수 있는 method 설계하면 좋긴 할 듯 

