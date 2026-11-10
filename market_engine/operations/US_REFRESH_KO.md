# 미국 운영 가격·추론 복구

`us_refresh`는 미국 가격과 Frozen V1 추론을 별도 수집 버전으로 갱신합니다.
기존 `run.py`의 엄격한 재현 조건은 유지합니다.

## 데이터 정책

`us-full-source-vintage-v1`은 기존 연구 입력과 새로운 운영 입력을 구분합니다.

1. 원본 계산 코드, reference, 모델·Scaler의 고정 해시를 확인합니다.
2. 동결 캐시로 기존 feature·MSI·임계값을 원래 `rtol=atol=1e-9` 기준으로 재현합니다.
   이 검사가 실패하면 수집·새 export 발행 전에 중단합니다.
3. Yahoo의 배당·분할 수정종가와 VIX, FRED의 DBAA·DGS10 전체 이력을 한 수집 버전으로 보관합니다.
   동결 캐시와 새 가격을 이어 붙이거나 Scaler·모델을 다시 학습하지 않습니다.
4. 제공처의 과거 수정값은 `revisionAudit`에 비교 행 수·변경 수·최대 차이로 기록합니다.
   이 별도 운영 정책은 과거 수정이 무해하거나 OOS 성능이 유지된다는 인증이 아닙니다.
5. 실제 같은 날짜의 SPY·VIX·신용 spread와 유한한 feature·MSI·임계값이 있는 날짜만 추론합니다.
   모델 입력 순서·출력 범위를 검증하고 학습 cutoff와 동결 캐시 이후 관측만 사용합니다.
6. 가격은 가장 최근 실제 장 마감까지 수집합니다. 추론은 공식 달력의 공개 여유 시간을 적용한
   기준일까지 계산합니다. 신용 원천이 늦으면 `DELAYED`, `current=null`을 유지하면서
   최신 **검증 관측일**의 점수를 표시합니다. 가격만 있는 날짜에 점수를 이월하지 않습니다.

기존 OOS CSV, `global-markets.json`, `korea-monitor.json`, 모델과 원본 reference는 변경하지 않습니다.
한국 export를 다시 수집한 것으로 표시하지 않도록 원래 생성 시각도 보존합니다.
학습 cutoff는 기존 계약의 추정값이며, 학습 receipt가 미보존되었다는 설명을 그대로 유지합니다.

## 실행

분리된 Python 환경에 `market_engine/operations/requirements.txt`를 설치합니다. 원본 V1은 계약 해시와 일치하는
읽기 전용 체크아웃이 필요합니다. 검증한 원본 코드 커밋은 `e939dc358c3bca92fee4c318d4bb297fd80debd3`입니다.

저장소 루트에서:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m market_engine.operations.us_refresh \
  --original-v1-root /path/to/pinned/market-stress-early-warning \
  --publish-prices
```

새 수집 결과는 `data/operations/<run-id>/`에 저장됩니다. 원천별 CSV·수집 receipt·SHA,
동결 캐시 재현 계산 로그, 운영 계산 로그와 `us-refresh.json`을 함께 보관합니다.
원천 전체 CSV와 FRED 금리 값은 공개 export로 내보내지 않습니다.
`--publish-prices`를 명시하면 요청된 SPY 가격 차트만 공개합니다. 기본값은 가격 제외입니다.

네트워크 없이 동일 수집 자료 재생성:

```bash
python -m market_engine.operations.us_refresh \
  --original-v1-root /path/to/pinned/market-stress-early-warning \
  --publish-prices --replay-run data/operations/<run-id>
```

## 2026-11-10 복구 검증

- 수집 버전: `20261110T094702Z-da25cb53`.
- SPY·VIX 최신 관측: 2026-11-09. DBAA·DGS10 최신 관측: 2026-11-06.
- 최신 SPY 수정종가: 752.69 USD, 2026-11-09.
- 최신 공통 관측일 추론: 2026-11-06. Risk Score 94.5%, MSI 1.140, 임계값 1.292.
- 이 Risk Score는 보정된 시장 스트레스 확률이나 포트폴리오 손실 확률이 아닙니다.
- 원본 캐시 재현 통과, 수집 자료 replay 시 가격·모든 추론·결측·수정 통계가 정확히 동일함을 확인했습니다.
- 한국 수치와 연구/OOS 스냅샷을 보존했습니다.

## 배포 전달

화면이 읽는 파일은 `frontend/public/data/operational-markets.json`입니다.
GitHub 동기화만으로 실행 중인 AWS 이미지가 바뀌지는 않습니다.
AWS 배포 담당 작업은 **JM973279/market-portfolio-risk-intelligence의 main**에서
수정 코드와 새 export를 가져와 웹 이미지를 다시 빌드·배포해야 합니다.
API 이미지는 이 수정의 대상이 아닙니다.

반영 후 `/us`와 홈에서 가격 관측일 11/09, 추론 관측일 11/06이 구분되는지 확인합니다.
현재 수집·배포는 명시적 실행이며, 이 변경은 새 AWS 자원이나 예약 작업을 만들지 않습니다.
