# Frozen V1 운영 수집 및 추론

이 모듈은 별도 V1 저장소를 **읽기 전용 코드/캐시 의존성**으로 사용한다.
학습, API 서버, 원본 운영 refresh, 알림, Portfolio 수집/스냅샷을 실행하지 않는다.

## 실행

별도 가상환경에 `requirements.txt`를 설치한다. 기존 Portfolio 환경을 업그레이드하지 않는다.
이 작업에서는 원본 저장소의 검증된 `.venv/bin/python`을 사용했다.

```bash
# 네트워크 없이 기존 캐시와 공식 연구 수치의 일치 및 고정 모델 추론 검증
<inference-python> market_engine/operations/run.py

# 신규 원천 수집 후 검증. 원본 .env의 기존 KRX_API_KEY / ECOS_API_KEY를 메모리에서 사용
<inference-python> market_engine/operations/run.py --collect

# 저장한 원천 SHA를 확인하고 네트워크 없이 동일 수집 자료 재계산
<inference-python> market_engine/operations/run.py --replay-run data/operations/<run-id>

# 검증된 export를 웹에 반영
cd frontend
npm run build
npm run start
```

`--original-v1-root`로 원본 저장소 위치를 지정할 수 있다. `contract.json`의
공식 계산 코드, reference CSV와 모델 SHA가 달라지면 실패한다. 코드가 없거나
파일이 변경됐다고 자동으로 hash를 갱신하지 않는다. 원본 코드/모델 변경 시 별도 검토가 필요하다.
Python script를 별도 프로세스로 실행한다. Portfolio의 `src`와 원본 `src`를 같은
서버 프로세스에서 섞어 import하지 않는다.

## 저장 경계 및 품질 규칙

- 신규 원천, 수집 receipt, feature/MSI 계산 결과, 결과 보고서는
  `data/operations/<UTC-time>-<uuid>/{korea,us}/`에 저장한다(gitignored).
- `frontend/public/data/operational-markets.json`만 원자적으로 교체한다.
  기존 `global-markets.json`, `korea-monitor.json`, OOS CSV 및 성능 지표는 그대로다.
- 기본 실행은 캐시 재현이며 `CURRENT`를 발행하지 않는다. 과거 관측을 현재에 이월하지 않는다.
- 모든 필수 원천이 실제 관측된 exact date만 추론한다. 기존 US cleaner의 연구용
  ffill 정책은 재현하되, 신규 출력 날짜 자체에 원천 결측이 있으면 점수를 내지 않는다.
- 시장 휴장일은 exchange_calendars XKRX/XNYS로 판단하며 공개 여유 시간은 한국 6시간,
  미국 12시간이다. 이는 실제 제공처의 관측일이나 공개 시각을 대체하지 않는다.
- 과거 reference의 모든 유효 feature/MSI/threshold가 rtol/atol=1e-9로 재현되어야 한다.
  신규 제공처 응답에 과거 revision이 있으면 자동 수용하지 않는다.
- **미국은 캐시 고정 + 신규 날짜만 이어 붙인다** (`anchor_us_history`). Yahoo가 SPY 조정가격을
  다시 계산해 과거 `SPY_1D_Return`이 최대 1.6e-6 달라지고, 연구 cleaner가 이월한 10/05 신용값이
  나중에 실제 관측되면서 전체 재수집으로는 1e-9 대조가 항상 실패했다. 이제 V1 캐시
  (`data/raw/raw_market_data.csv`) 행은 그대로 두고 캐시 마지막 날 이후 제공처 관측만 붙인다.
  SPY는 마지막 공통일 비율로 캐시 조정 기준에 맞춰(배당 재조정 대응, 일간 수익률 불변) 붙인다.
  겹치는 최근 약 250거래일의 차이가 SPY 상대 1e-5, VIX·신용 1e-9를 넘거나 SPY 기준 변화가 3%를
  넘으면 실제 revision으로 보고 그대로 보류한다. 검토 수치는 export의 `providerRevision`에 남는다.
  2026-11-10 실행: SPY 최대 상대차 1.9e-7, VIX·신용 ~0, 신규 25일, 추론 11/06까지(신용 11/06까지).
- `OPERATIONAL`은 기존 캐시 이후에 수집한 관측일에 한정한다. 기존 캐시 날짜의
  재계산은 `RETROSPECTIVE_INFERENCE`이며 OOS로 주장하지 않는다.
- 실패 시장의 `current`는 null. `lastValid`는 과거 재현 결과로만 표시한다.
  `inferenceSucceeded`는 과거 재현 성공도 포함하므로 최신 성공 여부는 `status`와
  `current`를 함께 확인해야 한다.
- 화면은 정적 연구/운영 export다. 수집 명령만으로 이미 실행 중인 사이트 캐시가
  갱신되지 않는다. 재빌드/재시작해야 하며 자동 스케줄러/배포는 이번 범위에 없다.
- API 키와 exception URL은 export하지 않는다. 원본 credential 파일을 복사하지 않는다.

## 데이터 제공처 및 이용 제한 (2026-11-03 확인)

- [KRX Open API 이용약관](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp):
  인증키·이용승인이 필요하며 지수 라이선스와 데이터 사용 조건은 소프트웨어 라이선스와 별도다.
- [한국은행 ECOS Open API](https://ecos.bok.or.kr/api/): 인증키를 사용한다.
  API 포털이 동적 페이지여서 이번 조회로 상세 재배포 조건을 확정하지 못했다.
- [yfinance 공식 저장소](https://github.com/ranaroussi/yfinance): 도구는 Apache 라이선스지만
  Yahoo 데이터 권리는 별도다. 개인/연구 목적 고지와 Yahoo 이용약관을 확인해야 한다.
- [Moody's DBAA via FRED](https://fred.stlouisfed.org/series/DBAA): Moody's 저작권 및
  재배포 제한을 명시한다. 무료 CSV 접근을 공개 재배포 허가로 해석하지 않는다.
- [Treasury DGS10 via FRED](https://fred.stlouisfed.org/series/DGS10),
  [FRED 이용약관](https://fred.stlouisfed.org/legal/terms/): 원 제공처 표시와 시리즈별
  저작권·허용 용도를 확인해야 한다. FRED 서비스 이용 조건에는 AI 관련 제한도 있다.
  현재 권리 확인 없이 상업적 제공이나 공개 원천 CSV 배포를 승인한 것으로 간주하지 않는다.

공개용 export는 `public_summary()`를 거쳐 원천 가격·금리 값(`availability[].values`,
추론 행의 `price`)을 제외한다. 관측일·출처·가용성·SHA와 파생 Risk/MSI/임계값만 공유한다.
원천 수치와 전체 수집 receipt/보고서는 gitignored `data/operations/`에 보관한다.
이전 구현 단계에서는 로컬 수치 조회를 제공했으며, 공개 저장소 공유 준비 단계에서 원천 수치
재배포를 줄이도록 변경했다. 원천 데이터의 이용 조건 검토가 완료되었다는 의미는 아니다.
원천 CSV를 frontend/public으로 복사하지 않는다. main 병합·배포는 수행하지 않는다.
