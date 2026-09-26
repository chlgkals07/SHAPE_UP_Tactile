[← 선행연구 목록](README.md)


# AnyTouch: Learning Unified Static-Dynamic Representation across Multiple Visuo-tactile Sensors



- 링크: https://arxiv.org/abs/2502.12191

- 읽은 사람: 임세화

- 날짜: 26.09.26

- ICLR 2025



# 내용



**해결하고자 한 문제**



(1) visuo-tactile sensor가 표준화가 잘 되지 않아서, 서로 다른 sensor들이 같은 tactile 정보를 포착하는데 있어서 차이를 보임.
-> robotic tactile sysyem, sensor specific data collection, model training 등에서 어려움이 있음. 

(2) 이를 해결하려고 multi-sensor data를 사용하려는 연구들이 있으나, aligned multi-sensor data가 부족해서 어려움이 존재함.  Touch2Touch가 dual-sensor paired dataset을 모으기도 했으나 특정 manipulation task에 국한되어 여전히 variety 측면에서 한계 존재함.  



<br>

**선행 연구와 차별점**



(1) 기존에도 different sensor로부터 multi-source tactile data를 함께 이용하려는 연구는 존재했음(Sparsh 같은 거). 하지만 이들은 multi modal data와 aligned multi sensor data를 사용하지는 않았으며, 우리는 이에 대한 dataset과 learning framework를 제안. 

(2) Touch2Touch는 2개의 sensor로부터 tactile image pair로 dataset을 만든 연구였음. 하지만 이 연구는 specific manipulation에 제한되었고, material이나 hardness같은 tactile은 고려 안 했으며, multi-modal information도 사용하지 않았음. 

(3) visual-tactile perception에 관한 연구는 계속 있었지만, visual-tactile sensor의 표준화가 잘 되지 않아서 다른 sensor에서 오는 large and diverse data를 사용하지는 못했으며 sensor transfer도 잘 안 되었음. 우리는 static and dynamic 관점에서 multi-sensor representation을 제안.

(4) tactile information을 image로서 나타내어 vision task에서의 representation learning을 적용한 연구들이 존재하지만, 이들은 "unified" visual-tactie representation for "various task"는 아님. 


<br>

**방법론**



(1) TacQuad: Aligned multi-modal multi-sensor tactile dataset 

multi-sensor aligned data with text and images

sensor: GelSight Mini, DIGIT, DuraGel(self-made), Tac3D(force fileld sensor)

GelSight Mini, DIGIT, DuraGel은 tactile image 수집용이고 Tac3D는 deformation force field 수집용임. 

Fine-grained spatio-temporal aligned data, Coarse-grained spatial aligned data

dataset 구성: tactile frame, paired visual image and attribute description

<br>

(2) AnyTouch: 

input: static tactile image or dynamic tactile video frames 

State 1 - Learning pixel level details: tactile image는 fine-grained data임. 
따라서 Masked Autoencoder로 pixel level detail을 learning. 일반적인 MAE loss와 video frame에 대해서는 next frame prediction loss 추가. 

Stage 2.1 - Multi-modal aligning: semantic level tactile 특성을 이해하고 multi-modal data로 sensor간의 차이를 채우려고. 

tactile과 vision만으로는 align하는데 어려움이 존재하며 text modality를 anchor로서 도입. 3가지 modality를 contrastive learning으로 align. 

Stage 2.2 - Cross-sensor matching: 동일 object에 대한 multi-sensor tactile representation을 clustering하려고. 

same object에 대한 것을 positive pair, different object에 대한 것을 negative pair로 해서 learning. 

Universal Sensor Token: training 시에 sensor-specific learnable token을 두는데, 이때 random하게 이를 universal sensor learnable token으로 바꿈. new sensor에 대해서 generalization을 하기 위해서. 


<br>


**결과**


(1) tactile representation pretraining이 중요했고 new sensor로 transfer되더라. 좋더라. 
 
(2) pretraining data와 downstream data의 overlap이 있을 때 그 효과가 훨씬 좋더라. CLIP과 같은 현상을 보였음. 

(3) 하드웨어 차이로 DIGIT data에 따른 performance 향상이 다른 sensor data에 비해서는 작더라. 

(4) real-world manipuation에서 dynamic video ablation 진행했고 dynamic perception도 학습한 것이 훨씬 잘 했음. 

<br>

**하드웨어**


In real-world manipuation task, 

arm:  6-DoF UFACTORY xArm  

hand: Robotiq 2F-140 gripper

tactile sensor: GelSight Mini




# 우리 연구와의 연결

**한계** 

(1) 여전히 dataset의 size, sensor의 종류가 부족하다고 언급함. 

(2) dynamic perception의 성능을 단일 manipulation task(pouring)으로만 평가함. 더 어려운 task에서도 평가할 필요가 있다고 언급. 

<br> 

**감상** 

(1) dataset이랑 pretrained encoder는 추후 우리 실험에서도 필요하다면 사용해볼 수 있음. 

(2) AnyTouch, Sparsh 같은 연구들은 dataset과 pretrained encoder에 대한 연구라서 encoder의 성능 위주의 연구이지 manipulation 위주 연구는 아님. 만약 우리가 manipulation task를 타겟한다면 이러한 pretrained encoder를 잘 써먹는게 좋을듯. 


