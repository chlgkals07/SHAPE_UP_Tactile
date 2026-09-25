[← 선행연구 목록](README.md)



\# Dexterity from Touch: Self-Supervised Pre-Training of Tactile Representations with Robotic Play



\- 링크: https://arxiv.org/abs/2303.12076

\- 읽은 사람: 임세화

\- 날짜: 26.09.05

\- CORL 2023



\# 내용



**해결하고자 한 문제**



(1) tectile sensor는 simulation, calibtration 하기 어려움.

(2) multi-fingered hands에서는 tactile sensor가 large area를 커버해야 해서 high dimensional임.  



**선행 연구와 차별점**



(1) two-fingered gripper에 적용해본 선행 연구와 다르게, multifingered hand에 적용.

(2) 선행 연구에서는 tactile representation을 위해서 많은 양의 task-centric data가 필요했지만,

우리는 task-agostic play data로 pretrained tactile encoder를 학습하고 그 다음에 task마다 소량의 demo만으로 policy 학습.  



**방법론**



(1) task-agostic play data를 많이 수집 -> tactile encoder를 pretraining.

(2) non-parametric policy such as Nearnest Neighbor (parametric model은 data를 많이 필요로 해서)

task-specific demonstration을 소량으로 수집. visual and tactile observation을 input으로 하여 non parametric policy 학습.

이때 tactile observation을 pretrained tactile encoder로 feature를 추출해서 사용.  



**결과**



policy input으로 both(vision, tactile), vision only, tactile only하여 비교한 실험에서

vision only는 contact를 잘 인지하지 못했고, tactile only는 robot의 위치를 제대로 못잡음.  



**하드웨어**



arm: 6-dof Kinova Jaco

hand: a 16-dof Allegro hand with four fingers

tactile sensor: 15 XELA uSkin  



\# 우리 연구와의 연결



(1) task-specific tactile data를 모으는 것은 어려움.

왜냐하면 사람이 teleoperation할 때 사람은 tactile 정보로 feedback이 불가능하기 때문에 tactile이 중요한 task에서는 성공한 demo를 모으기 어려움.



(2) tactile observation도 high dimensional이라 잘 처리하는 방법이 중요함.



(3) 논문에서는, OOD 성능이 낮다는 것과 offline imitation learning 기반으로만 했다는 것을 한계로 둠.



(4) 개인적인 생각으론, data 부족으로 non parametric policy를 사용하기 때문에 data를 잘 모아서 parametric model로 가는 것이 좋을 것 같다고 생각함.

