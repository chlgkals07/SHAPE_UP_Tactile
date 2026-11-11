# 3D Diffuser Actor

**Title:** 3D Diffuser Actor: Policy Diffusion with 3D Scene Representations

- **Venue:** RSS 2024

## 0. Takeaway

3D RoPE 3D token에 대해서 각 token의 실제 (X,Y,Z) 좌표를 바탕으로 하여 3D RoPE 적용

## 1. Introduction

3D robot policies

input: tokenzied 3D scene representation, language instruction, noised end-effector’s state traj

model represents the scene tokens and end effector locations in the same 3D space and fuses them with relative-position 3D attentions

3D Diffusion Policy와 비슷한 goal(combining 3D representation with diffusion objectives)이지만, 매우 다른 아키텍처임.

3D Diffusion Policy는 tokenized 3D scene representation을 받디 않고, 3D scene point cloud에서 pooling된 1D embedding 사용.

우리는 비교 실험을 진행했고 능가하였음. 그리고 이는 tokenized scene representation때문이라고 생각하며 이는 scene change에 robust함. 왜냐하면 scene의 일부가 변화했다고 할 때 3D scene token은 변화에 대응되는 부분만 영향받으면 되는데 pooled embedding은 전체가 바뀌어버림.

## 2. Related Works

### 2.1. Learning manipulation policies from demonstrations

### 2.2. Diffusion Models in robotics

### 2.3. 2D and 3D scene representations for robot manipulation

기존 end-to-end image-to-action policy는 2D observation으로부터 end-effector pose를 예측하게 됨.

하지만 이는 많은 양의 demonstration을 필요로 한다는 점에서 cost가 소요됨.

또한 3D scene-to-action policy도 있는데 resolution때문에 computationally 비쌈.

Act3D: compute 3D action map by samping 3D points in the empty workspace and featurizing them using cross attention to 3D scene points.

## 3. Method

---

**Notion 원문:** https://app.notion.com/p/415be171a76280d18a9ac967d636b224

**내용 출처:** https://app.notion.com/p/414be171a76280d397f4f3c843c10de7
