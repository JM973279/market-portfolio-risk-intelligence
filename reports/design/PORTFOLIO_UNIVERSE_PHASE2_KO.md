# M/PRI Phase 2 미국 pilot — 권리 gate에서 신규 승인 보류

2026-11-04 (Asia/Seoul). 기준 commit `c00b063ea5221b27aca1f71c975dc7d6b6b613ee`.
로컬 작업 브랜치 `feature/portfolio-universe-phase2`.

## 결과와 지원 수

**신규 실제 승인 0개, 신규 승인 목록 `[]`. 기존 28개만 계속 분석 가능하다.**
검토한 원천에서 신규 주가·기업행위·SPY·VIX·파생 API/배포 artifact까지 포괄하는 무료 공개 사용 권리를 확보하지 못했다.
목표 60~100개 분석 지원은 달성하지 못했으며, 후보 수나 연구 재현을 실제 신규 지원으로 계산하지 않는다.
신규 가격 수집 0회, 신규 공개 승인 스냅샷 0개, 신규 유료 계약/계정/API 구매 0건이다.

| 구분 | 수 | 의미 |
|---|---:|---|
| 검색 카탈로그 | 80 | 기존 28 + 신규 후보 52 |
| full | 28 | 기존 `frozen_v1_only` 범위 보존. 새 권리 승인 아님 |
| partial | 0 | 신규 부분 지원도 공개 승인하지 않음 |
| unsupported | 52 | 공개 권리·가격 receipt·식별 검증·승인 release 미확보 |
| 신규 승인 | 0 | 목표 수에 맞추기 위한 임의 편입 없음 |

기존 17주식+11ETF를 유지하고, 신규 후보 49주식+3ETF를 선정했다. 합계 66주식+14ETF다.
규모 순위나 현재 S&P500 구성 종목의 정본을 주장하는 목록이 아니라 산업별 검토 후보 풀이다.
후보의 상장 상태·MIC·provider class alias·통화·기업행위는 원천 대조 전이며 `identity_status=pending_provider_verification`으로 표시한다.
예를 들어 `BRK.B`를 제공처의 `BRK-B`에 검증 없이 매핑하지 않았다. ETF의 비레버리지·추종대상·분배금 이력도 실제 편입 전에 재확인한다.

## 신규 미승인 종목 전체 목록

| 검토 분류 | 티커 |
|---|---|
| 기술 | AVGO, ORCL, CRM, ADBE, AMD, INTC, CSCO, QCOM, TXN, IBM, AMAT, MU |
| 커뮤니케이션 | NFLX, DIS, CMCSA, T, VZ |
| 경기소비 | TSLA, HD, MCD, NKE, SBUX, LOW, BKNG |
| 필수소비 | COST, PEP, MDLZ, CL |
| 금융 | V, MA, GS, MS, BLK, BRK.B |
| 헬스케어 | LLY, ABBV, MRK, PFE, ABT, TMO |
| 산업재 | GE, HON, UPS, RTX, LMT |
| 유틸리티 | DUK, SO |
| 소재 / 부동산 | LIN / PLD |
| ETF | VTI, DIA, AGG |

52개 모두 `RIGHTS_UNCONFIRMED`, `NO_PRICE_RECEIPT`, `IDENTITY_UNVERIFIED`, `NO_APPROVED_RELEASE`다.
가격 부족·분할 오류·데이터 부정합을 실제로 발견했다는 뜻이 아니다. 새 원천을 수집하지 않았으므로 757개 관측·배당/분할·달력·vintage 대조는 **미실시**다.
종목별 상태는 `PORTFOLIO_PHASE2_CANDIDATE_AUDIT.csv`, 후보 메타데이터는 `data/portfolio_v2/catalog.json`에 기록했다.

## 공식 원천의 사용 권리 검토

아래는 확인한 조건과 승인 판단이며 새로운 사용 허가를 취득했다는 뜻이 아니다.
원천별 URL·검토일·역할·수집 결정은 `data/portfolio_v2/source_rights_review.json`에도 기록했다.

| 원천 | 확인 결과 / 이번 판단 |
|---|---|
| [yfinance 공식 고지](https://github.com/ranaroussi/yfinance) | 소프트웨어 라이선스와 Yahoo 데이터 권리를 구분하고 개인 용도를 명시한다. [Yahoo 직접 약관](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)은 HTTP 999로 본문 확인에 실패했다. 공개 서비스·자동 수집 권한을 추정하지 않고 새 다운로드를 실행하지 않았다. |
| [Alpha Vantage 약관](https://www.alphavantage.co/terms_of_service/), [API 문서](https://www.alphavantage.co/documentation/) | 기본 개인·비상업 범위를 넘어서는 제공에는 별도 서면 조건이 필요하며 daily adjusted는 premium 표시다. 가입·키 발급·유료 호출을 하지 않았다. |
| [Twelve Data 약관](https://twelvedata.com/terms), [용도 안내](https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage) | 외부 표시·파생 결과·재배포의 허용 범위는 plan·거래소·별도 계약과 attribution 조건에 달려 있다. 개인/internal 접근을 M/PRI의 공개 권리로 취급하지 않았다. |
| [Massive market-data 약관](https://www.massive.com/legal/market-data-terms-of-service), [재배포 안내](https://massive.com/knowledge-base/article/how-can-i-redistribute-massives-market-data) | 개인 라이선스의 공개·파생 재배포 제한을 확인했다. M/PRI에 맞는 별도 권리가 없으므로 미승인이다. |
| [Stooq historical 페이지](https://stooq.com/db/h/) | 브라우저 검증 화면만 반환했다. 공개 권리·조정 방식·기업행위 범위를 확인하지 못했고 차단 우회나 다운로드를 하지 않았다. |
| [FRED 약관](https://fred.stlouisfed.org/legal/terms/) | 서비스 조건과 series 원 소유자 조건을 함께 확인해야 한다. 일부 출처 표시 상업적 표시 범위가 설명돼 있으나, 공개 API와 runtime artifact 배포에 대한 포괄 허가로 확대 해석하지 않았다. |
| [Fed 직접 자료 정책](https://www.federalreserve.gov/disclaimer.htm), [H.15](https://www.federalreserve.gov/releases/h15/) | Board 자체 자료는 예외 표시가 없는 한 public domain이며 출처 표시를 요청한다. 직접 금리 원천의 유력한 대안이지만 endpoint·단위·관측일·수정 이력과 기존 계산 정합은 미검증이다. 주가·VIX 권리도 해결하지 않는다. |
| [Cboe 약관](https://www.cboe.com/terms/), [Index feed](https://www.cboe.com/data/global-indices-feed) | 웹 자료의 제한적 개인·비상업 이용과 별도 지수 데이터 licensing을 확인했다. 역사 CSV 다운로드 가능성이나 제3자 open-data 표기를 공개 VIX·파생 서비스 권리 증빙으로 사용하지 않았다. |

기존 snapshot의 source 권리 상태는 여전히 `legacy_unverified`이며 이번에 재승인하지 않았다.
공개 신규 주가와 필수 SPY/VIX/시나리오 의존성 중 하나만 미확인이어도 신규 full을 열지 않는다.
한국 팩터·대체 지수·임의 데이터로 부족한 미국 팩터를 대체하지 않았다.

## 구현과 실제 로컬 분석

- 카탈로그에 후보 52개를 추가하되 서버가 `unsupported`, 모든 capability false, 선택 불가, 공개 권리 미확인을 강제한다. V1 입력 허용 목록은 28개 그대로다.
- `src/portfolio/v2.py`에 별도 bundle 생성·검증·읽기 전용 `.npy` mmap·사전추정 beta·분석/비교 adapter를 구현했다. runtime은 최근 756수익률과 팩터 변화·beta·진단·메타데이터·시나리오를 읽고, 선택한 최대 10개만 공분산을 계산한다. LRU는 한 release로 제한하고 키는 snapshot ID·승인 manifest SHA·registry SHA다.
- 미국 USD만 허용하며, 비교 양측의 snapshot·시장·통화·평가금액을 일치시킨다. 알 수 없는 종목을 삭제하거나 비중을 재조정하지 않는다. partial을 기존 full 전용 What-if 엔진으로 전달하지 않는다.
- 757가격의 정확한 날짜·유일성·정렬·양수·유한성·급변, 756수익률·팩터 pairing·분산·표본·회귀 finiteness를 검사한다. 팩터 제외일은 날짜별 사유·https reference와 실제 null 집합이 정확히 같아야 한다. 임의 coverage 비율·ffill·clipping은 없다.
- `revision_diff()`는 겹치는 관측의 정확한 수정·추가·삭제를 보고하고 원본을 수정하지 않는다. 서로 다른 신규 실제 vintage를 수집해 비교한 것은 아니다.
- 공개 bundle 생성에는 여섯 의존성(가격·기업행위·market/rate/volatility factor·scenarios)의 검토된 권리 ledger가 필요하다. 저장·공개 파생 제공·artifact 배포 및 해당 종목/팩터/시나리오 범위를 모두 확인한다. 달력·식별·기업행위·정밀도·revision·팩터·시나리오 검토 reference도 필수다. 실제 원천과 증빙의 타당성은 별도 검토이며 boolean만 자동 생성하지 않는다.
- 별도 `/api/portfolio/v2/analyze`, `/compare`는 registry에 승인된 release와 manifest SHA가 있어야 동작한다. 현재 registry는 비어 있어 `409 NO_APPROVED_RELEASE`를 반환한다. 누락/손상된 V2 파일은 V2에만 오류를 내고 V1 `/health`와 분석은 유지한다. HTTP 요청에서 외부 수집을 하지 않는다.
- 공개 원천이 없으므로 신규 가격/팩터 adapter나 공개 V2 UI 승격을 실행하지 않았다. 승인 데이터가 생긴 뒤 source별 receipt·실제 기업행위 대조·완전한 portfolio capability 판정과 UI snapshot 전환을 검증해야 한다.

기존 실제 28개 자료로만 `research-v1-replay-20261104` 연구 bundle을 생성했다.
파일은 gitignored `data/portfolio_expansion/research/`에 있으며, 공개 release 경로에 연구 bundle을 생성하거나 공개 API로 읽는 것을 차단한다.
커밋에는 원천/returns/beta 연구 파일을 넣지 않고 `PORTFOLIO_PHASE2_RESEARCH_REPLAY.json`에 SHA와 연구 전용 상태만 기록했다.
이것은 신규 승인 snapshot이 아니라 **기존 실제 데이터의 별도 로컬 재현**이다.

재현:

```sh
.venv/bin/python scripts/portfolio_phase2_replay.py --snapshot-id another-research-id
.venv/bin/python scripts/benchmark_portfolio_phase2.py --output /tmp/phase2-resources.json
.venv/bin/python -m pytest -q
```

기존 snapshot ID 덮어쓰기는 거부한다. factor policy의 DGS10 746쌍은 기존 날짜/기존 자료의 재현에만 사용했다.
신규 source의 다른 결측일에 같은 예외를 자동 적용하지 않는다. 신규 실제 종목의 승인·분석 테스트 수는 0개다.

## 테스트와 보존

- 전체 Python **138개 통과**. 기존 Starlette/httpx deprecation 경고 1개. V1 golden은 수정하지 않았다.
- 기존 28개 단독 포트폴리오, before/after 전체 HTTP 응답 및 What-if golden 비교 통과. 변동성 23.38% → 16.94%, NVDA 위험기여 30.43% → 28.37%, Stress 3개·What-if 10행 유지.
- V2 연구 adapter는 실제 V1 예제의 전체 대응 금융 필드·순서·반올림을 재현한다. 공분산/위험기여는 NumPy 독립 계산, 베타는 절편을 포함한 `lstsq`와 대조했다. current/proposed는 각각 별도 analyze와 동일하다.
- 권리 미확인·라이선스 종목 범위 불일치·연구 bundle 공개 차단·가격 누락/중복/비정렬/0/급변·팩터 NaN/Inf·제외일 증빙 부재·snapshot/통화 불일치·unknown 종목·원천 파일 손상/registry 누락 격리를 검증했다.
- ESLint·TypeScript·차트·데이터 연동·Render 설정 검사·production build 통과. Chromium에서 390/1280px, KR/EN 회사명, 전각 티커, 키보드, 입력 결과 무효화, 미승인 사유·선택 차단 통과.
- `data/portfolio/` 원본 5개와 SHA manifest, 기존 Portfolio 계산 엔진, 시장 Frozen V1/운영 데이터·모델·threshold, `render.yaml`, main을 변경하지 않았다.

## Render Free 512MB 기준 로컬 리소스 검증

**Render 실제 검증/확대 용량 승인 아님.** 새 서비스나 배포 없이 Linux 로컬에서 API 1worker·BLAS 1thread로 측정했다.
API subprocess와 V2 연구 worker에 `RLIMIT_AS=512MiB` 가상주소 상한을 걸었다. 이는 Render의 RSS/cgroup 512MB와 다르다.
이 호스트의 cgroup `memory.max`는 `max`여서 실제 512MB cgroup/Render CPU·OOM·플랫폼 overhead를 모사하지 못했다.
기존 실제 28가격 열 + 80메타데이터 카탈로그이며, 신규 승인 60~100가격 열의 확대 부하는 실행할 수 없었다.

| 최종 성공 실행 | API HTTP V1 | V2 로컬 연구 adapter |
|---|---:|---:|
| peak RSS | 137.836 MiB | 123.027 MiB |
| 첫 analyze / 첫 bundle load | 102.317 ms | 1.984 ms |
| 동시4 analyze p95 | 87.019 ms | 62.517 ms |
| 동시4 compare p95 | 184.083 ms | 121.471 ms |
| 동시4·최대10보유 analyze p95 | 113.167 ms | 75.303 ms |
| 동시4·최대10보유 compare p95 | 218.286 ms | 133.757 ms |

동시1/2/4·analyze/compare·최대10보유 각각 12요청씩 실행했다. 표본이 작아 p95는 해당 표본의 최댓값과 같다.
모든 요청의 예제 금융 결과 또는 최대10개 입력 보존을 확인했다. 상세 원자료는 `PORTFOLIO_PHASE2_RESOURCES.json`이다.
V2 값은 오프라인 adapter이고 공개 V2 HTTP의 성능 측정이 아니다. Next 서비스 메모리도 포함하지 않는다.

**실패 관측도 보존:** 최대10보유를 추가한 초기 512MiB 가상주소 제한 실행에서 HTTP 500이 한 번 발생했다.
제한 없는 별도 로컬 API의 동일 10개 analyze/compare는 200이었고, 서버 로그 수집을 추가한 재실행에서는 위 전체 capped workload가 통과해 원인을 확정하지 못했다.
이 일시 실패를 해결된 것으로 주장하지 않으며, 실제 데이터 확대 전 반복 부하/오류 로그·진짜 cgroup·플랫폼 검증이 필요하다.
위 숫자를 Render 지연시간 보증이나 신규 80종목 용량 승인으로 사용하면 안 된다.

## 다음 조치와 대안

1. 기존 계약 또는 무료로 명시 승인된 source의 서면 증빙/공식 허용 조건을 확보한다. 가격·배당/분할·저장·수정 이력·공개 파생 API·배포 artifact·SPY/VIX·시나리오 의존성까지 범위를 확인해야 한다. 이번에 계약 문의 메시지 발송·가입·유료 구매를 하지 않았다.
2. 사용자가 이미 허가받은 파일을 제공할 수 있다면 별도 연구 경로에 receipt와 원본 SHA를 보관하고, 757개 실제 거래일·기업행위·revision을 검증한다. 기존 28개 원본을 새 vintage로 덮어쓰지 않는다.
3. Fed 직접 H.15는 무료 rate 원천 대안으로 독립 adapter를 검증할 수 있다. 그러나 주가/VIX가 해결되기 전에는 이것만으로 신규 full을 승인할 수 없다.
4. 권리가 확보될 때까지 기존 28개 공개 분석과 52개 unsupported 검색을 유지한다. 새 종목 가격·동결 데이터 복제·한국 팩터·임의 proxy로 목표 수를 채우지 않는다.
5. 실제 승인 source를 수집한 뒤 종목별 full/partial/unsupported를 다시 판정하고, 신규 V2 API 및 UI snapshot 전환·장애 격리·1/2/4 부하를 실제 60~100개로 검증한다. 실제 Render/cgroup 검증과 배포는 별도 승인 범위다.

로컬 feature 브랜치에만 커밋한다. **push·main/PR 병합·Render 재배포·유료 서비스 생성은 수행하지 않는다.**
