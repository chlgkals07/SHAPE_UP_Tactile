[← 선행연구 목록](README.md)


# RoboPack: Learning Tactile-Informed Dynamics Models for Dense Packing



- 링크: https://arxiv.org/abs/2407.01418

- 읽은 사람: 임세화

- 날짜: 26.09.26

- RSS 2024



# 내용



**해결하고자 한 문제**



(1) robot이 planning을 위해서 action과 tactile sensing 정보를 통합해야 하는데, dynamics model에 tactile sensing information을 통합하는 연구가 아직 명확하지 않음. 

이를 해결하기 위해서 

optimiation-based point tracking sysyem: raw observation을 keypoints로 처리
estimation module: tactile information을 prior interaction과 통합하고 future prediction을 위한 latent physics vector를 예측. 

<br>

**선행 연구와 차별점**



(1) 기존 dynamics model 연구에서는 visual observation을 위주로 사용했기 때문에 real world에서 관찰되지 않는 다른 변수들에 의해서 failure가 있었음. 그래서 우리는 tactile information과 history를 사용할 것임. 

(2) 기존 model-based RL과는 다르게 우리는 multi modal(visual and tactile) 정보를 사용. 또한 tactile observation history를 사용해서 partially observable state를 추정함으로써 online adaptation도 가능하게 하고자 함. 

(3) 이전에 manipulation task에 vision과 tactile 정보를 통합한 연구들은 존재함. 우리의 연구에서는 vision, tactile feedback을 dynamics를 learning하는데 사용할 것임. 


<br>


**방법론**

learn a state estimator(observation->state) and transition function(state, action -> state)

(1) Perception 

multi-view RGB-D visual observation을 받아서 object에 대한 3D keypoints를 추출

tactile observation에서부터 tactile particle을 추출하고, 이를 object partivle과 결합해서 보이는 scens의 하나의 particle represenation을 만듦. 

(2) State estimation 

state를 object particles와 object-level latent physics vector로 정의. 

GNN과 LSRM 아키텍처로 tactile history를 state estimation에 사용. 
추정된 previous state와 이전과 현재 시점의 tactile feedback에 대해서 graph 구성. 
그리고 estimator가 autoregressivegkrp object paricle과 latent physics vector를 prediction. 

(3) Dynamics Prediction 

state estimator로 state가 추정되면, dynamics model이 action plans를 위한 future를 예측. 
이때는 tactile observation 이용 안 함. physics vector는 업데이트 안 함. 
next step의 particle position을 예측. 

(4) Model-Predictive Control

cost fuction optimization 하는 방식으로 action sampling 


<br>

**결과**


(1) box pushing 에서 physics parameter가 box type에 따라서 clustering되는 것을 보였음. 특히 unseen box에 대해서도 cluster됨. 또한 초기에는 cluster가 잘 되지 않았지만, history가 쌓이면서 box type에 따른 parameter가 제대로 cluster됨. 

(2) dense packing은 occlusion이 심한 task인데 tactile 정보 ablation을 진행했고 tactile 유무가 성능에 큰 영향을 주었음. 


<br>

**하드웨어**



arm: Franka Emika Panda 7-DoF

hand: gripper 

tactile sensor: Soft-Bubble tactile sensor


<br>

# 우리 연구와의 연결

**한계** 

(1) 논문에 자기들이 직접 명확한 한계를 적지는 않았음 

(2) 개인적으로는, LSTM과 GNN 사용했기 때문에 long horizon task로 가면은 history context 너무 길어져서 성능이 붕괴할 수도 있지 않을까하는 생각을 해봄. 

<br>

**감상** 

(1) box pushing, dense packing task는 참고할 수 있을 듯. 

(2) GNN, LSTM을 대충 정도로 알아서 아키텍처 자체는 대충 보긴 했지만, progress가 진행될수록 parameter가 cluster 되는 것을 보면은 visual과 tactile history를 context로 가지고 가는 것이 도움이 크게 되는 것 같다고 생각함. 특히 이거로 generalize나 long horizon도 다룰 수 있지 않을까. BehaviorVLA와 연결 가능성이 여기서 또 있다고 생각이 들었음. 


