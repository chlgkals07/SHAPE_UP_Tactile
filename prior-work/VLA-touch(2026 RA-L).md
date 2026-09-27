[← 선행연구 목록](README.md)


# VLA-Touch: Enhancing Vision-Language-Action Models with Dual-Level Tactile Feedback


- 링크: https://arxiv.org/abs/2507.17294

- 읽은 사람: 임세화

- 날짜: 26.09.27

- RA-L 2026



# 내용



**해결하고자 한 문제**



(1) prior works는 task-specific policy에 tactile sensing을 결합. 하지만 large-scale foundation model에 tactile 사용하는 것은 아직 underexplored. 

(2) Current VLA는 tactile input을 받도록 pretrained 되지 않았기 때문에 tactile feedback을 사용하는데 어려움이 있음. 따라서 tactile input에 대한 prior가 없는 VLA 내지 embodied AI에 어떻게 tactile information을 활용하게 할 것인지가 중요함. 

<br>

**선행 연구와 차별점**

(1) Current VLA는 vision과 proprioceptive state에 의존. 추가적인 sensor modality 이용하는 VLA도 나오고는 있지만, task-level reasoning에 하고 precise manipulation을 타겟하지 않았거나 vision과 tactile 두 modality를 합쳐서 사용하지 않았음. 

(2) 선행 연구인 tactile-language model을 활용해서 우리는 task planning에 활용할 것임. 

(3) tactile 사용하는 policy 연구들이 존재하지만 대부분 특정 task에서 control-level improvement를 타겟함. 우리는 two level로 나누어서 task planning과 precise manipulation에 tactile을 활용. 

<br>


**방법론**


(1) Task Planning: Tactile-Assisted 

VLM task planner: GPT-4o

tactile-language model: Octopi (for GelSight Sensor)

tactile-language model은 tactile signal을 language description으로 바꾸고 planner에게 전달.

planner는 주어진 goal, current observation, language tactile description을 받아서 manipulation instruction을 생성하고 VLA에게 전달.  

(2) Policy Refinement: with Tactile Sensing 

VLA는 tactile signla을 받도록 pretrained되지 않았으므로, interpolant-based diffusion controller(BRIDGeR)를 사용

controller는 VLA-generated action chunk, visual observation, tactile signal을 input으로 받고 refined action chunk를 생성. 

이때 tactile signal의 경우 RDP의 방식을 차용해서 aggregated force를 계산해서 compact하게 사용한다고 함(필요 시 논문 참고)

<br>

**결과**

(1) planner가 tactile 정보 안 쓰는 것, tactile image 자체로 사용하는 것보다 tactile-language model의 description을 사용하는 것이 성능 좋았음. 

(2) policy가 RDT base, RDT + Residual controller, RDT + Interpolant controller 비교했을 때 Ours에 해당하는 Interpolant가 좋았음. 


<br>

**하드웨어**


arm: Franka Emika Panda 

hand: Robotiq 2F-140 gripper

tactile sensor: GelSight Mini



# 우리 연구와의 연결

**한계** 

(1) Ours는 modular sysyem임. end-to-end처럼 planner, tactile model, controller를 더 타이트하게 통합해서 redundancy와 latency를 줄일 여지가 있을 것이라고 언급함. 

(2) tactile-language model기 pretraining에서 사용한 dataset과 ours setting의 gripper setup이 달라서 measurement에서 차이가 있었음. 이 차이가 object hardness에서 관찰되었다고 함. 

(3) object positioning이나 target location task에만 적용함. 더 다양한 task에 적용할 필요 있음. 

(4) Interpolant controller가 latenct가 너무 느려서 high frequency tactile feedback을 이용하지 못함. 

<br>

**감상** 

(1) high frequency tactile feedback을 사용하는 것이 다른 연구들에서도 강조하는 연구 축이었는데 여기서는 그것을 못했고, 논문에서도 그것의 필요성을 말하긴 함. high frequency로 어떻게 할 수 있는지에 대한 방향성도 좋은듯. 

(2) pretrained model이나 open dataset 중에 써먹을만한거 있나 찾아보면 좋을듯. 

(3) 이때까지 읽은 논문들은 대부분 gripper에서 해서, 우리가 leap hand로 한다고 하면 이것만으로도 노벨티 있을지도? 

