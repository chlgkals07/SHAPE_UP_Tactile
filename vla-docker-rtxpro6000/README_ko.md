# RTX PRO 6000용 VLA Docker 빌드 구성

이 패키지는 **이미지를 만드는 소스와 설치·검증 절차**입니다. 빌드된 이미지
파일(`docker save`로 만든 tar)은 포함하지 않습니다. 작성 환경에 Docker 실행기와
GPU가 없어, 실제 의존성 해결·Docker 빌드·GPU 실행은 아직 확인하지 못했습니다.
`VALIDATION.json`에 수행한 검사와 수행하지 못한 검사를 구분했습니다.

## 운영진: 이번에는 `models` 이미지만 빌드·배포해 주세요

**이번 요청의 기본 배포 대상은 `models` 하나입니다. 아래 명령으로 빌드한
`vla-rtxpro6000:models` 이미지를 기존 인스턴스 시스템에 연결해 주세요.**
`pi05`·`full` 타깃을 따로 빌드하거나 UniVTAC을 추가 설치할 필요는 없습니다.

서버에서 다음 명령을 순서대로 실행합니다. 이미 저장소를 받았다면 `git clone`은
생략하고 해당 저장소의 `vla-docker-rtxpro6000` 폴더로 이동해 빌드하면 됩니다.

```bash
git clone https://github.com/chlgkals07/SHAPE_UP_Tactile.git
cd SHAPE_UP_Tactile/vla-docker-rtxpro6000
docker build --target models -t vla-rtxpro6000:models .
```

- **포함:** π0.5와 FTP-1을 각각 독립된 Python 환경에 설치하고, UniVTAC 소스를 포함합니다.
- **추후 선택 사항:** UniVTAC/Isaac Sim/Isaac Lab 실행 환경은 연구자가 필요할 때
  별도 conda 환경으로 추가합니다. 이번 이미지 배포의 완료 조건이 아닙니다.
- **배포 연결:** 기존 SSH 공개키 주입·승인·onstart 래퍼 적용 사항과 배포 후 확인 명령은
  [OPERATOR_HANDOFF.md](OPERATOR_HANDOFF.md)를 참고하세요.

아래의 다른 빌드 타깃과 UniVTAC 설치 설명은 참고용입니다. **`models` 빌드가
성공하면 다른 타깃을 빌드하지 않고 해당 이미지로 배포를 진행해 주세요.**

## 선택한 구성

NVIDIA RTX **PRO** 6000 Blackwell, Linux x86_64 서버를 대상으로 합니다.
RTX A6000이나 RTX 6000 Ada를 의미하지 않습니다. 실제 장비에서 `nvidia-smi`와
GPU capability를 확인하세요. Blackwell PRO 6000의 목표 아키텍처는 `sm_120`입니다.

| 항목 | 기본값 |
|---|---|
| 기본 이미지 | `nvidia/cuda:12.8.1-devel-ubuntu22.04` |
| Python | 각 환경에 3.11 |
| conda 배포판 | Miniforge 25.3.1-0 |
| uv | 0.8.22 |
| 모델용 PyTorch / torchvision | 2.7.1+cu128 / 0.22.1+cu128 |
| 모델용 NumPy / Transformers | 1.26.4 / 4.53.2 |
| 모델용 JAX | 공식 저장소와 같은 0.5.3, CUDA 12 플러그인 |
| OpenCV | 모델 환경에서는 headless 4.11.0.86 |
| TorchCodec | 0.4.0 (PyTorch 2.7 계열 ABI) |
| UniVTAC 추가 시 | Isaac Sim 5.1.0 / Isaac Lab 2.3.0, 별도 conda 환경 |

**하나의 이미지 안에 여러 Python 환경**을 만듭니다. π0.5와 FTP-1은 둘 다
`openpi` 패키지를 설치하므로 한 Python 환경에 함께 editable 설치하면 안 됩니다.
패키지 이름을 바꾸거나 모델 코드를 합치지 않고, 환경별로 각자의 소스를 사용합니다.

## 우선순위와 빌드 대상

| Docker target | 이미지에 설치되는 것 | 용도 |
|---|---|---|
| `pi05` | π0.5 환경 + 세 저장소 소스 | FTP-1 설치에도 문제가 생길 때의 우선순위 1 대안 |
| `models` (**이번 배포 대상**) | π0.5 + FTP-1 환경 + UniVTAC 소스 | 우선 두 모델을 사용하고 UniVTAC은 나중에 conda로 추가 |
| `full` | 위 구성 + UniVTAC/Isaac/TacEx/cuRobo 설치 시도 | 실험적인 Blackwell용 전체 빌드 |

Docker target을 생략하면 마지막 `default` 스테이지가 선택되며, 이는 `models`를 그대로
상속합니다. 운영진은 혼동을 피하도록 위의 `--target models` 명령을 사용해 주세요.
`models`에는 Isaac Sim/Isaac Lab/UniVTAC의 실행 의존성이 **아직 설치되지 않습니다.**
`full` 실패를 무시하거나 설치 성공으로 표시하지 않습니다. 실패하면 `models`를 쓰세요.

## 선택 사항: 대체·전체 빌드 (이번 배포에서는 생략)

**이 절은 필요할 때만 참고합니다. `models` 빌드가 성공했다면 아래 명령은
실행하지 않아도 됩니다.**

### `pi05`: FTP-1 빌드 실패 시에만 쓰는 대안

`models` 빌드가 FTP-1 설치 단계에서 실패할 때만 π0.5 단독 이미지를 먼저
배포하는 대안입니다. 정상적인 `models` 배포에 추가로 필요한 이미지가 아닙니다.
앞서 이동한 Dockerfile 폴더에서 실행합니다.

```bash
docker build --target pi05 -t vla-rtxpro6000:pi05 .
```

### `full`: 추후 별도 요청이 있을 때만 검토

**운영진에게 이번 `full` 빌드를 요청하지 않습니다.** UniVTAC까지 미리 설치할
필요가 생기면 검토할 수 있는 실험적 옵션입니다. 기본 배포 후 연구자가
`/workspace`에 conda 환경을 추가하는 방법으로도 진행할 수 있습니다.

전체 빌드를 선택하는 경우에만 NVIDIA 라이선스를 검토한 뒤 다음을 실행합니다.

```bash
docker build --target full \
  --build-arg ACCEPT_ISAAC_EULA=YES \
  --build-arg UNIVTAC_BUILD_JOBS=4 \
  -t vla-rtxpro6000:full .
```

`full`은 C++/CUDA 확장을 빌드하므로 시간·디스크·RAM이 많이 필요합니다.
`full`의 설치·검증은 이번 `models` 배포의 완료 조건이 아닙니다.

모든 빌드에는 패키지 서버 및 GitHub 접근이 필요하고, 모델 가중치와 데이터셋은
별도로 내려받습니다. 대형 데이터나 API 키, SSH 개인키를 이미지에 넣지 마세요.

학교 서버에서는 운영진이 기존 SSH 공개키 주입·승인·onstart 래퍼를 적용해야 합니다.
이 이미지에 `openssh-server`는 있으나 임의 비밀번호나 공개키를 넣어 SSH를 열지 않습니다.
자세한 전달 사항은 [OPERATOR_HANDOFF.md](OPERATOR_HANDOFF.md)에 있습니다.

## 접속 후 환경 선택

SSH 로그인 셸에서 기본 π0.5 환경이 활성화됩니다. 필요하면 다음을 실행합니다.

```bash
source /etc/profile.d/vla.sh
vla-use pi05
python -c 'import torch; print(torch.__version__, torch.version.cuda)'
vla-check pi05
```

FTP-1으로 전환합니다.

```bash
vla-use ftp1
vla-check ftp1
```

`vla-use`는 conda 환경을 활성화하고 해당 저장소로 이동하는 셸 함수입니다.
이미지 ENTRYPOINT가 교체된 시스템에서도 `/etc/profile.d/vla.sh`를 source하면 됩니다.

GPU가 없는 빌드 환경에서는 CPU import 검사만 수행합니다. 서버에서 기본 GPU 검사에
통과한 뒤 JAX도 따로 검사합니다. JAX GPU 검사는 CPU fallback을 성공으로 처리하지 않습니다.

```bash
vla-check pi05 --jax
vla-check ftp1 --jax
```

이 검사는 import, 패키지 버전, PyTorch GPU 행렬곱/NMS, 선택적 JAX GPU JIT 검사입니다.
실제 체크포인트를 읽거나 전체 모델 학습·벤치마크 성공을 검증하는 명령은 아닙니다.
모델 테스트에는 가중치, 정규화 통계, 데이터 경로와 실험 config가 추가로 필요합니다.
π0.5 PyTorch 구현은 공식 저장소 기준 JAX 구현과 기능 범위가 다릅니다. 특히 JAX용
LoRA/FSDP 예제를 PyTorch에서 그대로 쓸 수 있다고 가정하지 마세요.

## 실제 학습 명령을 쓸 때

README의 실행 명령은 선택한 환경에서 `python ...`으로 실행하거나 다음 형식을 씁니다.

```bash
vla-use pi05
uv run --frozen --no-sync scripts/serve_policy.py --help
```

`uv sync`를 다시 실행하면 수동 복사한 Transformers 패치가 원본 wheel로 돌아갈 수 있습니다.
의존성을 바꿨다면 패치를 다시 적용하고 검사하세요.

```bash
python /opt/vla/scripts/patch_transformers.py "$VLA_REPO"
vla-check pi05
```

기본 프로젝트 코드는 `/opt/repos/openpi`, `/opt/repos/ftp1-policy`에 있고 이미지에
들어 있습니다. **이 위치에 직접 수정한 코드는 인스턴스 삭제 시 사라집니다.**
연구용 수정본은 `/workspace/src`에 복사한 후 현재 환경에 재연결할 수 있습니다.
예를 들어 π0.5는 다음과 같습니다(최초 한 번, 목적 폴더가 없을 때).

```bash
vla-use pi05
cp -a /opt/repos/openpi /workspace/src/openpi
cd /workspace/src/openpi
uv pip install --python "$CONDA_PREFIX/bin/python" --no-deps -e .
python /opt/vla/scripts/patch_transformers.py /workspace/src/openpi
```

이후에는 `/workspace/src/openpi`에서 실행하세요. 새 컨테이너의 이미지 기본 환경은 다시
`/opt/repos`를 가리키므로 같은 `/workspace`가 연결되었다면 editable 재연결도 다시 해야 합니다.
별도 새 인스턴스에 기존 `/workspace`가 자동으로 붙는지는 운영진 정책에 따릅니다.

## UniVTAC을 나중에 /workspace에 설치하기

NVIDIA 라이선스를 검토한 뒤 실행합니다. 기존 두 모델 환경은 변경하지 않습니다.

```bash
OMNI_KIT_ACCEPT_EULA=YES UNIVTAC_BUILD_JOBS=4 vla-install-univtac
```

소스는 `/workspace/src/UniVTAC`, conda 환경은 `/workspace/conda-envs/univtac`에 둡니다.
실행 중인 서버가 외부 패키지 서버와 GitHub에 접근할 수 있어야 합니다.
기존 동명 경로가 있으면 원본을 덮어쓰지 않고 그 경로의 소스를 사용하므로,
다른 버전의 소스라면 패치 전제조건 검사에서 멈출 수 있습니다.

설치가 끝나면 실제 GPU에서 확인합니다.

```bash
vla-use univtac
OMNI_KIT_ACCEPT_EULA=YES vla-check univtac
```

이 검사는 시뮬레이터·렌더러·두 개의 촉각 센서를 실제로 만드는 공식 smoke test입니다.
빌드 시 설정한 EULA 변수는 런타임에 자동으로 유지하지 않습니다. 실행할 때 따로 지정하세요.
root에서 실행 제한이 나오면 승인된 런타임에 `OMNI_KIT_ALLOW_ROOT=1`을 추가하세요.
초기 asset 다운로드가 필요할 수 있습니다.

### UniVTAC을 '실험적'이라고 표시한 이유

확인한 `isaac51` 브랜치는 기본적으로 CUDA 12.6, torch 2.7.0+cu126, 아키텍처 8.9를
대상으로 설치하도록 고정되어 있습니다. 이 구성은 sm_120을 네이티브 컴파일하기 위한
기본값과 맞지 않아 다음 부분을 명시적으로 바꿉니다.

1. toolkit과 nvcc 버전 검사: 12.6 → 12.8
2. torch/torchvision: 2.7.0+cu126 / 0.22.0 → 2.7.1+cu128 / 0.22.1
3. TacEx의 torch-scatter wheel: pt27cu126 → pt27cu128
4. CUDA 컴파일 대상: 8.9 → 12.0 (CMake 값은 120)
5. `+cu128` wheel 버전을 고려하도록 버전 검사 수정
6. conda 채널을 conda-forge로 정리하고 build용 pybind11을 2.13.6으로 고정

TacEx와 libuipc는 **UniVTAC에 포함된 수정 소스**를 그대로 사용합니다. 공개 TacEx로
바꾸지 않습니다. cuRobo와 vcpkg의 upstream 고정 커밋도 유지합니다.
수정 내용은 `/opt/vla/manifests/univtac-blackwell.patch` 또는
`/workspace/manifests/univtac-blackwell.patch`에 기록됩니다.

**CUDA 버전을 바꾸는 것만으로 모든 네이티브 확장의 호환성이 증명되지는 않습니다.**
오래된 libuipc/MUDA/cuRobo 소스가 CUDA 12.8 또는 sm_120에서 추가 수정이 필요할 수 있습니다.
그 경우 실제 빌드 오류를 보고 후속 수정해야 하며, π0.5·FTP-1 환경에는 영향을 주지 않습니다.

UniVTAC 최신 저장소의 `isaac51`과 FTP-1 내부에 들어 있는 UniVTAC 4.5 기반 평가 코드는
같은 버전이 아닙니다. **FTP-1의 `eval_ftp1_batch.sh`를 5.1 환경에서 바로 실행할 수 있다고
보장하지 않습니다.** 5.1 환경에서 FTP-1 정책을 평가하려면 관측·촉각·상태·행동 형식과
정책 호출 adapter를 연결하는 작업이 별도로 필요합니다. π0.5 평가도 마찬가지입니다.
이 패키지는 저장소 실행 환경을 준비하며, 새 평가 adapter나 정책 이식을 구현하지 않습니다.
4.5용 데이터와 체크포인트를 5.1용으로 자동 변환하지도 않습니다.

## 영속 저장과 서버 설정

- 데이터: `/workspace/data`
- 체크포인트: `/workspace/checkpoints` 또는 `/workspace/runs/<프로젝트>/checkpoints`
- Hugging Face/OpenPI/torch 캐시: `/workspace/.cache`
- 나중에 추가한 conda 환경: `/workspace/conda-envs`
- 긴 작업: tmux 안에서 실행

각 소스 루트의 `checkpoints`가 없을 때만 workspace 경로로 심볼릭 링크를 만듭니다.
그 외 upstream 기본 출력 경로(`eval_result`, `eval_results`, 상대경로 assets 등)는
자동으로 모두 이전하지 않습니다. 실험 config에서 출력 경로를 `/workspace`로 지정하세요.
학교 안내대로 `/workspace`도 백업은 아니며 인스턴스 삭제 후에는 회수 정책을 따릅니다.

GPU 드라이버는 이미지 안에서 설치하거나 변경하지 않습니다. 호스트에 Blackwell과
Isaac Sim 5.1을 지원하는 드라이버 및 NVIDIA Container Toolkit이 필요합니다.
운영진이 GPU 할당과 graphics 드라이버 노출을 설정해야 합니다. SSH 키·WireGuard
프로파일·승인·포트 설정도 운영 시스템이 담당합니다.

## 재현성과 변경 기록

세 저장소의 검토한 커밋은 `config/repos.json`에 고정했습니다. 모델별 원본/수정
pyproject, 최종 `uv.lock`, pip freeze, conda 명시 목록을 빌드 이미지의
`/opt/vla/manifests`에 남깁니다. 모델 버전 공통화보다 저장소별 환경 분리를 우선했습니다.

upstream lock은 CUDA wheel 출처가 바뀌므로 빌드 시 재해결합니다. 따라서 **아직 모든
전이 의존성을 고정한 검증 완료 lock 배포물은 아닙니다.** 첫 성공 빌드 뒤 최종 lock과
이미지 digest를 함께 보관해야 합니다. apt/conda의 전이 패키지와 베이스 이미지 태그도
시간에 따라 달라질 수 있습니다. 처음 성공한 이미지를 두 노드에 동일하게 배포하려면
기존 운영 방식처럼 `docker save`/`docker load`를 사용하면 됩니다.

참고 문서와 저장소는 `SOURCES.md`, 로컬 검증 내역은 `VALIDATION.json`에 있습니다.
