# OMY + D435i 2대 시연 데이터 수집 실행표

## 실행 주기

- **최초 1회:** A1–A4. 카메라 위치·일련번호·소프트웨어가 바뀌면 해당 단계만 다시 수행한다.
- **수집 세션마다:** B1–B6, B8–B10. PC·로봇을 켠 후 실행한다.
- **첫 세션 또는 카메라·토픽 구성이 바뀐 세션:** B7을 수행한다.
- **에피소드마다:** C1을 반복한다.
- **수집 세션 종료 시:** D1–D2를 수행한다.

첫 수집 순서: **A1 → A2 → A3 → A4 → B1 → B2 → B3 → B4 → B5 → B6 → B7 → B8 → B9 → B10 → C1 → D1 → D2**.

이후 수집 순서: **B1 → B2 → B3 → B4 → B5 → B6 → B8 → B9 → B10 → C1 반복 → D1 → D2**. 카메라·토픽 구성이 바뀌었다면 B6 다음에 B7을 다시 수행한다.

# A. 최초 1회 설정

## A1 · 장비 장착·배선

- [ ] OMY-F3M 팔로워와 OMY-L100 리더를 고정하고 전원·케이블을 연결한다.
- [ ] OMY 손목 카메라의 `Camera` 포트를 USER PC에 연결한다.
- [ ] D435i #1을 작업대 정면에 고정하고 USER PC의 USB 3 포트 A에 연결한다. 카메라와 케이블에 `front` 라벨을 붙인다.
- [ ] D435i #2를 작업대 측면에 고정하고 USER PC의 USB 3 포트 B에 연결한다. 카메라와 케이블에 `side` 라벨을 붙인다.
- [ ] 카메라 3대의 화면에 그리퍼, 물체, 목표 위치가 들어오게 각도와 거리를 조정하고 케이블을 로봇 이동 범위 밖에 고정한다.
- [ ] 최초 수령 후 포장 자세라면 ROBOTIS OMY Setup Guide의 unpacking 절차를 완료한다.

## A2 · USER PC · OpenMANIPULATOR 준비와 일련번호 확인

USER PC 호스트에서:

```bash
lsusb -t
cd ~
git clone -b jazzy https://github.com/ROBOTIS-GIT/open_manipulator.git
cd ~/open_manipulator
./docker/container.sh start
./docker/container.sh enter
```

이미 `~/open_manipulator`가 있으면 `git clone`을 생략하고 해당 디렉터리에서 `./docker/container.sh start`를 실행한다.

USER PC의 OpenMANIPULATOR 컨테이너에서:

```bash
rs-enumerate-devices -S
ros2 pkg prefix realsense2_camera
ros2 pkg prefix compressed_image_transport
```

- [ ] `rs-enumerate-devices -S`에서 손목 카메라와 D435i 두 대를 구별하고 각 Serial Number를 적는다.
- [ ] `lsusb -t`에서 D435i 두 대가 USB 3 SuperSpeed 경로에 연결되었는지 확인한다.
- [ ] `compressed_image_transport`가 없다면 아래 명령을 컨테이너에서 실행한 뒤 다시 확인한다.

```bash
apt-get update
apt-get install -y ros-jazzy-compressed-image-transport
ros2 pkg prefix compressed_image_transport
```

컨테이너에서 나와 USER PC 호스트로 돌아간다.

```bash
exit
```

## A3 · USER PC · 공통 환경 파일 생성

USER PC 호스트에서 ROBOT PC의 IP를 확인한 다음, **실제 ROBOT PC IP와 카메라 3대의 Serial Number**를 입력한다. `hostname -I`가 여러 주소를 표시하면 USER PC에서 접속 가능한 주소를 고른다. 손목 카메라가 RealSense가 아니면 이 실행표의 손목 카메라 명령 대신 해당 장치의 실행 명령을 사용한다.

```bash
read -rp 'OMY 호스트 이름(omy-...local): ' OMY_ROBOT_HOST
ssh root@"$OMY_ROBOT_HOST" hostname -I
read -rp 'ROBOT PC IP: ' OMY_ROBOT_IP
read -rp '손목 카메라 Serial Number: ' OMY_WRIST_SN
read -rp '정면 D435i Serial Number: ' OMY_FRONT_SN
read -rp '측면 D435i Serial Number: ' OMY_SIDE_SN

mkdir -p ~/open_manipulator/workspace
cat > ~/open_manipulator/workspace/omy_env.sh <<EOF
export OMY_ROBOT_IP='$OMY_ROBOT_IP'
export OMY_WRIST_SN='$OMY_WRIST_SN'
export OMY_FRONT_SN='$OMY_FRONT_SN'
export OMY_SIDE_SN='$OMY_SIDE_SN'
export ROS_DOMAIN_ID=30
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_CONFIG_OVERRIDE='transport/shared_memory/enabled=true;mode="client";connect/endpoints=["tcp/$OMY_ROBOT_IP:7447"]'
EOF
cat ~/open_manipulator/workspace/omy_env.sh
```

- [ ] 출력된 IP와 Serial Number 3개가 실제 장치와 일치한다.
- [ ] 로봇에 별도의 `ROS_DOMAIN_ID`가 설정되어 있다면 환경 파일의 값과 ROBOT PC의 값을 동일하게 맞춘다.

## A4 · USER PC · Cyclo Intelligence 설치

USER PC 호스트의 **새 터미널**에서:

```bash
curl -fsSL https://raw.githubusercontent.com/ROBOTIS-GIT/cyclo_intelligence/main/install.sh | bash
cd ~/cyclo_intelligence
./docker/container.sh start
```

이미 `~/cyclo_intelligence`가 있으면 설치 명령을 생략한다. 업데이트는 필요할 때 별도로 진행한다.

# B. 수집 세션마다 실행

- [ ] 세 카메라의 장착 위치·USB 연결·케이블 고정 상태를 확인한다.
- [ ] A3의 `omy_env.sh`에 저장된 ROBOT PC IP와 세 일련번호가 현재 장비와 같은지 확인한다.
- [ ] 로봇 작업영역을 비우고 전원을 켠다.

## B1 · ROBOT PC · 터미널 A · Zenoh 시작

USER PC 터미널에서:

```bash
read -rp 'OMY 호스트 이름(omy-...local): ' OMY_ROBOT_HOST
ssh root@"$OMY_ROBOT_HOST"
```

ROBOT PC 호스트에서 USER PC와 통신 가능한 IP를 확인한다.

```bash
hostname -I
cd /data/docker/open_manipulator
./docker/container.sh start
./docker/container.sh enter
export ROS_DOMAIN_ID=30
echo "$ROS_DOMAIN_ID"
zenohd
```

**터미널 A는 종료하지 않는다.** `hostname -I`의 IP가 A3 환경 파일과 다르면 USER PC에서 `nano ~/open_manipulator/workspace/omy_env.sh`를 열어 `OMY_ROBOT_IP`와 `ZENOH_CONFIG_OVERRIDE` 안의 IP를 모두 수정한다. B8에서 Cyclo용 복사본을 갱신한다.

## B2 · ROBOT PC · 터미널 B · 텔레오퍼레이션 시작

USER PC의 **새 터미널**에서:

```bash
read -rp 'OMY 호스트 이름(omy-...local): ' OMY_ROBOT_HOST
ssh root@"$OMY_ROBOT_HOST"
cd /data/docker/open_manipulator
./docker/container.sh enter
export ROS_DOMAIN_ID=30
```

- [ ] 팔로워의 이동 범위에서 사람·물체·카메라 케이블을 치운다.
- [ ] 아래 명령은 팔로워를 즉시 움직일 수 있다. 비상 정지 수단을 확인하고 실행한다.

```bash
ros2 launch open_manipulator_bringup omy_ai.launch.py
```

- [ ] 초기 위치 이동, 리더 중력 보상, 리더·팔로워 동기화가 끝날 때까지 기다린다.
- [ ] 리더를 조금 움직여 팔로워가 예상대로 따라오는지 확인한다.
- [ ] 터미널 B를 종료하지 않는다. 추론용 팔로워 bringup을 동시에 실행하지 않는다.

## B3 · USER PC · 터미널 U1 · 손목 카메라 시작

USER PC의 **새 터미널**에서:

```bash
cd ~/open_manipulator
./docker/container.sh start
./docker/container.sh enter
source /workspace/omy_env.sh
ros2 launch realsense2_camera rs_launch.py \
  camera_namespace:=camera camera_name:=cam_wrist \
  serial_no:=_"${OMY_WRIST_SN}"
```

터미널 U1을 종료하지 않는다. 기존에 일련번호 없이 실행 중인 손목 카메라 노드가 있으면 먼저 종료한다.

## B4 · USER PC · 터미널 U2 · 정면 D435i 시작

USER PC의 **새 터미널**에서:

```bash
cd ~/open_manipulator
./docker/container.sh enter
source /workspace/omy_env.sh
ros2 launch realsense2_camera rs_launch.py \
  camera_namespace:=camera camera_name:=cam_front \
  serial_no:=_"${OMY_FRONT_SN}" \
  enable_color:=true enable_depth:=true \
  rgb_camera.color_profile:=640x480x30 \
  depth_module.depth_profile:=640x480x30
```

터미널 U2를 종료하지 않는다.

## B5 · USER PC · 터미널 U3 · 측면 D435i 시작

USER PC의 **새 터미널**에서:

```bash
cd ~/open_manipulator
./docker/container.sh enter
source /workspace/omy_env.sh
ros2 launch realsense2_camera rs_launch.py \
  camera_namespace:=camera camera_name:=cam_side \
  serial_no:=_"${OMY_SIDE_SN}" \
  enable_color:=true enable_depth:=true \
  rgb_camera.color_profile:=640x480x30 \
  depth_module.depth_profile:=640x480x30
```

터미널 U3을 종료하지 않는다.

## B6 · USER PC · 터미널 U4 · 토픽 확인

USER PC의 **새 터미널**에서:

```bash
cd ~/open_manipulator
./docker/container.sh enter
source /workspace/omy_env.sh
ros2 node list | grep -E 'cam_wrist|cam_front|cam_side'
ros2 topic list -t | grep -E 'cam_(wrist|front|side).*(color|depth|camera_info)'
ros2 topic echo /joint_states --once
```

- [ ] 손목·정면·측면 RGB의 실제 `/compressed` 토픽을 적는다.
- [ ] 정면·측면의 `depth/image_rect_raw`와 `color/camera_info`, `depth/camera_info` 토픽을 적는다.
- [ ] RGB 압축 토픽 형식은 `sensor_msgs/msg/CompressedImage`, 깊이 원본 형식은 `sensor_msgs/msg/Image`인지 확인한다.

실제 발행 토픽이 아래 예시와 일치할 때만 다음 명령을 실행한다. 다르면 `ros2 topic list -t`에 나온 경로로 바꾼다.

```bash
ros2 topic hz /camera/cam_front/color/image_raw/compressed
ros2 topic hz /camera/cam_side/color/image_raw/compressed
ros2 topic hz /camera/cam_front/depth/image_rect_raw
ros2 topic hz /camera/cam_side/depth/image_rect_raw
```

각 `ros2 topic hz` 명령은 측정 후 `Ctrl+C`로 종료한다. 터미널 U4는 계속 사용할 수 있다.

## B7 · 첫 세션/카메라·토픽 변경 시 · OMY-F3M 수집 설정 편집

USER PC 호스트에서:

```bash
cd ~/cyclo_intelligence/shared/shared/robot_configs
cp omy_f3m_config.yaml omy_f3m_config.yaml.bak
nano omy_f3m_config.yaml
```

A4에서 Cyclo를 설치한 뒤, 기존 `orchestrator → ros__parameters → omy_f3m` 아래의 `observation.images`를 다음처럼 만든다. **B6에서 확인한 실제 RGB 압축 토픽으로** `topic` 값을 바꾼다. 기존 `observation.state`, `action`, `urdf_path`는 유지한다.

```yaml
      observation:
        images:
          cam_wrist:
            topic: /camera/cam_wrist/color/image_rect_raw/compressed
            msg_type: sensor_msgs/msg/CompressedImage
          cam_front:
            topic: /camera/cam_front/color/image_raw/compressed
            msg_type: sensor_msgs/msg/CompressedImage
          cam_side:
            topic: /camera/cam_side/color/image_raw/compressed
            msg_type: sensor_msgs/msg/CompressedImage
```

기존 `recording.extra_topics` 목록에 아래 카메라 보정 토픽과 깊이 원본 토픽을 넣는다. **B6에서 확인한 실제 토픽으로** 경로를 바꾼다. 깊이 데이터를 저장하지 않으려면 `depth/...` 네 줄은 생략한다.

```yaml
      recording:
        extra_topics:
          - /tf
          - /camera/cam_wrist/color/camera_info
          - /camera/cam_front/color/camera_info
          - /camera/cam_side/color/camera_info
          - /camera/cam_front/depth/image_rect_raw
          - /camera/cam_front/depth/camera_info
          - /camera/cam_side/depth/image_rect_raw
          - /camera/cam_side/depth/camera_info
```

- [ ] YAML에서 `observation.images`와 `recording.extra_topics`가 각각 **한 번만** 나온다.
- [ ] 세 RGB 압축 토픽과 두 깊이 원본 토픽의 경로를 실제 `ros2 topic list -t` 결과에 맞췄다.
- [ ] `nano`에서 `Ctrl+O` → `Enter` → `Ctrl+X`로 저장한다.

## B8 · USER PC · 터미널 U5 · Cyclo Intelligence 실행

USER PC 호스트에서:

```bash
mkdir -p ~/cyclo_intelligence/docker/workspace
cp ~/open_manipulator/workspace/omy_env.sh ~/cyclo_intelligence/docker/workspace/omy_env.sh
cd ~/cyclo_intelligence
./docker/container.sh start
./docker/container.sh enter
source /workspace/omy_env.sh
ros2 topic list | grep -E 'joint_states|cam_wrist|cam_front|cam_side'
cyclo_intelligence
```

터미널 U5를 종료하지 않는다. USER PC 브라우저에서 `http://localhost:7080/`을 연다.

## B9 · 매 세션 · 시험 에피소드

1. `Home` → 로봇 유형 `OMY F3M` 선택.
2. `Record` → `Camera Views`에서 손목·정면·측면 세 장면 확인.
3. `Record` → `Topic Monitor`에서 세 RGB 압축 토픽, 관절 토픽, 두 깊이 토픽의 수신·Hz 확인.
4. `Rosbag Recorder`에 `Task Num`, `Task Name`, `Task Instruction` 입력.
5. 단계별 레이블이 필요 없으면 `Number of SubTasks = 0`.
6. 물체와 팔을 시작 상태에 놓고 `Record Start` 클릭.
7. 리더 팔로 짧은 동작을 시연한 뒤 `Save Episode` 클릭. 실패 시 `Discard Episode` 클릭.

## B10 · 매 세션 · 시험 기록 확인

USER PC의 **새 터미널**에서:

```bash
cd ~/cyclo_intelligence
./docker/container.sh enter
find /workspace/rosbag2 -maxdepth 2 -type d
```

실제 데이터셋 폴더와 에피소드 번호를 확인한 다음(`실제_데이터셋_폴더`를 교체):

```bash
ros2 bag info /workspace/rosbag2/실제_데이터셋_폴더/0/
ls -R /workspace/rosbag2/실제_데이터셋_폴더/0/
```

- [ ] `episode_info.json`, `metadata.yaml`, `*.mcap`, `videos/`가 있다.
- [ ] `videos/`에 손목·정면·측면 영상/타임스탬프 파일이 있다.
- [ ] 깊이를 선택했다면 `ros2 bag info`에 정면·측면 깊이 토픽과 0보다 큰 메시지 수가 보인다.
- [ ] 깊이 원본은 보조 MCAP 토픽이다. 현재 Cyclo의 LeRobot 영상 변환 결과는 세 RGB 관측을 대상으로 한다.

# C. 에피소드마다 반복

## C1 · 브라우저 · 본 시연 녹화

1. 물체와 팔을 정해 둔 시작 상태에 놓는다.
2. `Record → Camera Views`에서 손목·정면·측면 영상이 보이는지 확인한다.
3. `Rosbag Recorder`의 `Task Num`, `Task Name`, `Task Instruction`이 이번 작업과 맞는지 확인한다.
4. `Record Start` 클릭 → 리더 팔 조작 → 성공하면 `Save Episode`, 실패하면 `Discard Episode` 클릭.
5. 다음 시도 전에 물체·팔의 시작 상태를 다시 맞춘다.

# D. 수집 세션 종료 시

## D1 · 브라우저 · 데이터 검수·변환

1. `Data Tools → Review Episodes`에서 각 에피소드의 세 카메라 영상, 관절 동작, 지시문, 타임라인을 재생·확인한다.
2. 불량 에피소드의 인덱스를 적고 `Delete Episodes`에서 삭제한다.
3. 같은 작업을 여러 폴더로 기록했다면 `Merge Rosbag Datasets`로 병합한다.
4. `Convert Dataset`에서 실제 영상 토픽 Hz 이하의 FPS를 설정하고 `LeRobot v2.1` 또는 `v3.0`을 선택해 변환한다.
5. USER PC 호스트의 `~/cyclo_intelligence/docker/workspace/lerobot/`에서 결과를 확인한다.

## D2 · 프로세스 종료

1. 녹화가 끝났는지 확인한다.
2. 카메라 터미널 U1·U2·U3에서 각각 `Ctrl+C`.
3. 텔레오퍼레이션 터미널 B에서 `Ctrl+C`.
4. Cyclo 터미널 U5에서 `Ctrl+C`.
5. 마지막으로 Zenoh 터미널 A에서 `Ctrl+C`.

