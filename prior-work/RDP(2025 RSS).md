[← 선행연구 목록](README.md)


# Reactive Diffusion Policy: Slow-Fast Visual-Tactile Policy Learning for Contact-Rich Manipulation



- 링크: https://arxiv.org/abs/2503.02881

- 읽은 사람: 임세화

- 날짜: 26.09.05

- RSS 2025



# 내용



**해결하고자 한 문제**



(1) 기존 tactile input을 imitation learning에 합친 연구들은 observation level에 국한됨. 즉 추가적인 정보 제공 용도로만 사용함.

(2) action chunking은 많은 장점이 존재하지만 환경 변화에 대한 반응성이 좋지 않아서 low-precision task로 제한됨.

(3) traditional teleoperation로는 fine-grained tactile feedback을 가진 demostration을 모으기 어려움. 

<br>

**선행 연구와 차별점**



(1) Our teleoperation sysyem: low-cost VR controller와 tactile sensing 장점 결합. 다른 tactile sensor나 robot platform에 적용하기 쉬움.

(2) 기존 tactile 선행 연구는 task-specific modeling, hand-designed primitives, hand-crafted reward -> task에 대한 generalization가 안 좋았음.

(3) visual imitation learning에서도 tactile을 합치는 연구가 있지만, 한정적인 input modality만 사용하거나 simple task에 제한되었음.

(4) action chunking은 장점도 있지만, real time feedback이 안 되어서 tactile 같은 high-frequency signal을 이용하기 어려움. temporal ensemble로 해결하려고 한 VISK도 있으나 얘는 multi-modal distribution과 non-Markovian modeling이 안 좋음.

RDP는 normal force, shear force, visual RGB inputs을 모두 사용하여 visual-tactile policy를 만듦.

<br>

**방법론**



(1) TactAR(Teleoperation Sysyem)

tactile sensor가 받아온 값을 3D deformation field로 transformation해서 AR에 mapping

cross sensor, cross embodiment 가능한 시스템이라고 강조하심. 이 방법 사용해볼거면 나중에 다시 정독.

<br>

(2) RDP(Reactive Diffusion Policy)

tactile sensor에 대해서는 PCA feature를 뽑아서 사용. force sensor에 대해서는 6D 값을 그냥 concat해서 사용.

latent space 상에서 action chunk를 Latent Diffusion Policty가 prediction

Asymmetric Tokenizer(AT)는 latent action chunk와 tactile representation을 입력으로 받고 real action prediction



<br>

**결과**


(1) 단순히 tactile signal을 concat해서 넣어주는 것보다 low dimensional feature를 뽑아서 사용하는 것이 더 robust하였음.

(2) reactive behavior를 보일 뿐만 아니라 multi-modal behavior도 보였음 

(3) evaluation시에 perturbation으로 contact을 놓친다거나 하더라도 이에 대해 반응하고 빠르게 행동을 개선하는 것을 보였음. 

naive DP는 한 번 생성된 action chunk를 전부 실행해야 해서 perturbation에 대해서 즉각 반응하지 못했음 

(4) TactAR로 data를 수집할 때 teleoperator들은 훨씬 수월했다고 응답했으며 그에 따른 policy의 성능도 더 높았음. 

<br>

**하드웨어**


arm: two Flexiv Rizon 4

hand: two Flexiv Grav grippers

tactile sensor: two different optical tactile sensors (GelSight Mini and MCTac)

ar: Meta Quest3

<br>

# 우리 연구와의 연결

**한계** 

(1) TactAR은 high-quality data를 수집하는 방법이지 teleoperation을 efficient하게 하지는 못함. 

(2) two-finger grippers에만 적용하였음.

(3) high-frequency image input에는 반응 못함. 

(4) Diffusion Policy에 적용하였기 때문에 single-task에 국한됨. VLA로의 확장성 언급함. 

<br>

**감상** 

(1) TactAR보다 더 좋은 방법이 있는지는 모르겠지만 이러한 teleoperation 방법이 널리 쓰이고 사용 가능하다면 그렇게 하는게 좋을수도

(2) 2025년 논문이고 citation이 꽤 높아서, 이후로 발전된 연구 많이 나왔을듯. 이후 논문 찾아볼 필요 있을듯. 

(3) 문제 인식과 그에 대한 해결법이 명확한 거 같음. 

(4) contact-rich task를 우리도 정해야 할 텐데, 참고문헌에서 사용한 task 참고하면 좋을듯. 
