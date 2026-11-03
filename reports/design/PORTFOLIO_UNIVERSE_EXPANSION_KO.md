# Portfolio 미국·한국 유니버스 확장 설계

기준일 2026-11-03. 브랜치 `feature/portfolio-universe-design`, 기준 commit `97e78366a026e9221740526087ef8082a891fa28`.
이번 작업은 조사·설계·로컬 크기 실험뿐이다. **신규 실제 종목 추가0, 신규 시세 수집0, 기능 코드 변경0, Render 설정/배포 변경0, GitHub push0**.
기존 미추적 배포 보고서는 그대로 보존했다. 아래 경로·API·판정 정책은 명시한 현행 항목을 제외하면 구현 제안이다.

## 결론과 권장 순서

**28개 고정 V1을 그대로 유지하면서, 별도 버전의 검증된 데이터 묶음과 검색 카탈로그를 추가하는 방식**을 권장한다.
미국100개 내외 pilot → 현재 S&P500 구성 증권 전체와 승인 ETF → 한국20~30개 pilot → KOSPI200과 승인 ETF 순이다.
구성 종목 카탈로그 포함과 분석 지원을 구분한다. 목록에 있어도 실제 가격·팩터·권리 검증이 안 되면 선택/분석을 허용하지 않는다.
최종 지원 수는 수집·검증 이후에만 확정하며, 지금 500/200개 모두 분석 가능하다고 약속하지 않는다.

가장 큰 선행 조건은 공개 서비스에서 사용할 데이터의 권리와 한국 전용 팩터/통화/달력이다.
일봉 수익률 행렬의 크기 자체는 작다. 512MB에서 유니버스 크기와 보유 수 제한을 혼동하지 않는 것이 중요하다.
**포트폴리오 보유 제한10개는 유지**하고 검색 대상만 확대한다.

## 1. 현행 구조 전수 조사

| 영역 | 현행 코드/데이터 | 확장 시 문제 |
|---|---|---|
| 종목 registry | `src/portfolio/universe.py`, `data/portfolio/universe.csv` | 17주식+11ETF, 28개. ticker/name/type/sector/asset_class만 있고 국가·통화·출처·종목별 날짜 없음 |
| 원천 수집 | `src/portfolio/data.py` | Yahoo auto_adjust 가격+VIX, FRED DGS10. 기본2018-01-01. `main()`은 기존 raw 경로에 저장하므로 확장 수집에 그대로 실행 금지 |
| 품질 점검 | 같은 파일 `check_quality()` | SPY 최근756일의 자산별 결측 개수만 점검. split/dividend/거래정지/통화/상장기간·제공처 vintage 검증 부족 |
| snapshot 생성 | `src/portfolio/snapshot.py` | 모든 자산+VIX+DGS10이 완전한 마지막 날짜를 전역 as_of로 사용. 신규 결측 종목 하나가 전체 기준일을 과거로 당기거나 생성 실패시킬 수 있음 |
| 달력/가격 | snapshot은 SPY 관측일로 정렬, 가격 소수4자리 | 한국 휴장일/시간대/저가주 정밀도를 미국 규칙으로 일괄 처리할 수 없음. 새 가격 반올림 정책을 별도 검증해야 함 |
| Hidden Risk | `analytics.py` | 최근757가격→756수익률, 연252, 보유자산만 공분산/상관, 비중 기반 위험기여. pandas pairwise 결측 허용을 새 데이터의 승인 근거로 사용하면 안 됨 |
| 팩터 | `factors.py` | SPY 일수익률, DGS10 일차분×100bp, VIX 일차분pt. 각각 단변량 회귀. 최초 load에서 전체 등록종목 베타를 추정하고 LRU cache |
| 유의성 | 같은 파일 | t절댓값2 기준, 완전적합은 t=null/유의함 true. 낮은 t는 결과 불확실성이며 데이터 지원 불가와 다름 |
| Stress | `scenarios.py`, `stress.py` | 2018 이후 고정 history에서 미국3팩터의 10거래일 극단 충격. beta×shock, 자산별 USD cents 반올림. 시나리오 합산 금지 |
| What-if | `whatif.py` | 동일 금액 두 번 분석. factor_exposure/stress가 존재한다고 가정하므로 부분 지원 응답을 그대로 전달하면 안 됨 |
| API | `schemas.py`, `api.py` | 지원 ticker가 module import 시 frozenset으로 고정. 최대10개, 합100±0.01%p, 양수금액. `/universe`, `/scenarios`, `/analyze`, `/compare` |
| 무결성 | `readiness.py`, `config/portfolio-snapshot.sha256.json` | 요청마다 원본5파일 전체 bytes hash. CSV나 universe를 덧붙이면 현재 gate가503 반환함. 확장 artifact를 별도 manifest로 관리해야 함 |
| UI | `portfolio-panels.tsx`, `portfolio-api.ts` | native select가 전체 목록 렌더링. ticker·회사명 검색 없음. 명시적 통화 없는 USD 평가금액/손실 필드 |
| 운영 | `render.yaml`, `server.py`, `next.config.ts` | API1worker/BLAS1, Next 서버proxy, Free512MB 각1개, 자동배포off, 고정파일 읽기. 수집 scheduler 없음 |

현재 snapshot은2018-01-02~2026-10-23, 가격2215행×28열, 추정756거래일(2023-10-19~2026-10-23).
가격/VIX의 추정구간 결측0. 757가격일에 DGS10 결측5개, 차분 후 금리 회귀 가능일746개다.
이 결측은 기존 정책상 이어 쓰지 않고 금리 회귀에서만 제외한다. 전체 history의 결측16개와 혼동하지 않는다.

시장 Risk Score/MSI 파이프라인은 `market_engine/operations/`의 **별도 Frozen V1 추론**이다.
Portfolio beta·stress 계산은 해당17개 Feature 모델을 쓰지 않는다. 이를 섞거나 시장 모델의 source/model/threshold를 확장 목적으로 바꾸지 않는다.

## 2. 기존 결과 보존과 버전 경계

1. `data/portfolio/`5파일, manifest, 기존28개 route/schema/계산의 기본 동작을 그대로 둔다.
   기존 API 요청은 현재 고정 snapshot을 반환한다. 원본 raw를 덮어쓰는 기존 CLI를 확장 작업에서 실행하지 않는다.
2. 후보 원천/receipt는 별도 gitignored 경로에 append-only 저장한다. 자격을 통과한 공개 허용 artifact만 버전 고정한다.
   예: `data/portfolio_expansion/raw/<run_id>/`, `data/portfolio_v2/releases/<snapshot_id>/`.
3. 확장 화면/API는 명시적인 `snapshot_id`, `market`, `base_currency`, `methodology_version`을 사용한다.
   예시 새 경로 `/api/portfolio/v2/catalog`, `/analyze`, `/compare`는 설계안이며 현재 존재하지 않는다.
4. 새 수집이 기존28개 가격의 역사적 revision을 바꾸더라도 기존 V1을 덮어쓰지 않는다.
   기존 dataset과 동일 입력은 기존 결과를 그대로 재현하고, 새 vintage 결과는 별도 결과임을 표시한다.
   V2가 반드시 V1과 다른 vintage에서도 같은 수치를 내야 한다고 강제하지 않는다.
5. 오래된 snapshot·신규 승인 snapshot·수집 실패를 UI에 구분하고 입력/snapshot 변경 즉시 기존 분석을 무효화한다.
6. 새 종목 실패는 해당 종목/해당 capability에만 반영한다. 건강한 기존28개를 포함한 전체 서비스가503이 되지 않게 registry를 격리한다.

보존 기준: 기존28개 모든 supported tickers, 파일 SHA, 예제 전체 응답 필드의 수치/순서/반올림이 동일.
before 변동성23.38%, TLT30% after16.94%, NVDA 위험기여30.43→28.37%, 고정 Stress3개/What-if10행을 기준으로 한다.
같은 이름의 ETF라도 신규 분류체계 때문에 기존 sector concentration 결과를 자동 변경하지 않는다.

## 3. 종목 master, 지수 membership, ETF 선정

- 단순 ticker 대신 국가/거래소/보통·우선주/주식 class를 구분하는 안정 ID를 둔다. ISIN 등 확보 가능한 식별자와 기간별 provider_symbol 매핑을 기록한다.
- 예: 한국005930을 숫자로 바꾸지 않고 문자열로 보존하고 `.KS` 같은 provider suffix는 식별자와 분리한다.
  미국 점/하이픈 class 표기 변경은 검증된 alias 표로 처리한다. 예시는 식별 체계 설명이며 이번 신규 편입 승인이 아니다.
- `name_ko`, `name_en`, `aliases`, `country`, `MIC`, `quote_currency`, `asset_class`, `ETF 여부`, 상장·상폐·거래정지 상태를 기록한다.
- `index_membership`에 index_id/source/observed_at/effective_from/to를 저장한다. 회사 수와 증권 수를 구분한다.
  S&P 공식 페이지 확인 시500개 회사/503개 구성 증권이 표시되므로 목록 길이를500으로 하드코딩하지 않는다.
  [공식 S&P500](https://www.spglobal.com/spdji/en/indices/equity/sp-500/)
- 현재 구성으로 과거를 분석하면 survivorship bias가 생긴다. 초기 제품은 **현재 구성 종목 대상 현행 위험 분석**으로 표시하며
  과거 당시 구성 종목의 전략 OOS 검증인 것처럼 소개하지 않는다.
- ETF 보유 목록은 cash·선물·샘플링·리밸런싱 시점이 달라 지수 공식 구성 목록의 정본으로 간주하지 않는다.
- 주요 ETF는 시장별 승인 목록으로 한정: 초기에는 비레버리지/비인버스, 충분한 일봉·기업행위 이력, 분류·추종대상 확인 종목 우선.
  유동성 기준의 실제 수치/선정일은 데이터 조사 후 명시한다. 지금 임의 ETF를 실제 지원으로 추가하지 않는다.
- ETF 내부 holdings look-through는 현재 없음. 확장해도 자산 수준 sector/class라는 한계를 유지한다.

## 4. 데이터 소스별 조건과 권장안

아래는 기술/이용 조건 조사이며 공개 서비스 이용 허가를 취득했다는 뜻이 아니다.
다운로드 가능성, 가격 계산 적합성, 제3자 제공/파생 지표 공개 권한을 따로 확인한다.

| 용도/제공처 | 유용성 | 제한과 채택 조건 |
|---|---|---|
| S&P DJI / 승인된 index data vendor | S&P500 기준일별 공식 구성·class·변경 | 구성/지수/파생 정보의 허용 용도를 계약별 확인. 공식 factsheet나 ETF holdings 공개를 전체 database 재배포 허가로 해석하지 않음 |
| KRX Data Marketplace / Open API | KOSPI200 구성, KR 주식·ETF/지수·기업행위 후보 | key·승인 필요, endpoint별 실제 항목/시작일 확인. 약관의 비상업/제3자 제공 제한 때문에 공개 분석 결과의 허용 범위는 별도 확인 |
| Yahoo/yfinance | 기존 US source와 일봉 수집 경로 재사용 가능, KR `.KS` 후보 | 비공식 연계, 차단·429·revision·기업행위 검증 필요. 도구 라이선스가 데이터 권리를 주지 않음. 공개 서비스용 기본 허가가 확인된 소스로 취급하지 않음 |
| 금융위 공공데이터 주식시세 | 한국 공식 종가/기본정보 교차 대조 후보 | 현재 카탈로그는 공공누리4유형 및 무단 제3자 제공/재배포 제한을 명시. 일반 종가만으로 배당·분할 조정의 적합성은 확정 불가. 무료라고 공개서비스 원천으로 바로 채택하지 않음 |
| FRED DGS10 / 원 제공처 Fed H.15 | 현재 미국10년 금리, 일별% 단위 | release/관측일·수정 이력·휴장 차이 기록. FRED 이용 조건 및 series별 권리 확인. 가격처럼 ffill하지 않음. 원 Fed H.15 직접 소스도 별도 검증 후보 |
| 한국은행 ECOS | 한국 국고채10년 및 USD/KRW 후보 | 인증·series/item·단위·일별 주기·출판시각 실제 확인. 포털 동적 페이지로 상세 재배포 조건은 이번에 확정하지 못함 |
| Alpha Vantage | API 규격이 있는 US 가격 대안 | 일반 무료25호출/일, daily adjusted는 premium 표시. 550종목 매일 갱신용 무료 대체재로 가정하지 않음. 권리/가격은 도입 시 재확인 |
| pykrx/FinanceDataReader 등 wrapper | KRX/Yahoo 등을 연결하는 구현 도구 후보 | 원천 권리·안정성·수정가격 책임을 대신하지 않음. 이번에 새 의존성 도입하지 않음 |

근거:
- [S&P/Dow Jones EOD·Historical·Derived licensing 안내](https://www.cmegroup.com/articles/faqs/sp-indices-and-dow-jones-indices-licensing-faq.html).
- [KRX Open API 약관](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp): key당 일10,000회, 이용기간/비상업 목적·출처 표시·제3자 제공 제한을 확인했다.
- [금융위 주식시세 카탈로그](https://www.data.go.kr/data/15094808/openapi.do): 2026-10-28 수정 안내/라이선스를 공식 페이지 HTTP 조회로 확인했다.
- [yfinance 공식 고지](https://github.com/ranaroussi/yfinance): 개인·연구 목적 고지, Yahoo 약관 별도. 단순 adjusted close의 존재가 공개 사용 권리를 보장하지 않는다.
- [FRED DGS10](https://fred.stlouisfed.org/series/DGS10), [FRED 이용 조건](https://fred.stlouisfed.org/legal/terms/), [ECOS](https://ecos.bok.or.kr/api/).
- [Alpha Vantage 지원 한도](https://www.alphavantage.co/support/), [Daily adjusted 문서](https://www.alphavantage.co/documentation/#dailyadj).

권장: 무료/공개 source로 작은 비공개 검증 pilot을 진행할 수 있더라도 **공개 rollout은 파생 분석 결과의 전송·보관·공개 허용 범위 확인 후**다.
권리 미확인 source를 다른 무료 wrapper나 ETF holdings로 우회하지 않는다. 라이선스 비용이 필요하면 별도 보고하고 자동 결제하지 않는다.

## 5. 신규 수집·품질 gate

수집은 로컬/승인된 외부 배치에서 수행하고 Render HTTP 요청에서는 외부 가격 API를 호출하지 않는다.
국가별 장 마감/공표 완료 후 날짜 범위를 정해 batch25~50개, 제한된 동시성1~2부터 시작하는 제안이다.
제공처 공식 한도가 우선이며429 backoff/재시도 한도/일별 quota checkpoint를 둔다.
KRX의 일자별 전체종목 endpoint를 쓸 수 있는지 먼저 확인한다. 종목×일자 호출을 무작정 실행하지 않는다.

각 asset/팩터에 관측일(local date), source published_at(실제 제공 시), retrieved_at(UTC), snapshot_as_of,
built_at, valid_from/to, source_id/안전한 URL, 라이선스 기록, 조정 방식, 파일SHA, revision diff, 수집 code/dependency 버전을 기록한다.
published_at이 제공되지 않으면 null과 미제공 이유로 둔다. 조회시각을 발표시각으로 만들지 않는다.

승인 gate 제안:

1. 심볼/거래소/통화/종목명/상장기간·지수 membership 정합, source/공개 사용 권리 확인.
2. 해당 시장의756개 일간 수익률을 계산할 최소757개의 유효 가격.
   날짜 중복/비정렬, 0이하 가격, 비유한 값, 기업행위 설명 없는 급변, 거래일 누락은 거부/격리한다.
3. 분할·병합·배당·상폐·종목코드 변경은 조정 source와 corporate action 기록을 대조한다.
   이벤트가 확인된 큰 수익률을 임의로 clipping하거나 일반 허용 오차로 숨기지 않는다.
4. 각 시장의 실제 휴장일과 관측 누락을 구분한다. 휴장일에 0% 수익률을 만들거나 보간·이월하지 않는다.
   source가 거래정지 기간을 평탄 가격으로 반환한 경우도 정상적인 신선한 관측으로 자동 승인하지 않는다.
5. 팩터별 동일 날짜 표본 수/제외일 사유/분산/회귀 finiteness 검증. n>2는 수학적 필요조건일 뿐 충분한 경제적 표본 기준이 아니다.
   초기 full은 같은756일 target과 사전에 확인한 팩터별 휴장/공표 정책을 충족해야 한다.
   기존 DGS10 휴장 제외는 보존하되 새 시장·새 결측에 일괄 면책으로 적용하지 않는다. 임의95% coverage 기준은 만들지 않는다.
6. 저가주의 소수4자리 반올림으로0/수익률 왜곡이 생기지 않는지 확인한다. 기존28개 반올림은 그대로,
   신규 artifact는 provider 정밀도/조정 방식을 버전화하고 수익률 영향 시험 후 채택한다.
7. 같은 receipt 재생이 동일 결과를 내고 미래 데이터가 과거 beta/기간에 섞이지 않아야 한다.
   revision은 새 artifact로 격리한다. 시장 Frozen V1의 미국 revision 허용 기준과는 별개이며 이를 완화하지 않는다.

ETF 분배금·환헤지·레버리지·통화 노출, IPO3년 미만, 상폐/정지, provider rate limit 실패를 별도 reason code로 둔다.
현재 구성에 있어도 이 gate 미통과면 분석 지원 목록에 추가하지 않는다.

## 6. 지원 상태와 화면/API 계약

단일 ready bool 대신 capability와 사유를 노출한다.

| 상태 | 허용 | 금지/안내 |
|---|---|---|
| full | 승인 snapshot에서 Hidden Risk/세 팩터/세 Stress/같은 기준 What-if | 유의하지 않은 beta를 유의함처럼 표시하지 않음 |
| partial | 검증 가능한 범위만. 예: 가격은 완전하지만 금리 factor 미검증이면 Hidden Risk·검증된 factor만 | 누락 Stress는 N/A, 전체 완료 badge 금지. 비교는 양측 동일조건으로 계산 가능한 지표만 |
| unsupported | 검색/기본 메타데이터·필요한 데이터/사유 확인 | 분석 선택 disabled 또는 명시적 제한. 미수집·짧은 이력·권리 미확인·통화 미지원 등 |
| historical/stale | 마지막 검증 snapshot 날짜를 선택해 과거 분석 가능 | 과거 값을 최신 운영 결과로 이월 금지 |

allocation 자체는 입력을 보여주는 것이므로 데이터 기반 Hidden Risk 가능과 구분한다.
잘못된 자산을 조용히 빼거나 나머지 비중을100%로 재조정하지 않는다.
부분 지원이 들어간 portfolio의 capability는 각 asset 상태뿐 아니라 **공통756일/통화/팩터/시나리오**로 다시 판정한다.
What-if 양측 중 한 쪽만 계산 가능하면 해당 지표 delta는 N/A다. 기존 `compare_analyses()`를 null 데이터로 호출하지 않는다.

v2 metadata 제안: asset_id, display_symbol, name_ko/en, market, currency, membership_as_of,
first/last_valid_observed_at, retrieved_at, published_at(nullable), snapshot_id/as_of, approved_at,
coverage/required_count, factor_pair_counts, capabilities, reason_codes, source/license references.

검색 UI: ticker exact/prefix → 회사명 prefix/부분문자열, 국가·주식/ETF·지원상태 필터.
한국6자리코드/한글·영문 별칭, 미국class alias를 지원한다. 문자열NFKC/대소문자 정규화하고 동명이종은 거래소·통화로 구분한다.
최대 약800개 catalog는 가격을 제외한 작은 static JSON으로 받아 클라이언트 검색하는 안을 우선한다.
각 입력행에800개 option을 렌더링하지 않고 접근 가능한 combobox로 상위20~50개 결과만 표시한다.
키보드/스크린리더·KR/EN·모바일·기존 입력변경 무효화를 유지한다. 실제 새 catalog 크기는 생성 후 측정한다.
표시 날짜는 `가격 관측일`/`수집 시각`/`분석 snapshot 기준일`을 구분한다.

## 7. 한국 팩터·통화와 혼합 포트폴리오

미국은 기존 SPY/DGS10/VIX 및 기존 방식 유지. 한국 단독 포트폴리오는 별도 methodology로 검증한다.
권장 후보는 **KOSPI200 계열 benchmark / 국고10년 일별 변화(bp) / VKOSPI 변화(pt)**다.
확정된 factor가 아니며 수집 가능성과 기업행위/price-vs-total-return 정합·source 권리를 먼저 검증한다.
KOSPI200 TR을 확보할 수 없으면 price index 기준 차이를 명시하고 검증한다. ETF를 proxy로 쓰는 경우 별도 proxy 방법론이며 조용히 대체하지 않는다.
시장 모델이 보유한 한국3년 금리를 이름만10년으로 바꿔 사용하지 않는다. Portfolio 한국 factor adapter가 시장 Frozen V1 코드를 변경하지 않는다.

- KR calendar는 XKRX 기준, USD 단독은 기존 US calendar. 휴장일로 인한 row 합집합에 ffill해서 수익률을 만들지 않는다.
- KR 장 마감은 US 같은 날짜 종가보다 먼저다. 시차를 고려하지 않은 same-date beta는 미래 정보를 사용할 수 있다.
  한국을 US factor로 회귀하는 모델은 별도 연구이며 초기 KR local 모델에 적용하지 않는다.
- KR-only의 base는KRW, US-only는USD. API `value_usd`/`loss_usd`에 KRW를 넣지 않는다.
  v2는 value_amount/base_currency/loss_amount 및 통화별 반올림 adapter를 제안한다. 기존 USD cents 반올림과 결과는 그대로다.
  beta×shock 계산식 자체는 유지하고 단위/표시/통화 반올림을 분리 검증한다.
- 한국10일 충격은 승인된 KR 장기 reference에서 기존 min/max 규칙을 같은 단위로 적용해 별도 scenario_id/reference/version을 만든다.
  미국 충격 숫자를 한국 역사 충격으로 표시하지 않는다. 자료가 부족하면 해당 Stress는지원불가다.
- 미·한 혼합은 초기 범위에서 차단/국가별로 분리한다. 단순 KRW/USD 가격이나 손실 합산은 금지한다.
  후속에는 통일 평가시점·실제 FX·기준통화 수익률·환헤지 상태·FX 충격·공통 공분산을 별도 검증해야 한다.
  FX를 KRW per USD로 정의하면 USD 평가 한국자산 가격은 P_KRW/FX이므로 그 시계열로 수익률을 계산한다.
  FX를 현재 한 시점 값으로만 곱해 과거 수익률을 환산하지 않는다.

## 8. 리소스 실측과 512MB 예산

재현: `.venv/bin/python reports/design/benchmark_portfolio_universe.py`.
`PORTFOLIO_UNIVERSE_RESOURCE_BENCHMARK.json`에 원자료가 아닌 크기/시간/메모리 결과를 기록했다.
기존28개 실제 시계열을 반복 복제한 **부하 전용 열**로 실험했고 등록 종목/신규 금융 결과로 사용하지 않았다.
원본 CSV/manifest를 수정하지 않았고 격리 임시 파일은 삭제된다.

| 열 수 | CSV MiB(2215행) | 756수익률 frame MiB | cold caches 초 | warm 분석+exposure 초 | process peak RSS MiB |
|---:|---:|---:|---:|---:|---:|
| 28 | 0.51 | 0.17 | 0.0838 | 0.0046 | 118.2 |
| 100 | 1.78 | 0.58 | 0.2681 | 0.0048 | 134.7 |
| 550 | 9.65 | 3.18 | 1.4845 | 0.0046 | 153.6 |
| 800 | 14.02 | 4.62 | 2.2535 | 0.0048 | 173.2 |

各1回のローカル単一process実験。peakはimport・列生成・CSV・cacheを含む。HTTP server/Stress/What-if/同時接続全体の測定ではない。
위 일본어가 아닌 의미: 각 규모1회, 로컬 단일 프로세스이며 peak는 import/열생성/CSV/cache를 포함한다.
한국 달력·짧은 이력·여러 snapshot·FX·실제800개 기업행위와 Render0.1CPU/cgroup 제약을 모사하지 않는다.
실험마다 기존 실제 before 변동성23.38%를 확인했지만 전체 기존응답 회귀 검증을 대신하지 않는다.

해석/예산(설계 목표, 측정 보장 아님):

- NumPy float64 기준800×756은4.62MiB. 현재 returns cache와 factor_data asset_returns가 중복이면약9.24MiB.
  가격2215×800만 약13.52MiB이며 pandas/CSV파서·일시 복사·imports는 별도다.
- 기존 로컬 API 약140MiB, Next약278MiB 기록은 별도 baseline이다. 새800열 cache의 추가 비용만 고려하면
  API약200~320MiB의 계획 범위를 잡을 수 있으나 합산 추정이며 실제 동시부하를 보증하지 않는다.
- API 목표 steady RSS≤350MiB, 부하 peak<400MiB를 출시 전 gate 제안으로 둔다. 512MB 외 platform overhead·cgroup 측정 필요.
  초과하면 batch/동시성/cache를 줄이고 공개 확대를 멈춘다. 자동 유료 전환은 하지 않는다.
- cold2.25초를 Render latency로 인용하지 않는다. 낮은 free CPU와 Python 회귀 반복은 첫 요청30초 제한을 넘길 수 있다.
  offline beta/scenario 사전 계산과 첫 요청 로딩 최소화를 우선한다.
- 550/800은 수용량 산정을 위한 값이며 실제 구성/지원 종목 수가 아니다. 실측 catalog와 파일 크기는 실제 승인 후 재산정한다.

권장 runtime:

1. 기존 V1 번들은 고정. v2는 시장별756일 returns + factor moves + 사전추정 beta/진단 + metadata/scenario만 배포한다.
   full2215일 raw는 배치 저장소에 남긴다. NumPy `.npy`/mmap은 현행 NumPy로 처리 가능하다.
   Parquet/Arrow는 선택지지만 추가 의존성/메모리 비용을 비교하기 전 기본 도입하지 않는다.
2. 선택된 최대10개에만 DataFrame/covariance/correlation/portfolio t를 계산한다. 전체800종목 NxN 공분산을 요청마다 계산하지 않는다.
3. cache key는 snapshot_id/market/currency/methodology를 포함하고 활성 release 수를 제한한다.
   새 artifact hash를 streaming 검증한 뒤 read-only로 적재한다. 기존 V1 요청별 gate는 그대로 둔다.
   신규 artifact 전체 CSV를 요청마다 `.read_bytes()`하면 동시 요청마다14MiB 복사/디스크 읽기가 생기므로 피한다.
4. API1worker/BLAS1 유지, 무제한 요청 thread/수집 thread를 만들지 않는다. 부하 시 제한된 concurrency와 명시적 재시도 응답을 검토한다.
5. frontend는 catalog/지원상태만 받는다. 전 종목 가격·회귀 cache를 browser/HTML에 포함하지 않는다.
6. 신규 scheduler/worker/DB/유료 디스크를 만들지 않는다. Free filesystem은 재시작 시 소실되어 운영 수집 저장소로 부적합하다.
   외부 배치→승인 artifact→명시적 배포 방식이 초기안이다.

[Render Free 정책](https://render.com/docs/free): 휴면/ephemeral filesystem/공유750시간/빌드·대역폭 한도를 고려한다.
기존 API/웹 두 개 안에서 확장을 검증하며 새 상시서비스를 추가하지 않는다. 데이터 파일은 Next browser로 전달하지 않아 bandwidth를 줄인다.

## 9. 단계별 구현과 승인 기준

아래 일수는 개발 작업 추정이며 라이선스·API 신청·source 장애/원천 수집 대기 시간은 제외한다.

| 단계 | 범위 | 통과 조건 | 예상 작업 |
|---|---|---|---|
| 0 조사/설계 | 본 문서·용량실험 | 기존 V1 무변경, source·KR방법론 미확정 사항 명시 | 이번 완료 |
| 1 기반 | 버전 registry, receipt/gate, catalog 검색, capability API, V1 golden 분리 | 실제 source 허가 범위 확인, 기존28 전체 응답 동일, unsupported 선택 차단 | 2~3일 |
| 2 미국 pilot | 기존28 유지, 검증 후 총60~100개 내외 후보/ETF |757가격·기존 US팩터·revision/기업행위/각 endpoint실제 검증, memory/latency gate | 2~3일 |
| 3 미국 확대 | 승인된 현재 S&P 구성 증권+ETF, 약550열 planning | index정본/vintage, 누락·IPO·상폐 개별상태, full 지원 수 보고 | 2~4일 |
| 4 한국 pilot | KR20~30개 후보/ETF, KRW-only | 한국 factor/calendar·금액 adapter·공개권리·실제 원천검증, KR scenario재현 | 3~5일 |
| 5 한국 확대 | 승인 KOSPI200+ETF, 총약800열 planning | 두시장 격리, 부분지원·검색·동시부하·장애/rollback검증 | 2~3일 |

전체 순차개발11~18일 정도의 계획치다. 700개 모두full 보장일정이 아니다.
권리/팩터 미확정 상태에서는 단계1의 구조 작업·비공개 테스트를 진행할 수 있어도 공개 신규 지원은 보류한다.
미·한 혼합/ETF look-through/실시간수집/새 시장 Risk모델은 이 계획의 초기 구현 범위가 아니다.

## 10. 출시 전 검증과 남은 결정

- V1 전체28개/기존5개 예제/요청422/숫자·순서·반올림·SHA 회귀. 같은 버전 What-if current=별도analyze 결과.
- 새 실제 종목의 수익률·베타·Stress를 독립 수식과 원천 corporate action에 대조한다. Beta 낮은 유의성은 보존한다.
- 전부 null/IPO/중복일/정지/기업행위/지연 발표/휴일 차이/배당/통화오입력·알 수 없는 ticker를 재현한다.
- 부분 지원에서 패널·비교 delta N/A, 이월/보간/자동 종목제외 없음. 비교의 두 입력은 같은 snapshot/시장/통화다.
- KRW를USD로 표시하지 않음, US/KR 시차로 미래 정보 사용 없음. USD 기존 결과의 단위·cent 반올림 불변.
- 28/100/550/800 실제 승인 데이터로 first/warm/동시1·2·4 요청, compare, RSS/cgroup OOM, artifact hash I/O를 측정한다.
  첫cold가30초 요청 제한에 걸리면 배포하지 않고 로딩 경로를 조정한다.
- TypeScript/lint/차트·시장/Portfolio Python·production build 및 KR/EN 검색 접근성·모바일·오류 무효화 E2E.
- 최종 승인 전 기존 Render 서비스를 수정하지 않는다. rollout은 별도 검토·명시적 배포 후 하며 previous snapshot으로 복구 가능해야 한다.

남은 결정: 공개권리 확보 source, 구성목록 정본/갱신주기, 주요ETF 범위, 한국10년/VKOSPI/benchmark 실데이터 이력,
신규 가격 정밀도·공표 cutoff, KRW 반올림 계약, cloud memory/latency와 업데이트 실행 주체.
현 시점 새 실제 종목의 데이터 적격성을 검증하거나 가입/계약/결제를 수행하지 않았다.
