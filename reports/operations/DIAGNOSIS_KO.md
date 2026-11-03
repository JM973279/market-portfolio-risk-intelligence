# Frozen V1 운영 경로 진단 (2026-11-03)

원격 fetch 후 HEAD와 origin/main은 d2197c4로 동일(좌/우 차이 0/0).
작업 브랜치는 feature/frozen-v1-operational-data. push/merge 없음.

## 원천과 마지막 실제 관측

별도 원본 저장소: ../market-stress-early-warning (읽기 전용으로 사용).

| 시장 | 파일 | 관측 종료 | 수집/생성 코드 |
| --- | --- | --- | --- |
| US | data/raw/raw_market_data.csv | SPY/VIX 2026-10-05, spread 2026-10-02 | src/data/fetcher.py; Yahoo auto-adjusted Close, FRED DBAA-DGS10 |
| KR | data/raw/korea/krx_indices.csv | 2026-10-15 | src/korea/download_krx_indices.py; KRX KOSPI200 |
| KR | data/raw/korea/vkospi.csv | 2026-10-15 | src/korea/download_vkospi.py; KRX VKOSPI |
| KR | data/raw/korea/ecos_credit.csv | 2026-10-15 | src/korea/download_ecos_credit.py; ECOS 817Y002, 국고3년/회사 AA-3년 |
| KR | 현재 data/processed/early_warning_v2/korea_latest_features_v1_reproduction.csv | 2026-10-15 | build_korea_features_v2.py(inference_only=True) |
| KR | 현재 korea_feature_matrix_v1_reproduction.csv | MSI/threshold 2026-10-02, label 2026-09-16 | 공식 target inner join으로 기간 제한 |
| US | 원본 data/features/feature_matrix.csv | MSI/threshold 2026-10-05, label 2026-09-21 | cleaner → stress_index → targets → engineering |
| KR/US | OOS CSV | KR 2026-09-16 / US 2026-09-21 | 미래 10거래일 label을 요구하는 평가 기록 |

기존 캐시 수집 시각은 입증할 수 없음. 파일 수정 시각을 수집 시각이나 학습 시각으로 사용하지 않는다.
한국 지수는 long format이며 (Date, Index)가 키다. 날짜만 중복되는 것은 정상이다.

## 모델, 전처리, 재현성

- 한국 사이트 기준 Frozen V1 reproduction: 현재 models/early_warning_v2/v1_reproduction/xgboost_10d_latest.joblib.
  SHA256 b8524d9dab692434e051011987bc6a86ffbd18c20a0c30ff00b4b30856318247.
  17개 feature 이름/순서는 builder FEATURE_COLS와 artifact feature_names_in_에서 일치.
  StandardScaler + XGBClassifier Pipeline 자체로 predict_proba. 새 scaler fit 금지.
  scaler n_samples_seen_=3714. 현재 labeled matrix 3714행(2011-08-08~2026-09-16)의
  mean/variance와 최대 오차 2.22e-16. 학습 입력 cutoff 2026-09-16 재현 가능.
  모델 학습 실행 시각 자체는 artifact에 기록되지 않음.
- 원본 KR deployment hash 42c302...는 위 reproduction과 다름. 임의 대체하지 않는다.
- US 원본 models/saved/xgboost_latest.joblib와 xgboost_latest_17f.joblib는 동일한
  SHA256 90c51c245ebe62b58f804098a7a7045b60fb64ef83da72d4c9a049cf8d5eeb0d.
  StandardScaler + 17-feature XGBoost. scaler n_samples_seen_=6317.
  현재 matrix의 labeled prefix 6317행(2001-08-02~2026-09-16)과 mean 최대 오차
  1.54e-7, variance 1.11e-8. 현재 matrix labeled 종료(9/21)를 학습 cutoff라고
  단정할 수 없다. 정확한 학습 실행 시각·입력 receipt가 없으므로 cutoff는 추정치다.
  운영 시 원본 artifact/hash/feature 순서를 고정하고 이 한계를 표시한다.
- 두 시장 feature는 equity 7개, volatility 5개, credit 5개.
  pct_change(1/5/20), rolling std(20/60)*sqrt(252), cummax drawdown,
  value/rolling mean(20)-1, vol/credit diff(1/5), shifted rolling(252,min=60) zscore(+1e-8).
- 공식 MSI: negative equity pct_change(21), volatility level, credit spread의 동일 가중 Z.
  shifted rolling(252,min=126), sample std. KR zero std는 NaN; US denominator +1e-8.
  공식 threshold: MSI.shift(1).expanding(min_periods=252).quantile(0.90).
  Risk warning 0.50은 MSI threshold와 별개다.

## 기존 수집/추론 경로

원본 src/operations/{providers,refresh,worker,calendar,validation}.py와
/api/latest, /api/korea/latest가 존재. worker는 경로를 stage로 바꿔 계산하지만
API import, 운영 ledger/알림/attribution 의존성을 포함한다. 이 프로젝트 웹은 호출하지 않는다.
원본 운영 refresh를 그대로 실행하면 원본 운영 DB/알림에 부작용이 있을 수 있어 실행하지 않는다.
provider adapter와 공식 계산기만 분리 프로세스에서 재사용하고 출력은 신규 운영 디렉터리에 한정한다.
원본 US cleaner는 VIX/credit ffill(limit=5)을 수행한다. 기존 연구 재현에는 보존하되
신규 운영 점수는 해당 날짜의 원천 3채널이 모두 실제 관측된 경우만 허용한다.

## Portfolio 경계

src/portfolio/server.py의 독립 FastAPI, api.py router, data/snapshot/analytics/factors/stress/whatif,
data/portfolio의 frozen snapshot 및 frontend/src/lib/portfolio-api.ts → /portfolio를 보존한다.
시장 운영 수집은 portfolio.data의 수집기/스냅샷 명령을 호출하지 않는다.
공유 pandas/numpy/requests/yfinance와 frontend DashboardShell 외 계산 의존성을 추가하지 않는다.

## 판단

KR: 고정 모델·feature 전처리·공식 MSI/threshold 재현 경로가 존재한다.
US: 계산 경로는 존재하나 학습 receipt가 없어 cutoff의 엄밀한 증명이 제한된다.
두 시장 모두 기존 파일과 수치 대조 후에만 별도 운영 추론을 허용한다.
외부 수집 성공과 최신성은 별개로 검증해야 하며, 실패 시 N/A를 유지하고 이유를 표시한다.
OOS CSV를 연장하거나 학습기를 실행하지 않는다.
