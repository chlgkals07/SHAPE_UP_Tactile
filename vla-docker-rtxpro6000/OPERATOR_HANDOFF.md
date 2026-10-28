# 운영진 전달 사항

목적: NVIDIA RTX PRO 6000 Blackwell에서 π0.5 우선, FTP-1 차순위,
UniVTAC/Isaac Sim 5.1은 별도 환경으로 추가할 수 있는 연구용 인스턴스.

## 이번 요청: `models` 하나만 빌드·배포

**운영진께 요청하는 빌드 대상은 `models` 하나입니다.** 아래 명령으로 만든
`vla-rtxpro6000:models` 이미지를 기존 SSH·인스턴스 시스템에 연결해 주세요.
`pi05`·`full`을 추가로 빌드하거나 UniVTAC을 설치할 필요는 없습니다.

서버에서 실행할 명령은 다음과 같습니다. 이미 저장소를 받았다면 `git clone`을
생략하고 해당 저장소의 `vla-docker-rtxpro6000` 폴더에서 빌드하세요.

```bash
git clone https://github.com/chlgkals07/SHAPE_UP_Tactile.git
cd SHAPE_UP_Tactile/vla-docker-rtxpro6000
docker build --target models -t vla-rtxpro6000:models .
```

이 이미지에는 π0.5/FTP-1이 서로 다른 conda 환경에 설치되며, UniVTAC은 소스만
포함됩니다. **이번 범위는 `models` 빌드, 기존 접속 계약 적용, 아래 모델 환경
확인까지입니다. UniVTAC/Isaac 설치·검증은 배포 완료 조건이 아닙니다.**

다른 타깃은 다음 상황에서만 선택합니다.

- `pi05`: `models` 빌드가 FTP-1 설치 단계에서 실패했을 때의 대안입니다.
- `full`: 추후 별도 요청이 있을 때만 검토하는 실험적 전체 빌드입니다.
  이번에는 생략해 주세요. UniVTAC은 연구자가 필요할 때 `/workspace`의
  별도 conda 환경에 추가할 예정입니다.

Dockerfile의 마지막 `default` 스테이지도 `models`를 그대로 상속하지만,
운영진은 위의 `--target models` 명령으로 대상을 명시해 주세요.

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
다음은 연구자가 추후 UniVTAC을 설치했을 때만 실행하는 선택적 검사입니다.
**이번 `models` 배포에서는 생략합니다.**

```bash
OMNI_KIT_ACCEPT_EULA=YES OMNI_KIT_ALLOW_ROOT=1 vla-check univtac
```

## 재현 기록 보관

첫 성공 빌드 후 `/opt/vla/manifests`와 `docker image inspect`의 이미지 digest/ID를
함께 보관해 주세요. 두 노드에는 동일 이미지로 배포해 주세요.
작성 환경에서는 Docker 빌드와 실제 GPU 검증을 하지 못했습니다.
