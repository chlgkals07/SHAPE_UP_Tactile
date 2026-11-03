# 2026-11-03 OMY + HX5-D20 bringup 오류 기록

이 문서는 **2026-11-03 현장 시험**에서 사용자가 대화에 붙여 넣은 Robot PC·User PC
터미널 출력과 후속 성공 로그를 정리한 것이다. 손은 OMY 기존 그리퍼 4핀 케이블에
연결했다. 아래의 `관측`은 실제 터미널 출력 또는 사용자의 육안 보고, `해석`은 그
증거에서 가능한 결론, `후속`은 코드 변경·재검사 결과를 뜻한다. 명령의 성공 출력만으로
실제 손 움직임을 대신하지 않는다. **Preset 동작, Direct 손 상태·촉각 토픽 수신,
첫 작은 jog의 손 움직임**까지 실물에서 확인했다. 전체 20관절 키보드·리더 방아쇠
텔레옵은 아직 실물 실행으로 검증하지 않았다.

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
| `END 210 write 60/13 failed: There is no status packet!` | Direct 준비 중 END의 EEPROM 설정 쓰기 응답이 누락됐다. 손 ID 140의 무응답을 뜻하지 않는다. 첫 실패 뒤에는 기존 OMY 값으로 돌아왔지만 다음 실패 뒤 실측은 Tool ID 1, TableSync Enable 0, Read Address 1 = 0, Read Size 1 = 24, Write Size 1/2 = 0이었다. END 210 ping은 다시 성공했다. 복원 코드가 한 항목에서 실패하면 나머지를 건너뛰는 결함을 확인했다. | END 쓰기 응답 누락 시 읽기 재확인과 전체 설정 복원 검증을 추가했다. `omy_hx5_end_recover --apply`로 기존 OMY END 설정 복원이 실물에서 확인됐다. Direct 준비 중 END EEPROM 쓰기를 줄이도록 20모터 감사를 한 세션으로 묶었다. 이후 첫 작은 Direct jog은 움직였으나 전체 20관절 텔레옵은 미검증이다. 응답 누락의 전기적 원인은 미확정이다. |
| `All 20 HX5 actuators identified` 뒤 `END restoration incomplete; TableSync left off; END write buffer differs` | 20모터 ID·설정 검사는 통과했다. 다음 손 Direct 설정을 마치고 END 복원 단계에서 버퍼 비교가 실패했다. 직후 읽기에서 END의 저장 설정은 기존 OMY 값이고 TableSync만 0이었다. 당시 손 Direct 적용 여부는 확인되지 않았다. | 기존 코드는 비활성 버퍼 영역까지 128바이트 전체가 같아야 복원으로 판정했다. 기존 OMY에서 실제 전송되는 12바이트만 복원·검증하도록 수정했다. 후속 검사에서 Direct Mode 0과 END 기본 설정을 확인했다. |
| `--verify-direct`에서 `HX5 Bus Watchdog is not 100` 뒤 실제 값 `255` | 손 Direct Mode 0 검사는 통과했다. Watchdog 255는 공식 제어표의 오류 값 -1에 해당할 수 있지만, 뒤에 범위 밖 값 170도 읽혀 당시 큰 프록시 창의 신뢰성이 낮았다. 언제 실제 watchdog 오류가 있었는지는 미확정이다. | 손 TableSync가 꺼진 상태에서 Watchdog 0만 써서 해제하는 명령을 추가했다. 준비·종료 시 유휴 Watchdog를 0으로 두고 Direct 세션 중에만 100으로 설정하도록 수정했다. 후속 작은 창 진단에서 유휴 0, 활성 검사에서 100을 확인했다. |
| `--clear-watchdog`에서 `mode=0, TableSync=0, status=1, watchdog=170`, 뒤이어 `END TableSync could not be disabled` | `170`은 공식 HX5 Bus Watchdog 유효 범위 밖이어서 이 END 경유 손 읽기를 손의 확정 상태로 해석할 수 없다. 준비 명령은 손 쓰기를 시작하기 전에 중단했으나 END 복원도 실패했다. 이후 END 210 직접 읽기에서 Tool ID 140, TableSync 0, 읽기 주소 8·크기 1, 쓰기 크기 0으로 남은 것이 확인됐다. 이전 `255` 읽기도 재검증이 필요하다. | 기본 OMY END 설정이 실물에서 다시 검증됐다. Direct 읽기에는 손 Realtime Tick을 END 두 번째 슬롯으로 받아 갱신을 확인하도록 수정했다. END TableSync 복원은 지연된 읽기값을 재확인한다. 변경 후 실물 `--diagnose` 전에는 Direct 런치를 하지 않는다. 이 상태만으로 손 하드웨어 결함이나 실제 입력 전압 오류를 단정하지 않는다. |
| BASE ID 200 검사에서 Python SDK `setBaudRate(6250000)` 실패 | Python DYNAMIXEL SDK의 속도 허용 목록에 OMY BASE의 6.25 Mbps가 없어 SDK 단계에서 거부됐다. BASE 전원 오류의 증거가 아니다. | pyserial이 지원하는 사용자 지정 속도를 허용한 읽기 전용 검사에서 BASE 200 모델 220 응답과 `Power Enable(512)=1`을 확인했다. |
| Direct 실패 후 손은 느슨하지만 END 경유 손 전압 `23.77 V`, 상태 `0`, 모터 141 `torque=0` | 손 컨트롤러 전원과 기본 통신은 살아 있었다. 손이 느슨한 직접 원인 중 하나는 모터 토크가 꺼진 것이다. 뒤의 20모터 검사에서 모두 torque 0으로 확인됐다. | 손 상태를 작은 읽기 창으로 읽는 진단을 추가했다. 이후 20모터 토크를 각각 안전하게 켜고 읽기 검증했다. |
| 작은 읽기 창의 손 상태 진단 | 모드 0, TableSync 0, watchdog 0, tick `10989→12217` 증가, 입력 23.77 V, 상태 0을 실물에서 확인했다. 따라서 앞선 107바이트·두 슬롯 조합의 `tick stayed at 0`은 손 전원 단절의 증거가 아니다. | Direct의 손 읽기를 첫 번째 END 슬롯의 16바이트 단위로 나누고, 같은 슬롯에서 tick 전후 값을 읽도록 변경했다. 이후 실물 `--diagnose`가 통과했다. |
| 수정된 `--diagnose` 통과 후 20모터 검사 중단 | 실물에서 손 ID 140·모드 0·watchdog 0·tick 15493·23.77 V·상태 0을 읽었다. END의 Tool Status는 1이었으나 공식 문서가 값 1의 세부 의미를 명시하지 않는다. 20개 모터는 모두 모델 1710, 모드 5, 하드웨어 오류 0, 공식 영점·간접 주소와 일치했지만 모두 `Torque Enable=0`이었다. Drive Mode는 공식 Xacro와 bit 3만 다르며, 현재 값에서는 Goal 갱신만으로 토크가 자동 활성화되지 않는다. | Direct 준비의 기존 토크 1 선행 조건에서 중단됐다. 손이나 모터 목표값은 보내지 않았다. 안전한 토크 초기화 전에 모터 watchdog·현재 위치·목표 위치를 읽도록 엄지 첫 모터 진단에 항목을 추가했다. |
| 모터 141 시작 상태 | 모터 141에서 watchdog 0, Goal Current 300, Goal Position 1530, Present Position 1530, 오류 0, torque 0을 읽었다. 이 값만으로 나머지 19개 모터의 상태를 추정하지 않았다. | END를 경유해 각 모터의 상태를 검사하고 현재 위치를 목표 위치로 설정한 뒤 시작 Goal Current 100·torque 1을 쓰는 별도 명령을 구현했다. 뒤에 개별 모터 쓰기와 20개 전체 읽기 검증에 성공했다. |
| 첫 토크 활성화 명령 중 END 응답 길이 불일치 | 손 상태 읽기에서 END ID 210의 16바이트 응답을 요청했지만 Python SDK가 성공 코드와 함께 3바이트만 돌려줬다. 이 단계는 모터 목표·토크 쓰기보다 앞이므로 이번 호출은 모터 토크를 켜지 않았다. 같은 호출의 END 복원 검증은 비정상 값들을 냈지만 새 포트의 읽기 전용 검사에서는 Tool ID 140, TableSync 0, 나머지 레지스터가 기본값으로 확인됐다. | Tool ID 140·TableSync 0·나머지 기본값인 중단 상태를 END 복구 명령에서 허용했다. 복구 쓰기 전 설정을 두 번 읽어 일치하는지 확인하고, Python SDK의 다음 요청 전 늦은 수신 패킷을 비우도록 토크·복구 포트를 보강했다. 후속 개별 토크 명령과 전체 읽기 검증이 통과했다. |
| 개별 토크 명령 중 부분 실패 | 모터 141·142와 여러 후속 모터는 토크 1 읽기 검증에 성공했다. 모터 148은 준비 중 측정 위치가 `1809→1848`로 변해 중단됐다. 모터 157·161은 Goal Position 쓰기 후 읽은 값이 요청값과 1카운트 달랐다. 다른 한 호출에서는 END 읽기 두 번이 달라 중단됐다. 여러 명령을 한꺼번에 입력하여 실패 뒤에도 후속 명령이 실행됐으므로, 전체 토크 상태는 출력 개수만으로 확정할 수 없었다. | 쓰기를 반복하지 않고 END 읽기만 제한 횟수 재시도하게 수정했다. `--torque-status` 진단에서 ID 148·152·157·161이 0으로 남은 것을 확인해 개별 처리한 뒤 20개 모두 torque 1을 읽었다. |
| 20개 모터 토크 활성화 완료 | 실패한 ID 148·152·157·161을 개별 명령으로 다시 실행한 뒤 `--torque-status`에서 20개 모두 `torque=1`, `hardware_error=0`으로 읽혔다. END 설정도 복원됐다. | Direct 런치의 첫 상태 읽기와 실제 키보드 명령은 별도 실물 검증이 필요하다. |
| 첫 Direct 런치 중 `status=32` | 팔 컨트롤러와 손 노드가 시작됐으나 손의 첫 90바이트 간접 상태 읽기에서 tick 10014, status 32가 나와 런치가 중단됐다. 종료 후 END 설정은 기존 OMY 값이었고, 손 주소 106을 직접 읽는 `--diagnose`는 mode 0, TableSync 0, watchdog 0, 23.73 V, status 0이었다. 공식 HX5 제어표에서 status bit 5는 미사용·항상 0으로 기술한다. | 처음에는 손가락 명령 없이 간접·직접 상태를 비교했다. TableSync 활성 시 두 경로 모두 32였고 Hardware Error 0을 확인했다. 이후 32만 명시적으로 허용하는 런치에서 관절·촉각 토픽을 받았다. |
| 유휴 간접/직접 상태 비교 | 손 TableSync 0에서 END 90바이트 간접 읽기의 status는 세 번 모두 0, tick은 29176·29380·29584, 전압은 23.73 V였다. 직접 읽기도 status 0, tick 29994, 23.73 V였다. 실패한 Direct 런치 때 손가락의 눈에 띄는 움직임은 없었다. | 유휴 간접 창 자체는 정상으로 보였다. 후속 활성 상태 비교 및 읽기 전용 런치까지 진행했다. |
| 활성 간접/직접 상태 비교 | 손 TableSync를 켠 동안 세 번 모두 간접·직접 주소 106이 `status=32`였고 tick과 약 23.7 V 전압은 갱신됐다. 진단 종료 때 손 TableSync·watchdog을 끄고 END 설정을 복원했다. | 긴 END 읽기의 단독 오류가 아니라 손 컨트롤러가 활성 상태에서 실제로 32를 보고한다. 공식 문서상 이 bit 5는 미사용이므로 의미는 미확정이다. 센서 5개의 응답과 Hardware Error 0을 확인한 뒤 제한적으로 32를 허용했다. |
| 촉각 센서 ID 검사 | END를 통해 ID 145·150·155·160·165 모두 모델 250으로 응답했고 각 센서의 9개 압력 셀은 무접촉 상태에서 모두 0이었다. 손·모터 목표값은 보내지 않았고 END 설정도 복원됐다. | 센서 ID 자체의 누락은 확인되지 않았다. 이어 활성 TableSync에서 Hardware Error 0, watchdog 100을 확인했다. 실제 접촉 압력 변화는 미검증이다. |
| 활성 상태의 추가 오류 주소 | 손 TableSync 1인 동안 세 번 모두 주소 106은 32였지만 주소 71 Hardware Error는 0, watchdog은 100, 전압은 약 23.7 V였다. | 공식 제어표와 실측의 bit 5 의미가 불일치한다. `status=32`만 명시적으로 허용하고 다른 상태·하드웨어 오류·watchdog 이상은 차단하는 읽기 전용 Direct 런치 옵션을 추가했다. 이후 관절·촉각 토픽 수신과 첫 작은 jog의 실제 움직임을 확인했다. |
| 읽기 전용 Direct 토픽과 첫 jog | `Direct Mode ready`, `read_only=True`, `active_status=32`가 나왔고 손 관절 20개와 왼손 촉각 센서 5개 × 9셀의 메시지를 받았다. 무접촉 압력은 모두 0이었다. 이후 첫 jog에서 손가락이 움직였지만 선택하지 않은 손가락도 조금 움직였다는 실물 관찰이 있었다. | 이전 jog 구현은 한 관절만 목표를 바꾸되 20개 모터 전체의 목표값을 매번 다시 썼다. 선택 모터의 4바이트 슬롯만 END 경유로 쓰도록 수정했다. 실제 선택성은 재실행 후 확인이 필요하다. 공식 키보드 첫 입력도 엄지와 범위 밖 관절을 함께 보정할 수 있다. |
| `[ID:146] Rebooting...`와 `COMM_ERROR ... There is no status packet!` 반복, 종료 시 SIGTERM/SIGKILL | 이전 직결 `DynamixelHardware`가 내부 ID를 직접 접근·재부팅하려다 응답을 못 받아 반복한 로그다. 출력의 `Rebooting`은 **재부팅 명령 시도**를 나타내며, 실제 모터 재부팅 성공을 입증하지 않는다. 종료 중에도 재시도가 계속돼 런치가 강제 종료했다. | 해당 실물 직결 런치는 계속 차단한다. 새 실물 경로는 손을 END 210으로 접근하는 별도 노드를 사용한다. |
| `/joint_states`에 `joint1..6`만 있고 `/left_hand/finger_pressures`·손 trajectory 토픽이 없음 | 그때는 팔 컨트롤러와 END Preset 노드가 실행 중이었다. Preset 경로는 공식 20관절 컨트롤러나 촉각 broadcaster를 실행하지 않는다. 이 사실만으로 Zenoh 라우터 고장을 단정할 수 없다. | Direct Mode 노드에서 손 관절·압력 토픽을 발행하도록 구현했고, 이후 실물에서 20관절·5개 촉각 센서 메시지를 수신했다. |

## 11월 3일 붙여 넣은 터미널 기록: 단계별 상세

아래 출력은 반복되는 ROS 로그를 생략한 **대표 원문**이다. `No hand command sent`는
그 검사 프로그램이 목표 위치를 보내지 않았다는 뜻이며, 다른 프로그램까지 정지했거나
손의 모든 토크가 꺼졌다는 뜻은 아니다. 동일한 포트 `/dev/ttyAMA4`를 두 프로그램이
동시에 열면 판독이 달라질 수 있으므로 각 진단은 기존 런치가 종료된 상태에서 해석했다.

### 1. 소스·빌드·실행 환경

1. 최초 `colcon build --symlink-install --packages-up-to omy_hx5_bringup`은
   `robotis_hand_playground`의 `find_package(robotis_interfaces)`에서 중단됐다.
   출력은 `robotis_interfacesConfig.cmake`를 찾지 못했다는 내용이었다. 메시지
   소스 추가 후에는 `robotis_interfaces`, 손 description·broadcaster·teleop·
   playground·bringup, `omy_hx5_bringup`의 **7개 패키지 빌드 성공**이 기록됐다.
   이는 소스 빌드 결과이고 손 통신의 증거는 아니다.
2. `omy_hx5_end_proxy_probe` 최초 실행은 Python 진입점에서
   `ModuleNotFoundError: No module named 'serial'`로 종료됐다. 컨테이너에
   `python3-serial`을 설치한 다음 같은 검사에서 END 경유 손 응답을 받았다.
3. 한 컨테이너 셸에서는 `Package 'omy_hx5_bringup' not found`가 나왔다.
   검색 경로 목록에 `/workspace/omy_ws/install`이 없었다. 해당 셸에서 overlay를
   source한 뒤 `ros2 pkg prefix omy_hx5_bringup`은
   `/workspace/omy_ws/install/omy_hx5_bringup`을 출력했다. 컨테이너 재진입 후
   빌드·source는 별도 절차라는 점을 확인했다.
4. Yocto 호스트 셸에서 `ros2 launch ...`를 입력했을 때 `-sh: ros2: command
   not found`가 나왔다. `/data/docker/open_manipulator`에서 컨테이너에 들어간 뒤
   ROS 명령을 실행해야 했다. 반대로 컨테이너 안에서 호스트 경로로 다시
   `cd /data/docker/open_manipulator`를 실행했을 때는 `No such file or directory`였다.

### 2. 연결 경로 확인: END 210, 손 140, 내부 모터

초기 `/dev/ttyAMA4` 직접 ping은 `ID 210: ping OK, model number 230`과
`ID 140: 응답 없음 — [TxRxResult] There is no status packet!`이었다. 이 결과는
END 보드까지만 직접 접근할 수 있다는 가설을 만들었지만, 손의 전원 부재를 증명하지
않았다. 실제로 END 프록시 검사는 다음 값을 읽었다.

```text
END 210: model 230 OK; left HX5 via END: ID 140, model 261 OK;
voltage 23.68 V; status 0. No hand command sent.
END 210 -> motor ID 141: model 1710 replied. No hand command sent.
```

이후 모터 141의 drive·operating mode와 토크까지 읽혔다. 처음
`--inspect-sync-ids`는 `hand is not idle Direct Control Mode: mode=1,
TableSync Enable=0`으로 중단됐다. 당시 mode 1은 손의 Preset 모드였다. 읽기 전용
검사 조건을 수정한 후 `HX5 mode 1; TableSync1 IDs via END 210:
[141, 142, 143, 144, 145]. Five indirect addresses restored; no motor
command sent.`가 나왔다. 이 다섯 ID는 첫 손가락 그룹의 모터 4개와 센서 1개다.

Preset 런치가 준비된 뒤 출력은 `END 210 -> left HX5 140 ready: model 261,
Preset Mode 1, 23.70 V, status 0. No motion command sent. Publish
std_msgs/Int32 on /omy_hx5/preset_percent to move.`였다. 사용자는 이후 Preset
명령에서 손가락이 실제 움직였다고 보고했다. Preset 성공은 20개 관절의 Direct
경로가 성공했다는 뜻은 아니다.

### 3. END 설정 쓰기 실패와 복구 상태

Direct 준비 첫 시도에서 `END 210 write 60 failed: ... There is no status
packet!`, 재시도에서는 `write 13 failed`가 나왔다. 읽기 재확인 로직을 넣은
뒤에도 `END 210 write 13 had no status packet and readback failed: ID 210
read 13+1 failed ... received=0 bytes`가 있었다. 이 로그는 손 140이 아니라
**END 210의 설정 쓰기·읽기 응답**에 대한 것이다. 해당 시점의 정확한 전기적
원인은 로그만으로 확정하지 못했다.

읽기 전용 `omy_hx5_end_recover`가 기록한 기본 OMY END 목표는 다음과 같다.
여기서 `13`은 END의 Tool ID, `46`은 TableSync Enable이다.

```text
{13: 1, 46: 1, 48: 634, 50: 0, 52: 16, 54: 0,
 56: 665, 58: 0, 60: 12, 62: 0}
```

실패 후 상태는 한 가지가 아니었다. 처음에는
`{13:1, 46:0, 48:0, 52:24, 60:0}` 계열이었고, 뒤의 실패에서는
`{13:140, 46:0, 48:8, 52:1, 60:0}` 계열이 실측됐다. 전자는 END의
기본값에서 여러 항목이 달라졌고, 후자는 손 ID 140을 Tool ID로 선택한 상태가
남았다는 뜻이다. 예를 들어 마지막 상태에서는 읽기 전용 복구 출력이 아래와
같았다.

```text
END 210 before: {13: 140, 46: 0, 48: 8, 50: 0, 52: 1,
                 54: 0, 56: 665, 58: 0, 60: 0, 62: 0}
Stock OMY END target: {13: 1, 46: 1, 48: 634, 50: 0, 52: 16,
                       54: 0, 56: 665, 58: 0, 60: 12, 62: 0}
Read only; no write sent.
```

`--apply` 복구 후에는 `END 210 after`가 위 기본값과 정확히 같았고
`Stock OMY END settings verified. No hand or motor goal sent.`가 나왔다.
복구 명령의 성공은 END 설정 복원에 대한 증거다. 손 모터 토크 상태까지 바꾼
결과로 해석하지 않는다.

한 번은 `All 20 HX5 actuators identified and match ROBOTIS setup; no motor
goal sent.` 뒤에 `END restoration incomplete; TableSync left off; END write
buffer differs from saved value`가 나왔다. 모터 발견은 통과했지만 END 복원 검사가
실패한 경우다. 뒤에 사용하지 않는 버퍼 전체와 실전송 12바이트를 구분하도록
복원 비교를 수정했다.

### 4. Watchdog·손 상태 읽기 문제

Direct 준비 중 `HX5 Bus Watchdog is not 100 (2 seconds)`가 나왔고, 뒤의
추가 검사에서는 `HX5 Bus Watchdog is 255; expected idle 0 or 100`이 나왔다.
한때 해제 시도 출력은 `model=261, mode=0, TableSync=0, status=1,
watchdog=170`이었다. 유효 범위 밖인 170과 동시에 END의 설정 복원도 실패했으므로,
이 한 번의 묶음 읽기를 손의 확정 레지스터 상태로 보지 않았다. END의 작은 창을
통한 새 tick 검사를 추가해 실제 상태를 다시 확인했다.

```text
END direct preparation failed: END restoration stopped:
cannot verify TableSync off: END TableSync could not be disabled;
original failure: cannot clear HX5 watchdog:
model=261, mode=0, TableSync=0, status=1, watchdog=170
```

```text
HX5 ID 140 via END 210: mode=0, table_sync=0, watchdog=0,
tick_before=10989, tick_after=12217, tick_advanced=True,
voltage_centivolts=2377, status=0. No hand or motor command sent.
HX5 via END 210, fresh hand tick: model=261, id=140, mode=0,
table_sync=0, watchdog=0, tick=15493, voltage_centivolts=2377,
status=0, end_tool_status=1. No hand or motor command sent.
```

이 결과로 손 컨트롤러의 전원과 통신, tick 갱신은 확인됐다. 앞서 큰 읽기
창에서 나온 `hand realtime tick stayed at 0`은 전원 단절로 단정할 수 없었다.
`end_tool_status=1`의 세부 의미 역시 이번 출력만으로 확정하지 않는다.

### 5. 전원과 모터 토크는 별도였다

처음 BASE ID 200을 읽는 간단한 Python 명령은
`AssertionError: BASE 포트 열기/속도 설정 실패`로 끝났다. SDK 기본
`setBaudRate(6_250_000)`이 OMY 전용 6.25 Mbps를 받아들이지 않았기 때문이다.
사용자 지정 속도를 허용하는 읽기 전용 코드에서는 `BASE 200 ping: 220
[TxRxResult] Communication success! 0` 및 `Power Enable(512): 1
[TxRxResult] Communication success! 0`이 나왔다. END 경유 손 입력은
약 23.7 V였으므로, 이 시점의 **느슨한 손**을 전원 부재와 동일시할 수 없다.

모터 141을 읽었을 때는 `torque 0, error 0, watchdog 0, goal current 300,
goal position 1530, present position 1530`이었다. 이어 붙여 넣은
`END direct preparation failed: motor configuration differs from ROBOTIS Xacro`
출력에는 아래 20개 모터가 **모두 torque=0**, model 1710, Operating Mode 5,
Hardware Error 0으로 나왔다.

```text
141 142 143 144 | 146 147 148 149 | 151 152 153 154 |
156 157 158 159 | 161 162 163 164
```

같은 출력에서 Drive Mode 실측 4/5와 공식 Xacro 12/13은 bit 3 차이로 표시됐다.
각 모터의 homing offset과 간접 주소 1–10은 기대값과 일치했다. 로그의 대표
행은 `ID 141: model=1710, drive=5, mode=5, homing=0, torque=0,
goal_raw=1506, hardware_error=0, aliases=(126,127,128,129,132,133,102,103,116,117)`이다.
따라서 이 검사에서 Direct 준비를 막은 핵심은 20모터 torque 0이었다.

첫 `omy_hx5_end_torque_on` 묶음 시도는 `ID 210 read 72+16 failed:
result=Communication success!, error=0, received=3 bytes`로 중단됐다.
뒤의 END 복구 검사에서 일시적으로 `13:170`, `50:43434`, `52:42636` 같은
비정상 값도 나왔다. 새 포트의 안정된 재검사에서는 Tool ID 140·TableSync 0,
나머지 기본값을 읽었고 복구 명령으로 기본 설정을 되돌렸다. SDK 성공 코드와
요청 길이에 못 미친 응답을 동시에 받았으므로, 그 결과를 유효한 16바이트
손 상태로 채택하지 않았다.

이후 모터 141 단독 명령은 다음처럼 성공했고 사용자가 손이 뻣뻣해졌다고
보고했다. 이는 **해당 모터의** torque 1과 물리적인 저항감 확인이다.

```text
HX5 motor torque ON verified: 1 selected, 1 newly enabled.
Goal Position was set to each motor's measured position and startup
Goal Current to 100. No grasp trajectory sent.
```

후속 개별 명령 중 ID 148은 `motor 148 moved while preparing torque:
1809, 1848`로, ID 157은 Goal Position 주소 116 읽기값이
`expected=[146, 11, 0, 0], actual=[147, 11, 0, 0]`으로,
ID 161은 `expected=[38, 7, 0, 0], actual=[37, 7, 0, 0]`으로 중단됐다.
다른 시도에서는 `END proxy read was unstable; no hand state accepted;
rollback errors=[]`가 나왔다. 실패 메시지의 `rollback errors=[]`는 복원
시도 자체의 추가 오류가 없었다는 뜻이지, 전체 20개 토크가 모두 켜졌다는 뜻이
아니다. 여러 명령을 한꺼번에 붙여 넣어 실패 후 다음 명령도 계속 실행됐으므로
**최종 상태는 별도 읽기 검사로 판정**했다.

첫 전체 읽기 결과에서 ID 148·152·157·161은 `torque=0`, 나머지 16개는
`torque=1`, 전부 `hardware_error=0`이었다. 남은 네 ID를 개별 처리한 뒤
`--torque-status`의 최종 결과는 위에 적은 **20개 모두 `torque=1`,
`hardware_error=0`**이었다. `No hand or motor goal sent. END settings
restored.`도 출력됐다. 토크 확인은 관절 명령의 성공을 의미하지 않는다.

### 6. Direct Mode 준비와 `status=32`

20모터 토크를 켠 후 준비 검사는 `HX5 Direct Control Mode 0 and persistent
aliases verified; idle Bus Watchdog=0; no motor goal sent.`로 통과했다. 첫
실물 Direct 런치에서는 팔의 `joint_state_broadcaster`와 `arm_controller`가
활성화됐지만 손 노드가 다음 오류로 종료됐다.

```text
END direct bringup failed: HX5 health invalid: tick=10014, status=32
[omy_hx5_end_direct-4]: process has died ... exit code 1
process[omy_hx5_end_direct-4] was required: shutting down launched system
```

뒤이어 `ros2_control_node`가 팔 모터 ID 1–6을 `Torque OFF` 했고,
`controller_manager.pal_statistics`의 `context cannot be slept with because
it's invalid!`가 종료 중 출력됐다. 후자는 손 통신의 최초 실패가 아니라 런치
종료 과정의 부수 로그다. 사용자는 이 실패 때 손가락의 눈에 띄는 움직임이
없었다고 보고했다.

실패 직후 END는 기본 OMY 값으로 복원돼 있었다. `--diagnose`는 유휴
손에서 `mode=0, table_sync=0, watchdog=0, tick=10035,
voltage_centivolts=2373, status=0`을 읽었다. 손 TableSync를 켜지 않은
간접·직접 상태 비교에서도 세 번 모두 status 0, 전압 23.73 V, tick 증가였다.
반면 TableSync를 활성화한 비교에서는 세 번 모두 다음 패턴이 나왔다.

```text
sample 1: indirect status=32, direct status=32, table_sync=1,
          hardware_error=0, watchdog=100
sample 2: indirect status=32, direct status=32, table_sync=1,
          hardware_error=0, watchdog=100
sample 3: indirect status=32, direct status=32, table_sync=1,
          hardware_error=0, watchdog=100
```

실제 세 샘플의 간접 tick은 `9397 → 11440 → 13484`였고 전압은 약
23.70–23.73 V였다. 손끝 센서
ID 145·150·155·160·165도 각각 model 250으로 응답했고 무접촉 9셀은
모두 0이었다. 따라서 32는 긴 END 간접 읽기 하나만의 오류가 아니라
TableSync 활성 시 손 컨트롤러의 직접 상태 주소에서도 보인 값이다.
공식 제어표는 Status 주소 106의 bit 5를 미사용·항상 0으로 설명하므로
**32의 정확한 의미는 아직 확인되지 않았다**. 실측한 Hardware Error 71은
0이었고 Watchdog은 활성값 100이었다. 코드에서는 32만 명시적으로 허용하고
다른 비정상 상태, Hardware Error 및 Watchdog 이상은 계속 차단했다.

### 7. 읽기 전용 런치, 관절·촉각 토픽, 첫 손가락 동작

읽기 전용 런치는 `Direct Mode ready. No motion command sent.
read_only=True, active_status=32. Hand goals rejected; joint and tactile
topics active.`를 출력했다. 다른 컨테이너 터미널에서 손 관절 토픽을 조회하자
`finger_l_joint1`부터 `finger_l_joint20`까지 20개 이름과 위치가 나왔다.
예를 들어 joint1 `-0.788466`, joint6 `1.501767`, joint17 `-0.648874`
rad였다. 팔의 `/joint_states`와 손의 `/joint_states`는 별도 메시지로
발행되므로 한 번의 `echo --once`에 팔만 나오거나 손만 나올 수 있다.

`/left_hand/finger_pressures`는 `hand_name: left`,
`frame_id: hx5_d20_left_base`, 센서 `finger_l_sensor1..5`와 각
`Present Pressure 1..9`를 포함했다. 그때 45개 셀은 모두 0이었다.
이는 **무접촉 데이터가 ROS 토픽으로 도착했다**는 확인이며, 실제 접촉에 대한
압력 변화나 히트맵의 물리 정확도 검증은 아니다.

이어 작은 jog 명령으로 손이 조금 움직였다는 사용자의 육안 보고가 있었다.
선택하지 않은 다른 손가락도 조금 움직였다. 당시 구현은 한 관절의 목표만
변경해도 20개 모터의 목표를 전부 다시 쓰고 있었다. 이후 선택 모터의
4바이트 슬롯만 전송하도록 수정했다(`aa68941`). **그 수정 후의 실물 선택성은
아직 확인하지 않았다.** 전체 손 키보드와 리더 방아쇠 텔레옵도 별도 실물
검증이 필요하다.

### 8. 터미널에 설명·프롬프트까지 붙여 넣은 경우

이는 장치 통신 실패와 구분해야 한다. 사용자가 복사한 여러 줄에 명령과 설명,
이전 셸 프롬프트·출력이 함께 포함된 사례가 있었다.

| 입력 사례 | 실제 출력과 해석 |
| --- | --- |
| `git submodule update --init third_party/robotis_handcd /data/docker/open_manipulator` | `handcd`와 `cd`가 붙어 경로가 저장소 밖이라는 `fatal` 출력. `git submodule update --init third_party/robotis_hand`와 `cd ...`를 별도 줄로 실행한 뒤 정상 진행. |
| 명령 뒤에 한국어 안내문 `를 실행하고 END 210 before/after`까지 입력 | `omy_hx5_end_recover: error: unrecognized arguments: ...`. 옵션 파싱 오류이며 END 읽기는 실행되지 않음. |
| `root@omy-...#` 프롬프트와 traceback 출력까지 셸에 재입력 | `bash: ... No such file or directory`, `File: command not found`, `ModuleNotFoundError:: command not found` 등. 원래 Python 오류가 새로 늘어난 것이 아님. |
| 여러 `ros2 run ... --motor-id ...`를 연속 붙여 넣음 | 앞의 명령이 exit 1이어도 뒤의 명령이 계속 실행됨. 성공 메시지 개수로 최종 토크 상태를 추정하지 않고 `--torque-status`로 재확인. |
| 손으로 붙여 넣은 Python heredoc의 닫는 `PY` 줄에 다른 텍스트가 섞임 | 화면에 `PY  port.closePort()...`처럼 표시됨. 그 출력 일부는 유효했어도 그 입력 자체를 재사용 가능한 검사 스크립트로 간주하지 않음. |
| `fuser -v /dev/ttyAMA4` | 컨테이너에서 `fuser: command not found`. 이후 `/proc/.../fd` 검색과 프로세스 목록을 사용했지만, 이 출력만으로 시리얼 포트 경쟁이 절대 없었다고 증명하지 않음. |

### 9. SSH 접속 문제는 손 제어 오류와 별개

`ssh root@SNPR44B1050`은 `Temporary failure in name resolution`,
`.local` 이름은 `Name or service not known`이었다. IP로 시도한
`ssh root@10.42.0.241`은 한때 `No route to host`였다. 그때 User PC는
`wlo1 10.148.191.40/22`의 eduroam에만 연결돼 있었고, 10.42.0.241로 가는
경로가 Wi-Fi 게이트웨이 `10.148.188.1`로 향했다. USB 직결 이더넷
`enx5414a7e483b1`이 `10.42.0.1/24`로 연결된 뒤에는 경로가 해당 장치로
바뀌었고 IP SSH에 성공했다. DNS 이름 실패와 직접 케이블 미연결은 다른
문제다.

## 별도 첨부 로그의 날짜 구분

대화에 붙은 두 긴 텍스트 파일은 로그의 로그인·ROS 기록 시각이
**2026-10-13**이다. 11월 3일 실험의 새 실패로 집계하지 않았다.

- 한 첨부에는 END 210 직접 ping 성공(모델 230), 손 140 직접 ping 무응답,
  overlay를 source하기 전 `Package 'omy_hx5_bringup' not found`가 있다.
  User PC 전용 환경 변수와 `user_pc/omy_hx5_keyboard.py` 경로를 Robot PC
  컨테이너에 붙여 넣어 `python3: can't open file ... No such file or
  directory`도 나왔다. 같은 첨부의 옛 손 전용 런치는
  `[rmw_zenoh_cpp]: Unable to connect to a Zenoh router`를 출력했고,
  `controller_manager`가 `/robot_description`을 기다리는 동안 spawner도
  서비스를 찾지 못했다. 이는 **그 런치 세션**에서의 라우터 연결 문제다.
  11월 3일 Direct 런치의 `status=32`나 모터 토크 0의 원인으로 소급하지 않는다.
- 다른 첨부에는 `joint_trajectory_executor` step 0·1 완료 및
  `arm_controller: Goal reached, success!`가 있다. 이어
  `Trigger read/write called while the previous async trigger is still in
  progress` 경고가 한 번 나왔고, Ctrl+C 종료 시 팔 ID 1–6 `Torque OFF`,
  `pal_statistics`의 invalid-context 출력이 나왔다. 이것은 당시 팔 명령
  수행 뒤 정지 로그이며, 11월 3일 손 Direct 성공의 증거가 아니다.
- 별도 첨부의 `[ID:146] Rebooting...` 반복 로그는 ROS 시각
  `1793691142`로 시작한다. 이는 11월 3일의 옛 직결 방식 실패다. 146,
  147, 148, 149, 151, 152 등에서 `COMM_ERROR ... There is no status
  packet!`가 이어지고 Ctrl+C 뒤 5초의 SIGTERM, 10초의 SIGKILL,
  exit code `-9`로 끝났다. 여기의 `Rebooting`은 드라이버가 재부팅을
  **시도**했다는 로그이지 장치가 실제로 재부팅됐다는 확인이 아니다.

## 11월 3일 종료 시 확인된 상태와 남은 검증

| 항목 | 실제 확인 범위 |
| --- | --- |
| 배선·통신 | 기존 그리퍼 4핀 → END 210 → 왼손 컨트롤러 140(모델 261) → 모터 20개와 센서 5개. END 직접 ping, 프록시 읽기, 23.7 V대 전압 확인. |
| END 설정 | 마지막 읽기 전용 검사에서 OMY 기본값 `{13:1,46:1,48:634,52:16,56:665,60:12}` 및 나머지 0 항목이 일치. 실패 직후에는 설정이 달랐으므로 다음 시도마다 실제 상태를 다시 읽어야 함. |
| 손 모드·토크 | Direct Mode 0, 유휴 TableSync 0·Watchdog 0 검증. 20모터가 모두 torque 1, Hardware Error 0이라는 읽기 결과를 받음. 전원 재시작 후에도 토크 1이 유지된다고 가정하지 않음. |
| 활성 손 상태 | TableSync 1일 때 status 32가 반복 실측됨. Hardware Error 0, Watchdog 100, 전압·tick 정상. bit 5의 정확한 의미는 미확정. |
| ROS 데이터 | `finger_l_joint1..20` 위치와 `left_hand/finger_pressures`의 5 × 9셀(무접촉 모두 0)을 수신. 접촉 압력 변화는 미검증. |
| 손 동작 | Preset의 실제 손가락 움직임과 첫 작은 Direct jog의 실제 움직임을 사용자 육안으로 확인. 첫 jog에서 다른 손가락도 조금 움직였고 이후 선택 모터만 쓰도록 코드 수정. 수정본의 실물 재검증은 남음. |
| 텔레옵 | 공식 전체 키보드·리더 방아쇠→손 20관절·팔 동시 추종은 아직 실물 실행으로 확인하지 않음. |

다음 물리 시험은 [Direct 손 실행 절차](../hx5-d20-omy-direct-hand.md)에서
최신 코드를 빌드한 뒤, END 설정과 토크를 읽고 선택 모터 한 개의 작은 jog가
다른 손가락을 움직이지 않는지 확인하는 것이다. 이어 손끝에 실제 접촉을
주었을 때 촉각 45셀 중 해당 값이 변하는지 검증한다. 전체 손 키보드와
[리더 텔레옵](../hx5-d20-omy-teleop.md)은 그 뒤에 판단한다.

이 문서의 원인 분석은 붙여 넣은 출력과 후속 END 경유 성공 결과에 근거한다.
종단저항 상태, 순간적인 시리얼 패킷 손실의 전기적 원인, 손 컨트롤러의
`status=32` 의미까지 확정한 실물 전기 진단은 아니다.
