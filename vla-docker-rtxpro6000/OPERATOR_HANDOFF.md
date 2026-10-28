# 운영진 전달 사항

목적: NVIDIA RTX PRO 6000 Blackwell에서 π0.5 우선, FTP-1 차순위,
UniVTAC/Isaac Sim 5.1은 별도 환경으로 추가할 수 있는 연구용 인스턴스.

## 우선 배포할 대상

```bash
docker build --target models -t vla-rtxpro6000:models .
```

위 빌드에는 π0.5/FTP-1이 서로 다른 conda 환경에 설치됩니다. UniVTAC은 소스만
포함됩니다. FTP-1 설치에 실패하면 `--target pi05`로 1순위 이미지를 먼저 만들 수 있습니다.
UniVTAC 전체 설치는 선택적으로 `--target full --build-arg ACCEPT_ISAAC_EULA=YES`를
사용하며, Blackwell 대응 버전 조정이 실제 서버에서 검증되지는 않았습니다.

## 기존 접속 계약 적용

- `openssh-server` 패키지는 있지만 sshd 자동 실행/패스워드/공개키는 넣지 않았습니다.
- 기존 서비스의 공개키 주입·환경변수·onstart·sshd 래퍼를 적용해 주세요.
- ENTRYPOINT를 기존 래퍼로 교체해도 됩니다. workspace 초기화가 필요하면 onstart에서
  `bash /opt/vla/scripts/init-workspace.sh`를 호출해 주세요.
- 로그인 셸에서 `/etc/profile.d/vla.sh`를 읽도록 해 주세요. 비로그인 셸에서는 수동 source.
- WORKDIR은 `/workspace`입니다. 모델 소스는 `/opt/repos`에 있으므로 `/opt` 전체를
  bind mount하여 가리지 않도록 해 주세요.
- 기본 환경 `/opt/conda/envs/pi05`, `/opt/conda/envs/ftp1`은 이미지의 일부입니다.
- 나중에 설치하는 환경은 `/workspace/conda-envs/univtac`입니다.
- `/workspace`만 영속 볼륨으로 두면 됩니다. 다른 새 인스턴스에서 자동 재사용된다는
  가정은 하지 않았습니다.

## GPU/렌더러 조건

- NVIDIA Container Toolkit 및 해당 GPU를 지원하는 호스트 드라이버가 필요합니다.
- `NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,display`를 노출해 주세요.
- 최소 한 GPU가 컨테이너에서 보여야 합니다. GPU 식별과 할당은 서비스 정책을 따릅니다.
- shm 기본 예시는 16GB입니다. 기존 자원 할당 규칙을 적용하면 됩니다.
- Isaac EULA/개인정보 동의 및 root 실행 관련 값은 검토한 운영 정책에 따라 런타임에
  넣어 주세요. 이 패키지는 개인정보 동의 값을 자동 고정하지 않습니다.
- 사용자가 부여된 컨테이너 안에서 Docker daemon을 실행할 필요는 없습니다.

## 배포 후 확인

```bash
nvidia-smi
source /etc/profile.d/vla.sh
bash /opt/vla/scripts/init-workspace.sh
vla-check pi05
vla-check pi05 --jax
vla-check ftp1
```

이 검사는 모델 다운로드 없는 import/버전/일부 CUDA 커널 검사입니다. 전체 학습 성공을
의미하지 않습니다. 실제 모델 추론은 사용자 체크포인트와 설정으로 확인해야 합니다.
UniVTAC을 설치했다면 다음의 렌더링/촉각 smoke test도 필요합니다.

```bash
OMNI_KIT_ACCEPT_EULA=YES OMNI_KIT_ALLOW_ROOT=1 vla-check univtac
```

## 재현 기록 보관

첫 성공 빌드 후 `/opt/vla/manifests`와 `docker image inspect`의 이미지 digest/ID를
함께 보관해 주세요. 두 노드에는 동일 이미지로 배포해 주세요.
작성 환경에서는 Docker 빌드와 실제 GPU 검증을 하지 못했습니다.
