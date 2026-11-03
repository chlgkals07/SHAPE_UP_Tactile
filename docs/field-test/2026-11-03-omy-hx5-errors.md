# 2026-11-03 OMY + HX5-D20 bringup 오류 기록

이 문서는 오늘 Robot PC 터미널에서 나온 오류와 후속 성공 로그를 구분한다. 손은
OMY 기존 그리퍼 4핀 케이블에 연결했다. 아래의 END 경유 읽기와 Preset 손가락
움직임은 실물에서 확인했지만, Direct Mode의 20관절 텔레옵은 아직 실행하지 않았다.

## 결론

`/dev/ttyAMA4`에서 손 ID 140으로 **직접** ping했을 때 무응답이었던 사실만으로
손의 전원·모터 고장을 결론낼 수 없었다. 같은 포트에서 OMY END 보드 ID 210은
응답했고, END의 Tool ID·TableSync 창을 이용하면 손 140과 모터 141이
응답했다. 따라서 이번 배선의 소프트웨어 경로는 `Robot PC → END 210 → HX5
140 → 내부 모터`로 잡아야 한다. 이전 직결 손 드라이버가 140 및 146 등 내부
ID를 직접 찾던 방식은 이 경로에 맞지 않았다.

## 관측된 오류와 처리

| 터미널 출력 | 의미와 확인 결과 | 처리 |
| --- | --- | --- |
| `Could not find robotis_interfacesConfig.cmake` | 최초 overlay에 공식 `robotis_interfaces` 메시지 패키지가 없었다. 손의 통신 실패와 별개인 빌드 의존성 오류다. | `robotis_interfaces` Jazzy 소스를 `/workspace/omy_ws/src`에 추가한 뒤 `colcon build --packages-up-to omy_hx5_bringup`이 성공했다. |
| `ModuleNotFoundError: No module named 'serial'` | END 진단 프로그램이 쓰는 `dynamixel_sdk`의 Python 시리얼 의존성이 컨테이너에 없었다. | 컨테이너에서 `apt-get install -y python3-serial` 후 같은 진단 명령이 실행됐다. |
| `Package 'omy_hx5_bringup' not found` | 당시 셸의 ROS 검색 경로에 `/workspace/omy_ws/install`이 없었다. 빌드 실패라는 뜻은 아니다. | `source /opt/ros/jazzy/setup.bash`, `source /root/ros2_ws/install/setup.bash`, `source /workspace/omy_ws/install/setup.bash` 후 `ros2 pkg prefix omy_hx5_bringup`이 설치 경로를 출력했다. 새 터미널마다 source가 필요하다. |
| 호스트 셸의 `ros2: command not found` | Yocto 호스트에서 ROS 컨테이너에 들어가지 않고 명령했다. | 호스트의 `/data/docker/open_manipulator`에서 `./docker/container.sh enter` 후 컨테이너에서 ROS 명령을 실행했다. |
| ID 210 ping 성공, ID 140 직접 ping `There is no status packet!` | `/dev/ttyAMA4`는 END 보드가 앞에 있는 포트다. 직접 ping은 손의 간접 경로를 검사하지 못한다. | `omy_hx5_end_proxy_probe`로 END 210을 경유해 손 140을 읽었다. |
| `END proxy probe failed: hand is not idle Direct Control Mode: mode=1, TableSync Enable=0` | 첫 `--inspect-sync-ids` 검사가 손의 정상적인 Preset Mode 1도 차단했다. 검사 코드의 조건이 지나치게 좁았다. | mode 1에서도 **읽기 전용 TableSync ID 검사**를 허용하도록 수정했다. 재검사에서 ID `[141, 142, 143, 144, 145]`가 나왔고 임시 간접 주소가 복원됐다. |
| `END 210 write 60/13 failed: There is no status packet!` | Direct 준비 중 END의 EEPROM 설정 쓰기 응답이 누락됐다. 손 ID 140의 무응답을 뜻하지 않는다. 첫 실패 뒤에는 기존 OMY 값으로 돌아왔지만 다음 실패 뒤 실측은 Tool ID 1, TableSync Enable 0, Read Address 1 = 0, Read Size 1 = 24, Write Size 1/2 = 0이었다. END 210 ping은 다시 성공했다. 복원 코드가 한 항목에서 실패하면 나머지를 건너뛰는 결함을 확인했다. | END 쓰기 응답 누락 시 읽기 재확인과 전체 설정 복원 검증을 추가했다. `omy_hx5_end_recover --apply`로 기존 OMY END 설정 복원이 실물에서 확인됐다. Direct 준비 중 END EEPROM 쓰기를 줄이도록 20모터 감사를 한 세션으로 묶었다. Direct 20관절 동작은 아직 확인하지 않았다. 응답 누락 원인은 미확정이다. |
| `All 20 HX5 actuators identified` 뒤 `END restoration incomplete; TableSync left off; END write buffer differs` | 20모터 ID·설정 검사는 통과했다. 다음 손 Direct 설정을 마치고 END 복원 단계에서 버퍼 비교가 실패했다. 직후 읽기에서 END의 저장 설정은 기존 OMY 값이고 TableSync만 0이었다. 손의 Direct Mode 적용 여부는 아직 읽어 확인하지 않았다. | 기존 코드는 비활성 버퍼 영역까지 128바이트 전체가 같아야 복원으로 판정했다. 기존 OMY에서 실제 전송되는 12바이트만 복원·검증하도록 수정했다. 실물 재검증 전에는 손 런치를 실행하지 않는다. |
| `--verify-direct`에서 `HX5 Bus Watchdog is not 100` 뒤 실제 값 `255` | 손 Direct Mode 0 검사는 통과했다. Watchdog 255는 공식 제어표의 오류 값 -1로, 손 TableSync의 통신 감시가 중단된 상태다. 언제 이 값으로 바뀌었는지는 미확정이다. | 손 TableSync가 꺼진 상태에서 Watchdog 0만 써서 오류를 해제하는 별도 명령을 추가했다. 준비·종료 시 유휴 Watchdog를 0으로 두고 Direct 세션 중에만 100으로 설정하도록 수정했다. 실물 재검증은 아직 하지 않았다. |
| `--clear-watchdog`에서 `mode=0, TableSync=0, status=1, watchdog=170`, 뒤이어 `END TableSync could not be disabled` | `170`은 공식 HX5 Bus Watchdog 유효 범위 밖이어서 이 END 경유 손 읽기를 손의 확정 상태로 해석할 수 없다. 준비 명령은 손 쓰기를 시작하기 전에 중단했으나 END 복원도 실패했다. 이후 END 210 직접 읽기에서 Tool ID 140, TableSync 0, 읽기 주소 8·크기 1, 쓰기 크기 0으로 남은 것이 확인됐다. 이전 `255` 읽기도 재검증이 필요하다. | 기본 OMY END 설정이 실물에서 다시 검증됐다. Direct 읽기에는 손 Realtime Tick을 END 두 번째 슬롯으로 받아 갱신을 확인하도록 수정했다. END TableSync 복원은 지연된 읽기값을 재확인한다. 변경 후 실물 `--diagnose` 전에는 Direct 런치를 하지 않는다. 이 상태만으로 손 하드웨어 결함이나 실제 입력 전압 오류를 단정하지 않는다. |
| BASE ID 200 검사에서 Python SDK `setBaudRate(6250000)` 실패 | Python DYNAMIXEL SDK의 속도 허용 목록에 OMY BASE의 6.25 Mbps가 없어 SDK 단계에서 거부됐다. BASE 전원 오류의 증거가 아니다. | pyserial이 지원하는 사용자 지정 속도를 허용한 읽기 전용 검사에서 BASE 200 모델 220 응답과 `Power Enable(512)=1`을 확인했다. |
| Direct 실패 후 손은 느슨하지만 END 경유 손 전압 `23.77 V`, 상태 `0`, 모터 141 `torque=0` | 손 컨트롤러 전원과 기본 통신은 살아 있다. 손이 느슨한 직접 원인 중 하나는 모터 토크가 꺼진 것이다. 나머지 19개 모터 토크와 손 모드·watchdog는 아직 확인하지 않았다. | Direct 준비 코드는 20개 모터 토크가 이미 켜져 있기를 요구하지만 토크를 켜는 단계가 없다. 이 상태에서 Direct 명령을 반복하거나 모터 141만 토크를 켜지 않는다. 손 상태를 작은 읽기 창으로 검사하는 `omy_hx5_end_proxy_probe --hand-state`를 추가했다. 실물 재검증 전이다. |
| 작은 읽기 창의 손 상태 진단 | 모드 0, TableSync 0, watchdog 0, tick `10989→12217` 증가, 입력 23.77 V, 상태 0을 실물에서 확인했다. 따라서 앞선 107바이트·두 슬롯 조합의 `tick stayed at 0`은 손 전원 단절의 증거가 아니다. | Direct의 손 읽기를 첫 번째 END 슬롯의 16바이트 단위로 나누고, 같은 슬롯에서 tick 전후 값을 읽도록 변경했다. 이후 실물 `--diagnose`가 통과했다. |
| 수정된 `--diagnose` 통과 후 20모터 검사 중단 | 실물에서 손 ID 140·모드 0·watchdog 0·tick 15493·23.77 V·상태 0을 읽었다. END의 Tool Status는 1이었으나 공식 문서가 값 1의 세부 의미를 명시하지 않는다. 20개 모터는 모두 모델 1710, 모드 5, 하드웨어 오류 0, 공식 영점·간접 주소와 일치했지만 모두 `Torque Enable=0`이었다. Drive Mode는 공식 Xacro와 bit 3만 다르며, 현재 값에서는 Goal 갱신만으로 토크가 자동 활성화되지 않는다. | Direct 준비의 기존 토크 1 선행 조건에서 중단됐다. 손이나 모터 목표값은 보내지 않았다. 안전한 토크 초기화 전에 모터 watchdog·현재 위치·목표 위치를 읽도록 엄지 첫 모터 진단에 항목을 추가했다. |
| 모터 141 시작 상태 | 모터 141에서 watchdog 0, Goal Current 300, Goal Position 1530, Present Position 1530, 오류 0, torque 0을 읽었다. 이 값만으로 나머지 19개 모터의 상태를 추정하지 않는다. | END를 경유해 각 모터의 상태를 모두 검사하고 현재 위치를 목표 위치로 설정한 뒤 시작 전류 100·토크 1을 쓰는 별도 명령을 구현했다. 실물 쓰기 결과는 아직 없다. |
| 첫 토크 활성화 명령 중 END 응답 길이 불일치 | 손 상태 읽기에서 END ID 210의 16바이트 응답을 요청했지만 Python SDK가 성공 코드와 함께 3바이트만 돌려줬다. 이 단계는 모터 목표·토크 쓰기보다 앞이므로 이번 호출은 모터 토크를 켜지 않았다. 같은 호출의 END 복원 검증은 비정상 값들을 냈지만 새 포트의 읽기 전용 검사에서는 Tool ID 140, TableSync 0, 나머지 레지스터가 기본값으로 확인됐다. | Tool ID 140·TableSync 0·나머지 기본값인 중단 상태를 END 복구 명령에서 허용했다. 복구 쓰기 전 설정을 두 번 읽어 일치하는지 확인하고, Python SDK의 다음 요청 전 늦은 수신 패킷을 비우도록 토크·복구 포트를 보강했다. 실물 재검증 전까지 토크 명령을 반복하지 않는다. |
| `[ID:146] Rebooting...`와 `COMM_ERROR ... There is no status packet!` 반복, 종료 시 SIGTERM/SIGKILL | 이전 직결 `DynamixelHardware`가 내부 ID를 직접 접근·재부팅하려다 응답을 못 받아 반복한 로그다. 출력의 `Rebooting`은 **재부팅 명령 시도**를 나타내며, 실제 모터 재부팅 성공을 입증하지 않는다. 종료 중에도 재시도가 계속돼 런치가 강제 종료했다. | 해당 실물 직결 런치는 계속 차단한다. 새 실물 경로는 손을 END 210으로 접근하는 별도 노드를 사용한다. |
| `/joint_states`에 `joint1..6`만 있고 `/left_hand/finger_pressures`·손 trajectory 토픽이 없음 | 그때는 팔 컨트롤러와 END Preset 노드가 실행 중이었다. Preset 경로는 공식 20관절 컨트롤러나 촉각 broadcaster를 실행하지 않는다. 이 사실만으로 Zenoh 라우터 고장을 단정할 수 없다. | Direct Mode 노드에서 손 관절·압력 토픽을 발행하도록 구현했다. 실물 토픽 확인은 다음 연결 때 필요하다. |

명령을 붙여 넣을 때 `git submodule update --init third_party/robotis_handcd ...`처럼
두 명령이 합쳐진 사례도 있었다. 이 경우 `outside repository`가 나왔으며
저장소나 손 하드웨어의 결함은 아니었다. Robot PC 호스트의
`/data/docker/open_manipulator`와 컨테이너의 `/workspace/omy_ws`도 서로 다른
경로다.

SSH의 `No route to host`는 User PC의 OMY 직결 이더넷 인터페이스가 연결되지
않았을 때 발생했다. 이후 인터페이스 `10.42.0.1/24`와 OMY 주소
`10.42.0.241`로 향하는 직접 경로가 확인됐고 IP SSH 접속에 성공했다.
`SNPR44B1050` 같은 이름의 DNS/mDNS 조회 실패는 IP 경로 문제와 구분한다.

## 오류 이후 실물에서 확인한 값

| 대상 | END 210 경유 결과 |
| --- | --- |
| END 보드 | ID 210, 모델 230 |
| HX5 왼손 컨트롤러 | ID 140, 모델 261, 입력 약 23.68–23.70 V, 상태 0, Preset Mode 1 |
| TableSync1 대상 | `[141, 142, 143, 144, 145]` 읽기 성공 |
| 엄지 첫 모터 | ID 141, 모델 1710, Operating Mode 5, torque 1, 간접 주소 1/2 = 126/127 |
| Preset 경로 | `omy_hx5_end_preset`의 준비 로그 후 `/omy_hx5/preset_percent` 명령에 검지가 실제 움직인 것을 사용자가 확인 |

모터 141의 Drive Mode 실측 `5`와 공식 왼손 Xacro의 `13`은 bit 3 차이다.
이는 목표값 갱신 시 자동 토크 활성화 설정이다. 현재 토크 1과 Preset 동작
사실만으로 나머지 19모터 설정이 같다고 추정하지 않는다. 새 Direct Mode
준비 명령은 20모터를 전부 읽고 공식 Xacro와 대조한다.

## 다음 연결 때의 검증 경계

1. [END Direct Mode 준비](../hx5-d20-omy-direct-hand.md#2-손-direct-mode-준비)에서 20모터 설정 점검과 5채널 TableSync 설정을 완료한다. 이 단계는 목표 관절값을 보내지 않는다.
2. 공식 키보드로 한 손가락의 작은 동작부터 실측한다. 손 관절·촉각 토픽의 실제 갱신과 물리 움직임을 함께 확인한다.
3. [리더 방아쇠 텔레옵](../hx5-d20-omy-teleop.md#3-팔-추종-없이-손-드라이런)은 손 브리지 드라이런부터 시작한다. `hand_dry_run:=true`는 손 명령 발행을 멈추지만 팔 텔레옵을 자동으로 막지는 않는다.

이 기록의 원인은 당시 로그와 후속 END 경유 성공 결과에 근거한다. 종단저항
상태나 순간적인 통신 품질까지 배제한 실물 전기 진단은 아니다.
