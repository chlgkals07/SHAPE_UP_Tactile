# VLA Architectue and Using Tactile in Vla

**VLA architecure**

<br> 

diffusion policy: https://arxiv.org/abs/2303.04137 : 엄밀히 말하면 vla는 아니지만 최근 vla 아키텍처의 시초임. 

pi0: https://arxiv.org/abs/2410.24164v4

pi05: https://arxiv.org/abs/2504.16054

gr00t: https://arxiv.org/abs/2503.14734 : pi와 gr00t는 아키텍처 차이는 거의 없고 vlm을 frozen 하는지 안 하는지 차이가 있음. report 되는 논문들 보면 pi가 gr00t보다 성능이 일반적으로 좋긴 함. 하지만 무조건 pi를 사용할 필요는 없고 무엇을 쓰든 우리 방법론이 효과적이다라는 것을 보일 수만 있으면 됨. 그래서 무조건 vla를 사용할 필요는 없음. 

<br> 

위 논문 4개는 모든 내용을 읽어볼 필요는 없고, 
데이터 구성, 모델 input output, 모델 아키텍처, Finetuning 어떤 식으로 하는지 등만 보아도 될 거 같아. 
그냥 최근 robot learning 쪽에서는 이런 식으로 모델을 짜고 로봇을 제어하는구나 공부하는 정도. 

<br> 

**Using Tactile in VLA**

<br> 

tactile-vla: https://arxiv.org/abs/2507.09160 : tactile을 vla에 거의 처음으로 적용한 논문이고 pi에 적용. 

FTP-1: https://arxiv.org/abs/2606.13102 : tactile pretrained expert를 pi와 결합한 pretrained tactile vla. dexterous hand 사용.

Canonical Representation and Force-Based Pretraining of 3D Tactile for Dexterous Visuo-Tactile Policy Learning: https://arxiv.org/abs/2409.17549 : 하민이가 처음에 알려준 논문. vla는 아니지만 우리 세팅이랑 유사해서. 

<br> 

위 논문 3개는 다 읽어도 좋을 것 같고, tactile을 이런 식으로 기존 모델에 추가하는구나, 이런 식으로 tactile 정보를 처리할 수 있구나 참고하면 좋을듯. 
