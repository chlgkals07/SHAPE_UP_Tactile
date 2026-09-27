# 촉각센서 하드웨어 사전 검토

검토일: 2026-09-27

## 문서의 범위

이 자료는 **LEAP Hand에 어떤 촉각센서를 구매하고 장착할 수 있는지 판단하기 위한 하드웨어 중심의 사전 조사**다.

관련 논문의 robot setup, sensor placement, taxel 수, 공개 코드와 장착 자료를 확인했지만, 팀이 각 논문의 방법과 실험을 정독해 재검증한 literature review는 아니다. 논문별 주장과 성능 수치는 향후 원문을 읽고 별도로 검토한다.

## 현재 하드웨어 판단

현재 1순위는 **PaXini PX-6AX GEN3**다.

- LEAP Hand에서 PaXini tip+pad 배치를 사용한 연구 사례와 공개 코드가 있다.
- normal·shear를 포함한 분산 3축 tactile array를 정책 입력으로 사용할 수 있다.
- GEN3 sensor와 통신 보드를 국내 디바이스마트에서 기관 구매할 수 있다.
- 기존 mount를 그대로 쓰는 방식은 아니며 GEN3 형상에 맞게 기구·software interface를 직접 수정해야 한다.

구매 기준은 다음과 같다.

| 품목 | 수량 | 구성 |
|---|---:|---|
| DP-S2015-Elite | 5 | fingertip 운용 4 + 예비 1 |
| IP-S1610-Elite | 5 | finger pad 운용 4 + 예비 1 |
| 고속 통신 통합 보드 `[paxini-02]` | 2 | 보드당 운용 센서 4개 가정 |

확인된 VAT 포함 합계는 **1,353,000원**이다. 하네스, 전원, USB cable, mount 제작비와 예비 보드는 포함되지 않는다.

## 팀이 먼저 볼 자료

1. [PaXini 구매·통합 계획](paxini-integration.md)
2. [구매 BOM](paxini-bom.xlsx)
3. [전체 조사 HTML](report/README.md)

## HTML 보고서에 대한 주의

HTML 보고서는 조사 과정 전체를 보존한 스냅샷이다. 여러 sensor 후보와 관련 논문을 넓게 찾기 위해 AI를 사용해 작성했으며, 현재 결정과 다른 과거 순위도 포함한다. 팀 내부 참고용으로 사용하고 논문 내용이나 성능 수치를 연구 근거로 인용하기 전에는 원문을 확인한다.

## 브랜치 사용 원칙

자료조사를 코드와 분리하기 위해 장기 전용 branch를 유지하지 않는다. branch는 review 후 main에 합치는 임시 작업 단위로만 사용한다.

repository 안에서는 다음처럼 폴더로 구분한다.

```text
research/      하드웨어 조사, 구매 자료와 조사 스냅샷
prior-work/    팀원이 직접 읽고 작성한 논문 노트
src/           이후 구현 코드
hardware/      이후 CAD, mount와 wiring 자료
```

문서 규모가 코드보다 훨씬 커지거나 외부 공개 범위가 달라지면 그때 `SHAPE_UP_Tactile_Research` 별도 repository 또는 GitHub Wiki로 분리한다.

