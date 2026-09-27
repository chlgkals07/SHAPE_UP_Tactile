# PaXini GEN3 구매·통합 계획

## 구매안

| 품목 | 수량 | VAT 포함 단가 | 금액 | 링크 |
|---|---:|---:|---:|---|
| DP-S2015-Elite, 20×15×10 mm | 5 | 90,200원 | 451,000원 | [디바이스마트](https://www.devicemart.co.kr/goods/view?no=16040501) |
| IP-S1610-Elite, 16×10×8 mm | 5 | 90,200원 | 451,000원 | [디바이스마트](https://www.devicemart.co.kr/goods/view?no=16040502) |
| 고속 통신 통합 보드 USB to UART `[paxini-02]` | 2 | 225,500원 | 451,000원 | [디바이스마트](https://www.devicemart.co.kr/goods/view?no=16040513) |
| **합계** |  |  | **1,353,000원** |  |

가격·상품명·링크는 2026-09-27에 확인했다. 판매 페이지상 평균 준비기간은 `[해외] 1주일`이다.

## 계획한 연결

```text
thumb tip+pad + index tip+pad   → Board A → USB serial
middle tip+pad + ring tip+pad   → Board B → USB serial
LEAP Hand                       → separate USB serial
```

보드당 4센서는 공개 연구 코드의 구성을 참고한 보수적인 가정이다. 현재 판매 보드가 4센서만 지원한다는 뜻은 아니다. 판매 페이지는 최대 28개 센서를 표시하지만, 8개 GEN3 sensor의 동시 고속 출력률과 전원 공급을 보증하는 정보는 아니다.

## 별도로 필요한 것

- 운용 8센서와 예비 2센서용 harness
- board-to-PC USB cable 2개와 예비 cable
- 두 보드와 운용 센서 8개의 전원 구성
- GEN3용 fingertip/finger-pad mount
- screw, insert, cable clamp와 strain relief
- sensor/board CAD, taxel coordinate와 calibration file

## 공급처에서 확인할 항목

1. 보드 하나에 S2015 2개와 S1610 2개를 연결하는 정확한 배선
2. 같은 PC에서 보드 두 개를 독립 serial device로 읽을 수 있는지
3. 필요한 harness의 part number, 길이, 수량과 pinout
4. board input voltage, sensor power budget와 USB back-power 처리
5. Linux에서 모든 taxel의 Fx/Fy/Fz raw data에 접근 가능한지
6. 실제 지속 output rate와 timestamp 방식
7. viewer, SDK/protocol, 좌표 파일, CAD와 calibration 자료

## 통합 작업

### 기구

1. 보유 LEAP revision을 확인한다.
2. 공개 mount는 참고만 하고 GEN3 CAD와 cable exit에 맞춰 다시 설계한다.
3. 전체 관절 범위에서 self-collision과 object 접근성을 확인한다.
4. 손가락마다 cable strain relief를 설계한다.

### 데이터

1. sensor ID와 물리 장착 위치를 고정한다.
2. packet status, checksum, frame counter와 timestamp를 기록한다.
3. taxel local coordinate를 sensor→link→hand-base frame으로 변환한다.
4. force vector도 같은 frame으로 회전한다.
5. raw 값, zero/noise/drift와 heatmap을 먼저 검증한다.

### 정책 입력

초기 baseline은 다음 순서로 만든다.

1. proprioception only
2. contact mask와 부위별 합력
3. normalized raw force
4. taxel position+3축 force token
5. temporal window 기반 slip/contact transition

논문에서 사용한 tactile representation과 fusion 방법은 팀이 원문을 읽은 뒤 재현 범위를 결정한다.

## 실물 완료 기준

- 운용 센서 8개가 동시에 식별된다.
- 모든 taxel의 3축 값과 위치를 시각화할 수 있다.
- 장시간 수집에서 frame loss, latency, jitter와 drift를 측정한다.
- normal/shear 방향이 실제 가압 방향과 일치한다.
- LEAP 동작 중 mount와 cable이 관절 범위를 방해하지 않는다.
- `q`, `qdot`, tactile과 camera timestamp를 같은 episode에서 저장한다.

