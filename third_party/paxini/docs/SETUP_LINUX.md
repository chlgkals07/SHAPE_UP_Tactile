# Linux / WSL 실행 명령어 및 작업 기록

이 문서는 이 프로젝트의 Linux/WSL 실행 방법, 센서 연결 시 주의사항,
확인 결과와 자주 쓰는 터미널 명령어를 모아 두는 문서다.
앞으로 프로젝트에서 확인한 중요한 내용과 재사용할 명령어도 여기에 추가한다.

## 1. 센서 연결 순서 — 센서를 먼저, USB는 마지막

**USB 전원이 분리된 상태에서 센서를 통신보드에 먼저 연결하고, 그 다음 보드의 USB를 랩탑에 연결한다.**

1. 실행 중인 센서 프로그램을 종료한다(`Ctrl+C`).
2. 보드의 USB를 빼서 전원을 끈다.
3. 사용할 센서를 모두 통신보드에 연결한다. 센서를 교체하거나 추가할 때도 이 순서를 따른다.
4. 보드 USB를 랩탑에 연결한다.
5. Windows에서 `usbipd list`로 BUSID를 확인하고 WSL에 `attach`한다.
6. WSL에서 센서 목록과 포인트 수를 확인한 다음 데이터를 수신한다.

이번 장비에서는 전원이 켜진 채 센서를 교체했을 때 이전 센서의 52포인트 정보가 남았고,
스트리밍 시작이 `0x07` 오류로 실패했다. USB 전원을 완전히 분리한 뒤
센서를 연결한 상태에서 다시 켜자 새 센서의 25포인트가 정상 조회됐다.
이 결과만으로 `0x07`의 일반적인 의미를 단정하지는 않는다.

## 2. 확인한 환경과 장비

2026-11-12 작업 기준이며, 장치를 옮기거나 재연결하면 BUSID와 포트는 바뀔 수 있다.

| 항목 | 확인 값 |
| --- | --- |
| 프로젝트 경로 | `/home/sehwa/paxini-sdk` |
| WSL 배포판 | `Ubuntu-20.04`, WSL 2 |
| Python | 3.13.9, 프로젝트 전용 `.venv` |
| 통신보드 | High-Speed Communication Board, 저장소 표기 `PXSR-STDOTO4B` |
| 펌웨어 | `ADAPTER_FW02.26` |
| USB VID:PID | `28e9:018a` |
| Windows 포트 / BUSID | `COM3` / `2-3` |
| Linux 포트 | `/dev/ttyACM0` |
| USB 전달 도구 | usbipd-win 5.3.0 |

센서 모델은 보드에서 읽은 포인트 수를 SDK 레지스트리와 대조해 판단한다.
`Index-Tip`, `Middle-Tip` 등은 보드가 보고하는 모듈 이름이며 센서 제품명과 구분한다.

## 3. 최초 설치

### WSL 터미널 — Python 환경

```bash
cd /home/sehwa/paxini-sdk
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test,viz]'
```

이 환경에는 설치를 완료했다. 매번 설치할 필요는 없다.
`viz`는 시각화용 선택 의존성이며, CLI와 테스트만 필요하면 `.[test]`로 설치한다.
Ubuntu에서 venv 생성이 불가능하면 사용하는 Python 버전에 맞는 venv 패키지를 설치한다.

### Windows PowerShell — USB 전달 도구

```powershell
winget install --interactive --exact --id dorssel.usbipd-win
usbipd list
```

설치 중 Windows 관리자 승인 창이 나타날 수 있다.
`usbipd list`에서 보드의 BUSID를 확인한 뒤 **관리자 PowerShell**에서 공유 등록한다.
아래 `2-3`은 이번 작업에서 확인한 값이다.

```powershell
usbipd bind --busid 2-3
```

이미 `Shared` 상태라면 다시 bind할 필요는 없다.
공식 절차: [Microsoft WSL USB 연결 안내](https://learn.microsoft.com/en-us/windows/wsl/connect-usb).

## 4. 매번 연결하거나 센서를 교체한 뒤 실행할 명령어

### Windows PowerShell

WSL 터미널을 열어 둔 상태에서 실행한다.

```powershell
usbipd list
usbipd attach --wsl --busid 2-3
usbipd list
```

최종 상태가 `Attached`인지 확인한다. USB를 뺐다 꽂거나 WSL을 재시작하면
다시 attach해야 한다. BUSID가 바뀌면 실제 조회한 값으로 바꾼다.
`attach`에는 관리자 PowerShell이 필요하지 않다.

설치 직후 PATH에 `usbipd`가 없다면 다음처럼 실행하거나 PowerShell을 새로 연다.

```powershell
& 'C:\Program Files\usbipd-win\usbipd.exe' list
& 'C:\Program Files\usbipd-win\usbipd.exe' attach --wsl --busid 2-3
```

WSL 터미널에서 Windows 도구를 직접 호출할 수도 있다.

```bash
'/mnt/c/Program Files/usbipd-win/usbipd.exe' list
'/mnt/c/Program Files/usbipd-win/usbipd.exe' attach --wsl --busid 2-3
```

### WSL 터미널 — 포트 확인 및 짧은 수신

```bash
cd /home/sehwa/paxini-sdk
source .venv/bin/activate
lsusb
paxini list
paxini info --port /dev/ttyACM0
paxini-smoke --port /dev/ttyACM0 --duration 5
```

`paxini-smoke`는 펌웨어, 활성 모듈, 모듈별 포인트 수와 합력을 출력하고
지정한 시간 동안 스트리밍한다. `active modules`와 각 모듈의 포인트 수를 확인한다.
센서가 여러 개여도 터미널 스트리밍 출력은 기본적으로 첫 모듈에 집중한다.

## 5. 센서 모델과 모듈 목록만 조회

WSL에서 프로젝트 가상환경을 활성화한 뒤 실행한다. 모델 확인을 위해
스트리밍이나 영점 보정을 시작하지 않아도 된다.

```bash
python - <<'PYCODE'
from paxini_sdk import HighSpeedHandBoard, registers, sensor_registry

with HighSpeedHandBoard('/dev/ttyACM0') as board:
    print('Firmware:', board.read_version())
    cfg = board.read_auto_push_config()
    print('Active sensors:', len(cfg.active_modules))
    for module in cfg.active_modules:
        points = cfg.point_counts.get(module, 0)
        variant = sensor_registry.find_by_point_count(points)
        print(registers.MODULE_NAMES[module], points,
              variant.sensor_model if variant else 'Unknown',
              variant.vendor_part_code if variant else 'Unknown')
PYCODE
```

## 6. 자주 사용하는 데이터 명령어

### 30초 수신 / 특정 모듈 표시

```bash
paxini-smoke --port /dev/ttyACM0 --duration 30
paxini-smoke --port /dev/ttyACM0 --duration 30 --module Index-Tip
paxini-smoke --port /dev/ttyACM0 --duration 30 --module Index-Middle
```

`--module`에는 현재 조회된 모듈 이름을 넣는다. 위 두 모듈 명령어는
각각 순서대로 실행하며, 동시에 같은 포트를 여는 프로그램은 하나만 사용한다.

### 영점 보정 후 수신

센서에 힘을 가하지 않은 상태에서 실행한다.

```bash
paxini-smoke --port /dev/ttyACM0 --duration 10 --calibrate
```

### CSV 기록

```bash
paxini-record --port /dev/ttyACM0 --out runs/session1.csv --duration 30
```

`runs/`는 자동 생성된다. 기존 파일을 덮어쓰지 않도록 세션마다 다른 파일명을 사용한다.
기간을 지정하지 않으면 `Ctrl+C`로 종료할 때까지 기록한다.

### 실시간 시각화

WSL 그래픽 드라이버 오류가 있으면 웹 뷰어를 사용한다.

```bash
env -u PYTHONPATH .venv/bin/paxini-rerun --port /dev/ttyACM0 --web-viewer
```

터미널에 출력되는 `http://localhost:9090/?url=...` 전체 주소를 **Windows의
Chrome 또는 Edge**에서 연다. 웹 화면은 9090, 데이터 서버는 9876 포트를 사용한다.
이 모드는 WSL 네이티브 그래픽 창을 생성하지 않고 브라우저에서 렌더링한다.
`viz` 의존성이 필요하며, 구버전 Rerun에 웹 API가 없으면 CLI가 업데이트 방법을 안내한다.
이번 환경의 Rerun은 `0.43.1`이다. `Ctrl+C`로 수신과 서버를 종료한다.
`--duration 30`을 추가하면 30초 후 센서 수신을 끝내고 웹 뷰어는 `Ctrl+C`까지 유지한다.
2026-11-12 사용자가 DP·IP 각 1개를 연결한 구성에서 이 웹 뷰어 실행 방법으로
시각화가 동작한다고 확인했다. 프레임 수·수신 속도와 센서별 힘 반응은 별도로 확인하지 않았다.

구현은 `paxini_sdk/tools/to_rerun.py`에 있다. 모듈별 Fx/Fy/Fz 합력 그래프와
Fz에 따라 색·크기가 바뀌는 3D 측정점 표시, CSV 재생을 지원한다.
실시간 모드는 각 모듈의 포인트 수로 센서 좌표를 개별 선택하며, 센서별로
3D 분포와 합력 그래프를 나눠 표시하도록 구성했다. DP·IP 혼합 구성에서는
`--sensor-part`를 생략해 자동 판별한다. CSV 재생의 혼합 센서 처리는 별도 미검증이다.

기본 네이티브 뷰어는 WSLg 등 그래픽 환경이 필요하다.

```bash
paxini-rerun --port /dev/ttyACM0
```

사용자 실행 로그에서 네이티브 뷰어가 `R32Float` 렌더링 지원 부족으로 종료됐다.
투명 창·클립보드 경고 뒤에 나온 GPU 오류가 종료 원인이며, 이후 gRPC 오류는
뷰어 종료에 따른 연결 단절이다. [Rerun 공식 문제 해결 안내](https://rerun.io/docs/getting-started/install-rerun/troubleshooting)는
WSL 그래픽 드라이버 문제와 웹 뷰어 사용 방법을 설명한다.

### 테스트 및 의존성 검사

이 WSL 셸은 ROS의 Python 경로를 포함하므로 검사할 때 해당 경로를 제외한다.

```bash
env -u PYTHONPATH .venv/bin/python -m pytest -q
env -u PYTHONPATH .venv/bin/python -m pip check
```

확인 결과: `52 passed`, `No broken requirements found`.
SDK 명령어에서도 ROS 등 다른 Python 환경과 충돌하면 같은 방식으로 실행한다.

```bash
env -u PYTHONPATH .venv/bin/paxini-smoke --port /dev/ttyACM0 --duration 5
```

### 장치를 Windows로 돌려주기

WSL의 센서 프로그램을 종료한 뒤 Windows PowerShell에서 실행한다.

```powershell
usbipd detach --busid 2-3
```

WSL에 연결된 동안에는 Windows 센서 앱이 같은 장치를 사용할 수 없다.

## 7. 문제별 점검

| 증상 | 점검 및 조치 |
| --- | --- |
| USB 재연결 후 Linux 포트가 없음 | Windows `usbipd list` 확인 후 다시 `attach` |
| 펌웨어는 읽히지만 활성 센서 0개 | USB 전원을 빼고 센서–보드 케이블 연결을 확인한 다음 USB 연결 → attach → 재조회 |
| 교체 전 센서 정보가 남거나 스트리밍 `0x07` 오류 | USB 전원을 완전히 분리하고 새 센서를 연결한 상태에서 다시 시작 |
| 센서 2개 중 1개만 조회 | 각 센서를 단독 확인하고 두 센서를 연결한 상태에서 전원을 다시 켜서 조회; 주소 중복 여부는 별도 확인 필요 |
| 포트 접근 권한 없음 | 포트 소유 그룹과 현재 사용자의 그룹 확인 |
| 테스트에 ROS 플러그인이 섞임 | 위 `env -u PYTHONPATH` 검사 명령 사용 |
| 뷰어가 `R32Float` 지원 부족으로 종료 | `--web-viewer`로 실행하고 출력 URL을 Windows Chrome/Edge에서 열기 |

Linux 포트 및 권한 점검 명령:

```bash
ls -l /dev/ttyACM* /dev/ttyUSB* /dev/serial/by-id/* 2>/dev/null
id
```

현재 사용자는 `dialout` 그룹 소속이다. 다른 Ubuntu 계정에서 포트 그룹이
`dialout`인데 접근 권한이 없다면 다음 명령 후 새 로그인 세션을 시작한다.

```bash
sudo usermod -aG dialout "$USER"
```

USB는 보이지만 시리얼 포트가 없다면 `sudo dmesg | tail -50`으로 드라이버
오류를 확인한다. 네이티브 Linux에서는 Windows USB 전달 단계가 필요 없다.

## 8. 확인 기록

### 2026-11-12 — WSL 설치 및 센서 교체 확인

- SDK, pyserial, pytest, rerun-sdk를 `.venv`에 설치하고 usbipd-win으로 보드를 연결했다.
- 펌웨어 `ADAPTER_FW02.26`과 Linux 포트 `/dev/ttyACM0`를 확인했다.
- DP-S2015-Elite 단독 연결: `Middle-Tip`, 52포인트, 5초간 455~456프레임(약 91 Hz) 수신.
- IP-S1610-Elite 단독 연결: `Middle-Middle`, 25포인트, 5초간 456프레임(약 91 Hz) 수신.
- 전원 인가 중 센서 교체 후 이전 정보가 남는 현상을 확인했고, USB 전원 재연결 후 정상화됐다.
- 일부 연결 시도에서는 센서 0개 또는 두 센서 중 1개만 보였다. 해당 시도의 원인은 확정하지 않았다.
- 마지막 조회에서는 아래 두 센서가 함께 인식됐다. 이 구성은 모델·포인트 수 조회까지 확인했으며,
  두 센서의 동시 스트리밍은 아직 검증하지 않았다.

| 마지막 조회 모듈 | 센서 모델 | 부품 코드 | 포인트 수 |
| --- | --- | --- | ---: |
| `Index-Middle` | IP-S1610-Elite | `PXSR-STDIP03B` | 25 |
| `Index-Tip` | DP-S2015-Elite | `PXSR-STDDP03G` | 52 |

### 2026-11-12 — Rerun GPU 오류 및 웹 뷰어 추가

- 사용자 제공 로그: `ADAPTER_FW02.26`, `/dev/ttyACM0`, 활성 모듈
  `Index-Middle`·`Index-Tip` 조회 성공 후 네이티브 뷰어가 `R32Float` 지원 부족으로 종료됐다.
- 코드 검토: 첫 활성 센서의 25점 좌표를 모든 센서에 재사용해 DP 측정점이 잘리는 문제를 확인했다.
  실시간 모드를 모듈별 좌표 판별과 별도 보기로 수정했다.
- `--web-viewer`를 추가하고 네이티브 창 없이 웹·데이터 서버를 실행하도록 했다.
  `Ctrl+C` 종료 시 최상위에서 인터럽트를 처리하고 연결을 닫는다.
- 검증: 임시 단일 프레임 CSV로 웹 서버 HTTP 200, CSV 재생 완료, SIGINT 종료 코드 0 확인.
  DP 52점·IP 25점 좌표 선택 및 잘못된 좌표 강제 지정 거부, 웹 모드 동작 회귀 검사를 포함해
  `env -u PYTHONPATH .venv/bin/python -m pytest -q` 결과 `56 passed`.
- 당시 에이전트 실행 환경에는 `/dev/ttyACM0`가 없어 실제 장치로 실행하지 않았다.
  이후 사용자 실행 확인은 아래 기록에 구분해 남긴다.

### 2026-11-12 — 사용자 웹 시각화 동작 확인

- 연결 구성: DP·IP 센서 각 1개. 앞선 조회에서 `Index-Middle`(IP, 25점)과
  `Index-Tip`(DP, 52점)이 인식된 구성이다.
- 안내한 실행 명령어:

  ```bash
  env -u PYTHONPATH .venv/bin/paxini-rerun --port /dev/ttyACM0 --web-viewer
  ```

- 실행 방법: 출력되는 `http://localhost:9090/?url=...` 전체 주소를 Windows Chrome/Edge에서 열기.
- 확인 결과: 사용자가 위 안내 후 웹 시각화가 동작한다고 보고했다.
  네이티브 뷰어의 `R32Float` 오류를 우회하는 실행 방법으로 확인됐다.
- 미확인: 실제 수신 프레임 수·속도, 각 센서를 눌렀을 때의 개별 힘 반응, 장시간 안정성.

### 2026-11-12 — CSV 수신 주파수 및 설정 지원 확인

- 사용자 보고: CSV로 측정한 데이터 주파수가 약 89.9 Hz였다. 계산 방식과 원본 CSV는 이번 확인에서 검토하지 않았다.
- 코드 확인: 현재 High-Speed 보드 SDK는 auto-push 활성화/비활성화를 지원하지만,
  전송 주파수(Hz)를 지정하는 API나 `paxini-record` 옵션은 없다. 기록 루프는 수신한 프레임마다 CSV에 기록한다.
- 약 90 Hz는 앞서 단독 센서에서 관측한 약 91 Hz와 비슷한 수준이다.
  보드 내부 측정 주파수와 호스트 수신 주파수가 같은지는 검증하지 않았다.
- 처리·저장 주파수를 낮추는 것은 호스트에서 프레임을 선택하거나 시간 기준으로 재표본화하여 구현 가능하다.
  이는 보드의 측정·전송 주파수 변경과 구분한다. 현재 기록 CLI에는 해당 옵션도 없다.
- `--baud`는 시리얼 통신 설정이며 Hz 지정 옵션이 아니다. 펌웨어에서 실제 전송 주파수 변경을
  지원하는지, 약 90 Hz 이상으로 높일 수 있는지는 제조사 프로토콜·펌웨어 확인이 필요하다.

## 9. 앞으로 기록할 내용

재사용할 명령어는 관련 절에 추가하고, 새로운 확인 결과는 아래 형식으로
`확인 기록`에 날짜별로 추가한다. 확인한 결과와 추정, 아직 확인하지 않은 항목을 구분한다.

```text
### YYYY-MM-DD — 작업 내용
- 목적 / 변경한 연결 구성:
- 보드 펌웨어 / 포트 / BUSID:
- 센서 모델 / 모듈 / 포인트 수:
- 실행한 명령어:
- 확인 결과(프레임 수, 속도, 오류 등):
- 남은 문제 / 다음 확인:
```
