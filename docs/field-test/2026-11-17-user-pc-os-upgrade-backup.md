# User PC OS 업그레이드: 백업, 절차, 바꿀 곳 (22.04 Humble → 24.04 Jazzy)

대상: 현장 User PC `jiwoo-950QDB` (지금 Ubuntu 22.04 + ROS 2 Humble).

> **11/24 갱신.** 메인 User PC를 RTX 5080 PC(처음부터 Ubuntu 24.04 + Jazzy)로 바꿨다. 이 PC에는 업그레이드 절차(4절)가 필요 없다. 7.1·7.2의 코드·설정 변경은 브랜치 `chore/user-pc-jazzy`에 적용했다. 예전 PC를 다시 쓸 때만 4절을 따른다. 3절 백업 목록의 A1·A2·A4·A5는 새 PC로 옮겨야 한다.

**방식: 제자리 업그레이드** (`sudo do-release-upgrade`). 디스크를 지우지 않으므로 홈 폴더, 레포, 녹화 데이터, 설정, 설치한 앱이 그대로 남는다. 다만 도중에 실패하면 새로 설치(디스크 포맷)로 가야 하므로, **백업은 보험으로 반드시 먼저 한다.**

| 절 | 내용 |
|---|---|
| 1 | 업그레이드로 남는 것과 바뀌는 것 |
| 2–3 | 백업 목록과 백업 명령 (실패 대비) |
| 4 | 제자리 업그레이드 절차 (Humble 제거 → 업그레이드 → Jazzy 설치) |
| 5 | 업그레이드 뒤 확인 |
| 6 | 업그레이드가 실패해 새로 설치했을 때 되돌리기 |
| 7 | Jazzy 로 바꿀 때 코드와 설정에서 바꿀 곳 (목록만, 아직 적용하지 않음) |

- 경로는 `feat/control-hub-and-recorder` 브랜치 코드의 기본값과 `.gitignore` 기준이다. 현장 PC 에서 실제로 있는지는 3절 1) 의 `ls` 로 확인한다.
- Robot PC(OMY 컨테이너)는 건드리지 않는다. 로봇 쪽 설정은 그대로 남는다.
- LEAP 모터의 ID 와 baud 는 모터 안(EEPROM)에 있다. PC 를 바꿔도 남는다.

## 1. 업그레이드로 남는 것과 바뀌는 것

| 대상 | 제자리 업그레이드 뒤 | 할 일 |
|---|---|---|
| 홈 폴더 전체 (레포, 녹화 데이터, `.bashrc`, `.ssh`, 앱 설정 `~/.config`) | 그대로 남는다 | 없음 |
| `/etc` 설정 (udev 규칙, USB 랜 공유 모드) | 그대로 남는다 | 없음 |
| apt 로 깐 일반 앱 (Ubuntu 저장소) | 24.04 판으로 같이 올라간다 | 없음 |
| snap 앱 | 영향 없음 | 없음 |
| 외부 저장소 앱 (VSCode, Chrome, Docker 등) | 앱은 남고 실행된다. 단 업그레이드 도구가 **외부 저장소를 꺼 둔다** | 4.4 에서 다시 켠다. 안 켜면 업데이트만 안 된다 |
| ROS 2 Humble | 22.04 전용이라 깨진다 | 4.2 에서 **업그레이드 전에 지운다**, 4.5 에서 Jazzy 설치 |
| Humble 로 빌드한 것 (Manus 워크스페이스) | 쓸 수 없다 | 4.6 에서 다시 빌드 |
| 시스템 Python | 3.10 → 3.12 | `pip install --user` 로 깐 것은 다시 깐다. 녹화기·Hub 의 `.venv` 를 시스템 Python 으로 만들었다면(`python3 -m venv`) 깨진다. 4.6 에서 지우고 다시 만든다 |

## 2. 백업 목록 (실패 대비)

### 2.1 반드시 백업할 것 (다시 만들 수 없거나, 다시 만들면 데이터 기준이 바뀌는 것)

| # | 파일 | 무엇 | 없으면 |
|---|---|---|---|
| A1 | `user_pc/config/hardware_motors*.yaml` (전부) | **LEAP 모터 원점.** 모터별 편 손 자세의 각도(`open_motor_radians`)와 방향(`sign`). `calibrate_motors` 가 만든다. git 에 안 올라간다 | 원점을 다시 잡아야 한다. 다시 잡은 원점이 조금만 달라도 이전 에피소드와 손 관절각 기준이 어긋난다. 11/12 손 교체 뒤 파일이 여러 개일 수 있으니 패턴에 맞는 것을 전부 뺀다 |
| A2 | `user_pc/config/manus_calibration.yaml` | **글러브 보정.** 수집자의 편 손/주먹 값(`leap_glovecal`). git 에 안 올라간다 | 텔레옵이 시작되지 않는다(예시 파일은 dry-run 전용). 다시 찍을 수는 있지만 리타게팅 결과가 이전과 달라진다. 수집자마다 따로 있으면 전부 뺀다 |
| A3 | 녹화 데이터 `~/data/shape_up/` (또는 `rig.yaml` 의 `data_root`) | 에피소드 원본. `ep_NNNN.tmp/` (미저장, 복구 대상) 포함 | 복구 불가 |
| A4 | `recorder/config/rig.yaml` | 녹화기 장치 설정: Paxini `places`, 카메라 `serial`, 실측 `hz`, `latency_ms`, `hand_action` | 현장 확인으로 채운 값을 다시 찾아야 한다 |
| A5 | `control_hub/config/hub.yaml` | Hub 설정 (git 에 안 올라간다). example 에서 현장에 맞게 고친 부분 | example 에서 다시 고쳐야 한다 |
| A6 | 레포의 커밋 안 한 변경, git 에 없는 새 파일, 로컬 브랜치, stash | `git status`, `git stash list`, `git branch -vv` 로 확인. git 에 올라가 있는 설정(`manus_leap.yaml`, `postures.yaml` 등)을 현장에서 고쳐 쓰고 커밋하지 않았다면 여기에 걸린다 | 커밋·push 하거나 3절 3) 처럼 뺀다. stash 가 여러 개면 브랜치로 만들어 둔다 |

### 2.2 백업해 두면 좋은 것 (기록, 또는 다시 설정하는 수고)

| # | 경로 | 무엇 | 비고 |
|---|---|---|---|
| B1 | `~/.local/state/control_hub/sessions/` | Hub 세션 기록과 사고 폴더(`incidents/`) | 현장 문제 추적용 |
| B2 | `~/.local/state/control_hub/logs/` | Hub 가 켠 프로세스 로그 | 같음 |
| B3 | `--log-csv` 로 지정했던 경로 (보통 `user_pc/logs/`, git 제외) | 텔레옵 진단 CSV | 기본 경로가 없는 옵션이라 쓴 자리를 확인한다. 리타게팅 분석에 썼다면 |
| B4 | `~/.bashrc` | `leap_aliases.sh` source, `LEAP_NO_ZENOH=1`, `LEAP_ROS_DISTRO=humble` 등 추가한 줄 | 제자리 업그레이드면 남는다. 4.2 에서 humble 줄만 고친다 |
| B5 | `~/.ssh/` (키 쌍, `config`, `known_hosts`) | Robot PC(`root@10.42.0.241`) 비밀번호 없는 ssh | **같은 키 쌍을 되돌려 두면** 로봇에 다시 등록할 필요가 없다. 권한: 폴더 700, 개인키 600 |
| B6 | `/etc/udev/rules.d/` 중 직접 넣은 것 | Manus 동글(`70-manus-hid.rules`), 만들었다면 LEAP latency timer 규칙 | Manus 규칙은 레포에 있다(`third_party/manus/70-manus-hid.rules`). 직접 만든 규칙만 챙긴다 |
| B7 | `/etc/NetworkManager/system-connections/` 중 USB 랜 연결 | 로봇 쪽 공유 모드(`ipv4.method shared`) | 다시 해도 한 줄이다: `nmcli connection modify "<연결 이름>" ipv4.method shared` |
| B8 | `third_party/manus/MANUS Core Dashboard (Linux build)/` | MANUS 에서 받은 바이너리 (git 제외, 약 213 MB) | 있으면. integrated mode 에는 필요 없다 |
| B9 | `third_party/paxini/runs/`, `*.rrd` | Paxini 뷰어 기록 | 있으면 |

### 2.3 백업하지 않아도 되는 것

| 경로 | 이유 |
|---|---|
| `recorder/.venv`, `control_hub/.venv` | `uv sync` 로 다시 만든다. Python 3.12 고정이라 OS 와 무관하다 |
| `third_party/manus/ROS2 package/{build,install,log}/` | Humble 로 빌드한 것이라 **어차피 Jazzy 로 다시 빌드**해야 한다 |
| zenoh-ros2-sdk 캐시 | 첫 실행 때 다시 받는다 (그때 인터넷 필요) |
| ROS 패키지, librealsense, Cyclo Docker 이미지 | 다시 설치한다 |

## 3. 백업 명령

외장 SSD 를 `/media/$USER/BACKUP` 에 꽂았다고 가정한다. 레포는 `~/SHAPE_UP_Tactile`.

```bash
R=~/SHAPE_UP_Tactile
OUT=/media/$USER/BACKUP/userpc_$(date +%F)
mkdir -p "$OUT"

# 1) 있는지 먼저 본다
ls -la $R/user_pc/config/hardware_motors*.yaml $R/user_pc/config/manus_calibration*.yaml \
       $R/recorder/config/rig.yaml $R/control_hub/config/hub.yaml
du -sh ~/data/shape_up ~/.local/state/control_hub 2>/dev/null
cd $R && git status --short && git stash list && git branch -vv
#    LEAP 5V 를 켜고 편 손 자세로 둔 뒤 관절 각도를 적어 둔다 (토크는 켜지 않는다.
#    5절에서 업그레이드 뒤 값과 비교). leap_check 는 user_pc/ 로 이동한 뒤 실행되므로 경로는 config/...
leap_check --motor-calibration-file config/hardware_motors.yaml | tee "$OUT/leap_check_before.txt"

# 2) 레포 안의 git 에 없는 설정 (A1, A2, A4, A5, B3)
cd $R && tar czf "$OUT/repo_local_config.tgz" --ignore-failed-read \
  user_pc/config/hardware_motors*.yaml user_pc/config/manus_calibration.yaml \
  recorder/config/rig.yaml control_hub/config/hub.yaml user_pc/logs

# 3) 커밋 안 한 것과 로컬 브랜치 (A6): push 가 어려우면 bundle
#    bundle 은 모든 브랜치를 담지만 stash 는 가장 최근 것 하나만 담는다.
#    stash 가 여러 개면 먼저 브랜치로 만들어 둔다: git stash branch <이름> stash@{N}
#    커밋 안 한 변경과 새 파일은 따로 뺀다
git bundle create "$OUT/repo_all_branches.bundle" --all
git diff HEAD > "$OUT/uncommitted.diff"          # staged + unstaged 둘 다
git ls-files --others --exclude-standard -z \
  | tar czf "$OUT/untracked_files.tgz" --null -T -   # git 에 없는 새 파일 (ignore 된 것 제외)

# 4) 녹화 데이터 (A3): 크기가 크면 rsync
rsync -a --info=progress2 ~/data/shape_up/ "$OUT/data_shape_up/"

# 5) 홈과 시스템 설정 (B1, B2, B4, B5)
tar czf "$OUT/home_config.tgz" --ignore-failed-read \
  -C ~ .bashrc .ssh .local/state/control_hub
sudo tar czf "$OUT/etc_config.tgz" --ignore-failed-read \
  /etc/udev/rules.d /etc/NetworkManager/system-connections

# 6) 확인: 열어 보고 개수와 크기가 맞는지
tar tzf "$OUT/repo_local_config.tgz"
diff -rq ~/data/shape_up "$OUT/data_shape_up" && echo "data OK"
```

`home_config.tgz` 와 `etc_config.tgz` 에는 ssh 개인키와 와이파이 비밀번호가 들어 있다. 백업 디스크를 공유 장소에 두지 않는다.

## 4. 제자리 업그레이드 절차

**현장에서, 키보드와 모니터를 붙이고** 한다(ssh 로 원격 업그레이드하지 않는다). 인터넷이 1–2시간 필요하다. 도중에 전원을 끄지 않는다. 노트북이면 전원을 꽂는다.

### 4.1 준비

```bash
# 3절 백업을 마쳤는지 확인한다 (leap_check_before.txt 포함)

# 디스크 여유: 루트(/)에 10 GB 이상 권장
df -h /

# 22.04 를 최신으로 올리고 재부팅
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

### 4.2 Humble 제거

Humble 은 22.04 전용이다. 남겨 두면 업그레이드 도중 의존성 충돌로 멈출 수 있으니 **업그레이드 전에** 지운다.

```bash
# 1) 지금 깔린 Humble 패키지 목록을 남긴다 (4.5 에서 Jazzy 로 같은 것을 깔 때 참고)
dpkg -l 'ros-humble-*' | awk '/^ii/{print $2}' > ~/humble_packages.txt
wc -l ~/humble_packages.txt

# 2) Humble 패키지 전부 제거
sudo apt purge 'ros-humble-*'
sudo apt autoremove --purge

# 3) 남은 폴더 확인 (비어 있거나 없어야 한다)
ls /opt/ros/

# 4) ROS apt 저장소(jammy 용) 끄기
#    ros2-apt-source 패키지로 저장소를 넣었다면 그 패키지를 지운다
#    (안 깔려 있으면 "not installed" 라고만 하고 넘어간다)
sudo apt purge ros2-apt-source
#    남은 ROS 저장소 파일을 찾아 옮겨 둔다 (예: ros2.list). 아무것도 안 나오면 이 단계는 끝
F=$(grep -rl "packages.ros.org" /etc/apt/sources.list.d/); echo "$F"
[ -n "$F" ] && sudo mkdir -p /root/apt-sources-jammy && sudo mv $F /root/apt-sources-jammy/
sudo apt update
```

`~/.bashrc` 에서 Humble 을 가리키는 줄을 고친다. 고치지 않으면 새 터미널을 열 때마다 `/opt/ros/humble/setup.bash: No such file` 이 뜬다.

```bash
grep -n "humble" ~/.bashrc
#    - source /opt/ros/humble/setup.bash  → 주석 처리 (4.5 뒤 jazzy 로 바꾼다)
#    - export LEAP_ROS_DISTRO=humble      → 지우거나 jazzy 로
```

### 4.3 업그레이드

```bash
sudo do-release-upgrade
```

- "No new release found" 가 나오면 `/etc/update-manager/release-upgrades` 의 `Prompt=lts` 인지 확인한다.
- 외부 저장소를 끈다는 안내가 나온다. 그대로 진행한다 (4.4 에서 다시 켠다).
- 설정 파일을 덮어쓸지 물으면 기본값(지금 것 유지)을 고른다.
- "더 이상 지원되지 않는 패키지 제거" 를 물으면 제거해도 된다. ROS 관련 도구는 4.5 에서 다시 깐다.
- 끝나면 재부팅한다. 다시 로그인한 뒤 `lsb_release -a` 가 24.04 인지 확인한다.

### 4.4 외부 저장소 다시 켜기

업그레이드 도구는 외부 저장소를 꺼 둔다. 앱(VSCode, Chrome, Docker 등)은 그대로 실행되지만 업데이트를 받으려면 다시 켠다.

```bash
ls /etc/apt/sources.list.d/
#    꺼진 저장소는 내용이 주석 처리되어 있거나 이름이 바뀌어 있다 ("disabled on upgrade to noble")
```

- "소프트웨어 & 업데이트" → "기타 소프트웨어" 탭에서 체크해서 켜도 된다.
- Docker 처럼 저장소 줄에 배포판 이름(`jammy`)이 들어간 것은 `noble` 로 바꾼다. VSCode(`packages.microsoft.com ... stable main`)처럼 배포판 이름이 없는 것은 켜기만 한다.
- 마지막에 `sudo apt update` 가 오류 없이 끝나는지 본다.

### 4.5 ROS 2 Jazzy 설치

저장소 추가는 공식 문서를 기준으로 한다(docs.ros.org 의 Jazzy "Ubuntu (deb packages)" 설치 문서). 2025 년 이후 공식 방법은 `ros2-apt-source` 패키지다.

```bash
sudo apt install -y software-properties-common curl
sudo add-apt-repository universe
export ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F "tag_name" | awk -F\" '{print $4}')
curl -L -o /tmp/ros2-apt-source.deb \
  "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo ${UBUNTU_CODENAME:-${VERSION_CODENAME}})_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb
sudo apt update && sudo apt upgrade -y

# 이 프로젝트에 필요한 것
#   ros-jazzy-desktop 은 rqt 등 GUI 도구까지 (Humble 때 desktop 을 썼으면 이것, 아니면 ros-jazzy-ros-base)
sudo apt install -y ros-jazzy-desktop ros-dev-tools \
  ros-jazzy-rmw-zenoh-cpp ros-jazzy-dynamixel-sdk ros-jazzy-realsense2-camera python3-serial

# Humble 때 깔았던 나머지가 있는지 비교 (Jazzy 에 없는 패키지는 오류가 난다. 필요한 것만 골라 깐다)
sed 's/^ros-humble-/ros-jazzy-/' ~/humble_packages.txt | sort > /tmp/want.txt
dpkg -l 'ros-jazzy-*' | awk '/^ii/{print $2}' | sort > /tmp/have.txt
comm -23 /tmp/want.txt /tmp/have.txt     # Humble 에는 있었고 Jazzy 에는 아직 없는 것
```

`~/.bashrc` 에서 4.2 때 주석 처리한 줄을 `source /opt/ros/jazzy/setup.bash` 로 바꾼다. 새 터미널에서 `echo $ROS_DISTRO` 가 `jazzy` 인지 확인한다.

### 4.6 프로젝트 쪽

```bash
cd ~/SHAPE_UP_Tactile

# Manus ROS 2 워크스페이스를 Jazzy 로 다시 빌드 (Humble 빌드 결과는 지운다)
cd "third_party/manus/ROS2 package"
rm -rf build install log
source /opt/ros/jazzy/setup.bash
colcon build
cd ~/SHAPE_UP_Tactile

# 녹화기와 Hub 의 venv 를 새로 만든다 (Python 3.10 으로 만든 venv 는 깨지므로 지우고 다시)
#   uv 가 없으면: curl -LsSf https://astral.sh/uv/install.sh | sh
cd ~/SHAPE_UP_Tactile/recorder
rm -rf .venv
uv sync --extra ui --extra arm --extra tactile --extra camera
uv pip install -e ../third_party/paxini          # Paxini SDK 는 venv 안에 설치
cd ~/SHAPE_UP_Tactile/control_hub
rm -rf .venv
uv sync
```

녹화기 extras 는 `docs/data_preparation/recorder_usage.md` 의 "버전을 맞춰 설치" 명령과 같다. 24.04 에서는 시스템 Python 에 `pip install` 이 막힌다(`externally-managed-environment`). 그래서 Paxini SDK 도 venv 안에 넣는다.

그다음 7.1 의 설정 변경(`hub.yaml` 의 `LEAP_ROS_DISTRO=humble` 두 줄)을 적용하고 `control_hub/` 에서 `uv run control-hub validate --config config/hub.yaml`.

## 5. 업그레이드 뒤 확인

| 확인 | 통과 기준 |
|---|---|
| `ls user_pc/config/hardware_motors.yaml` | 원점 파일(A1)이 제자리에 있다. 텔레옵은 이 경로를 기본으로 읽는다 |
| `leap_check --motor-calibration-file config/hardware_motors.yaml` | 모터 16개 응답. `leap_check` 는 원점 파일을 기본으로 읽지 않으므로 옵션으로 준다. 편 손 자세에서 `leap_check_before.txt` 의 값과 비교한다 |
| Manus 노드 + 글러브 착용 후 `leap_manus --dry-run` | `manus_calibration.yaml` 을 읽고 `[teleop] live` |
| 세 패키지 pytest: `recorder/` 와 `control_hub/` 에서 각각 `uv run --extra dev pytest -q`, `user_pc/` 에서 `env -u PYTHONPATH python3 -m pytest -q` | 모두 통과. control_hub 는 tmux 가 있어야 34개 시험이 skip 되지 않는다. lerobot 이 없으면 recorder 1개 skip 은 정상 |
| 녹화기 venv 에서(`cd recorder && source .venv/bin/activate`) `tactile-rec inspect <에피소드>` | 옛 에피소드가 열린다 |
| zenoh 를 켠 셸(`unset LEAP_NO_ZENOH; leap_env`)에서 `ros2 topic echo /joint_states --once` | Robot PC 팔 값이 온다 (Humble 에서 0개였던 것이 풀렸는지). zenohd 와 팔 bringup 이 떠 있어야 한다 |
| `leap_leader` | leader 트리거에 LEAP 이 반응한다 |
| VSCode 등 외부 저장소 앱 | 실행되고, `sudo apt update` 가 오류 없이 끝난다 |

## 6. 업그레이드가 실패해 새로 설치했을 때 되돌리기

제자리 업그레이드가 끝나지 않거나 부팅이 안 되면 24.04 를 새로 설치(디스크 포맷)한다. 이때는 홈 폴더가 지워지므로 3절 백업으로 되돌린다.

아래에서 `<백업>` 은 3절에서 만든 폴더(`userpc_<날짜>`)다. 새 OS 에서는 외장 SSD 가 붙은 경로가 다를 수 있으니 직접 확인한다.

1. 레포를 받고 브랜치를 맞춘다. push 하지 못한 브랜치가 있었으면 `git fetch <백업>/repo_all_branches.bundle '+refs/heads/*:refs/remotes/backup/*'` 로 가져온다. 커밋 안 한 변경은 `git apply <백업>/uncommitted.diff`, 새 파일은 `tar xzf <백업>/untracked_files.tgz` 로 되돌린다.
2. 레포 설정을 같은 자리에 푼다: `cd ~/SHAPE_UP_Tactile && tar xzf <백업>/repo_local_config.tgz`
3. `~/.ssh` 를 되돌리고 권한을 맞춘다(`chmod 700 ~/.ssh; chmod 600 ~/.ssh/id_*`). `ssh root@10.42.0.241 true` 가 비밀번호 없이 되는지 본다.
4. `~/.bashrc` 는 통째로 덮지 말고, 백업에서 우리가 넣은 줄만 옮긴다. `LEAP_ROS_DISTRO=humble` 은 `jazzy` 로 바꾸거나 지운다.
5. 녹화 데이터를 `rig.yaml` 의 `data_root` 자리로 되돌린다.
6. 앱(VSCode 등)과 일반 도구(tmux, uv)를 다시 설치한다. Manus udev 규칙, `dialout` 그룹, USB 랜 공유 모드도 다시 한다.
7. 4.5(Jazzy 설치)와 4.6(프로젝트 쪽)을 그대로 한다.
8. 5절로 확인한다.

## 7. Jazzy 로 바꿀 때 바꿔야 할 것 (11/24 `chore/user-pc-jazzy` 에 적용)

지금 코드는 Humble 현장 PC 기준 그대로 둔다. 아래는 업그레이드할 때 바꿀 곳의 목록이다. 줄 번호는 `feat/control-hub-and-recorder` 의 파일 기준이다. 현장 `hub.yaml` 은 example 에서 고쳐 쓴 파일이라 줄 번호가 다를 수 있으니 같은 키(`envs.teleop` 등)를 찾는다.

### 7.1 반드시 바꿀 것 (안 바꾸면 실행이 안 된다)

| 파일 | 위치 | 지금 | 바꿀 것 | 이유 |
|---|---|---|---|---|
| `control_hub/config/hub.example.yaml` 과 현장 `hub.yaml` | 29줄 `envs.teleop` | `export LEAP_ROS_DISTRO=humble ... LEAP_NO_ZENOH=1` | `humble` → `jazzy` (또는 이 export 를 빼서 `leap_aliases.sh` 기본값 `jazzy` 를 쓴다) | `/opt/ros/humble` 이 없어져 Manus 노드, 텔레옵, 카메라 노드가 바로 실패한다 |
| 같음 | 36줄 `envs.teleop_zenoh` | `export LEAP_ROS_DISTRO=humble ...` | 같음 | `leap_leader` 가 실패한다 |
| 현장 PC `~/.bashrc` | 가이드대로 넣은 줄 | `export LEAP_ROS_DISTRO=humble`, `source /opt/ros/humble/setup.bash` | `jazzy` 또는 삭제 (4.2, 4.5) | 새 터미널마다 오류, 직접 `leap_env` 할 때 같은 문제 |
| Manus ROS 2 워크스페이스 | `third_party/manus/ROS2 package/` | Humble 로 빌드한 `build/install/log` | 세 폴더를 지우고 Jazzy 에서 colcon build (4.6) | 코드 변경은 없다. 소스와 ROS 무관한 `libManusSDK` 라 다시 빌드만 하면 된다 (24.04 + Jazzy 동작은 개발 PC 에서 확인함) |

### 7.2 고치면 좋은 것 (안내 문구, 기능에는 영향 없음)

| 파일 | 위치 | 지금 | 바꿀 것 |
|---|---|---|---|
| `control_hub/config/hub.example.yaml` | 27줄 주석 | "Humble, zenoh 끔" | "Jazzy, zenoh 끔" |
| 같음 | 55줄 hint | `sudo apt install ros-humble-dynamixel-sdk` | `ros-jazzy-dynamixel-sdk` |
| `recorder/src/tactile_rec/streams/arm_zenoh.py` | 맨 위 설명 1–5줄 | "User PC 의 Humble rmw_zenoh 가 못 받아서 SDK 로 직접 붙는다" | 이유가 과거형이 된다. 우회가 필수가 아니라 "ROS 없는 venv 를 유지하려고 쓴다"로 고친다. 동작 코드는 그대로 |
| `docs/manus_teleop_guide.md` | 94, 101, 136, 265줄 | `LEAP_ROS_DISTRO=humble`, `ros-humble-*` 설치 명령 | Jazzy 판으로 |
| 같음 | 135, 558, 573줄 | Humble↔Jazzy 불통 설명 | "해결됨 (User PC Jazzy 업그레이드)" 로 |
| `user_pc/README.md` | 26줄 | "이 PC 는 Ubuntu 22.04 + ROS 2 Humble" | 24.04 + Jazzy |
| 같음 | 48줄 | `pip install -e ".[dev,hardware]"` | 24.04 시스템 Python 에서는 막힌다. `PYTHONPATH` 방식(`leap_env`)만 안내 |
| `docs/manus_teleop_guide.md` | 280줄 | `pip install -e .../third_party/paxini` | 녹화기 venv 안에서 설치하도록 |

### 7.3 바꾸지 않는 것

| 대상 | 이유 |
|---|---|
| 녹화기 코드 `recorder/` | ROS 를 쓰지 않는다. 팔은 zenoh-ros2-sdk 로 Robot PC 라우터에 직접 붙으므로 User PC 의 ROS 버전과 무관하다. `.python-version` 3.12 고정. 업그레이드 뒤 venv 만 다시 만든다 (4.6) |
| Control Hub 코드 `control_hub/` | ROS 없음, 3.12 고정. 설정 파일만 7.1 처럼 바꾼다 |
| 텔레옵 코드 `user_pc/src/` | 원래 24.04 + Jazzy 에서 만들고 검증한 코드다(10/09). `leap_aliases.sh` 기본값도 이미 `jazzy` |
| `LEAP_NO_ZENOH` 구분 (`envs.teleop` / `teleop_zenoh`) | 유지한다. 로봇 없이 손만 쓰는 실행표(`hand_only`)에서 zenoh 를 켜면 Robot PC 라우터 접속에 실패한다(11/03 `bad_alloc`). 바뀌는 것은 Humble 때문에 꺼 두던 이유가 사라진다는 것뿐이다 |
| Python 용 Manus SDK (`cpython-310` 바이너리) | 3.10 전용이지만 우리 코드에서 import 하지 않는다 |
| Robot PC | 원래 Jazzy |

### 7.4 업그레이드로 새로 되는 것 (확인 대상)

모두 User PC 셸이 zenoh 를 켠 상태(`LEAP_NO_ZENOH` 없음)일 때의 이야기다. 지금처럼 `LEAP_NO_ZENOH=1` 로 띄운 노드는 Robot PC 와 통신하지 않는다.

- User PC 의 ROS 로 Robot PC 팔 토픽을 직접 받는다 (`ros2 topic echo /joint_states --once`). 타입 해시가 양쪽 모두 `RIHS01_...` 로 같아지기 때문이다.
- `leap_leader` (leader 트리거 → LEAP) 가 이 PC 에서 동작한다(`envs.teleop_zenoh`). 10/09 검증은 Jazzy PC 에서 한 것이다.
- Cyclo(Jazzy 컨테이너)에서 User PC 의 손·카메라 토픽이 보인다. 단 Manus 노드, 텔레옵, 카메라 노드를 zenoh 를 켠 환경으로 띄워야 한다. 11/12 의 "DDS 로 통일" 후보는 필요 없어진다.
- Python 3.12 라 openpi 의 Python 조건(≥3.11)을 만족한다. 변환기를 User PC 에서 돌리려면 openpi 가 고정한 lerobot 설치까지 따로 확인해야 한다.

## 체크리스트

백업 (3절)
- [ ] A1 LEAP 모터 원점 `hardware_motors*.yaml`
- [ ] A2 글러브 보정 `manus_calibration.yaml`
- [ ] A3 녹화 데이터 `data_root` (`.tmp` 포함)
- [ ] A4 `recorder/config/rig.yaml`
- [ ] A5 `control_hub/config/hub.yaml`
- [ ] A6 커밋 안 한 변경, git 에 없는 새 파일, 로컬 브랜치, stash
- [ ] 업그레이드 전 `leap_check` 결과 (`leap_check_before.txt`)
- [ ] B1–B9 (해당하는 것)
- [ ] 백업 디스크에서 파일 목록과 데이터 diff 확인

업그레이드 (4절)
- [ ] 4.1 22.04 최신화, 재부팅, 디스크 여유
- [ ] 4.2 Humble 목록 저장 → 제거 → ROS 저장소 끄기 → `.bashrc` humble 줄 처리
- [ ] 4.3 `do-release-upgrade`, 재부팅, 24.04 확인
- [ ] 4.4 외부 저장소 다시 켜기 (VSCode, Docker 등)
- [ ] 4.5 Jazzy 설치, `.bashrc` 를 jazzy 로
- [ ] 4.6 Manus 재빌드, 녹화기·Hub venv 새로 만들기, 7.1 설정 변경, `control-hub validate`
- [ ] 5절 확인 전부
