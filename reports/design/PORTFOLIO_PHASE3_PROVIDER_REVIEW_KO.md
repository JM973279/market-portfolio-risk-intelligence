# 금융 데이터 공급처 비교 — Phase 3

확인일 **2026-11-04, Asia/Seoul**. 공식 공개 문서·요금표만 사용했다.
가입·구매·키 발급·무료 trial 신청·문의 발송·신규 금융 데이터 수집은 0건이다.
금액은 표시 통화의 월납 정가이며 세금·환율·추가 권리·거래소·VIX 비용을 포함한 확정 견적이 아니다.
`PORTFOLIO_PHASE3_PROVIDERS.json` / `.csv`에 공급처별 확인일·공식 URL·기능·세 가지 권한과 원본 재배포 권한을 구분했다.

## 가격·호출량·기능

| 공급처 | 무료 / 개인·저비용 | 상업·공개 서비스 후보 비용 | 호출 제한 / 품질 차이 |
|---|---|---|---|
| Twelve Data | Basic $0: 8 credits/분·800/일. Grow $29부터, 55 credits/분 | Venture $149·610 credits/분부터. 화면의 $499는 2,584 variant. Enterprise $1,099·10,946 | `time_series` 종목당 1 credit, dividends 20. 유료 일일 cap 없음. 일봉·ETF·분할/배당 endpoint. 가격 `adjust` 기본값은 splits이므로 `all`을 명시·검증해야 함 |
| Alpha Vantage | 무료 25회/일. 개인 premium $49.99·75회/분부터, $249.99·1,200회/분까지 | 상업용은 별도 서면 견적. 개인 premium 금액으로 공개 라이선스를 계산하면 안 됨 | 유료 일일 cap 없음. Daily Adjusted premium이 조정종가·split/dividend events 제공. 기본 compact 100개는 부족하므로 full 필요. ETF·VIX endpoint 존재와 실제 entitlement는 별개 |
| EODHD | 개인 EOD $19.99/월. 무료 20 calls/일. 유료 100,000 calls/일부터 | 확인된 상업 페이지는 **GBP**: Internal £399/월, 기업 서버 다운로드 +£200, Enterprise £2,499, Custom £399부터. 공개 결과 범위는 견적 필요 | 1,000 requests/분과 가중 calls/일을 구분. `adjusted_close`는 배당·분할 조정, OHLC는 원가격. ETF·기업행위 지원. indicative/OTC 원천 설명 때문에 공식 EOD와의 정합도 별도 검증 |
| Massive | Basic $0·5회/분·2년 history. 개인 Starter $29·5년, Advanced $199 | Stocks Business $2,499/월, Enterprise 별도 견적. VIX/index 권리는 별도 확인 | 유료 stock plan은 unlimited API calls 표시. Basic 2년은 757거래일에 부족. REST bars는 분할 조정만 제공하며 배당 조정은 별도 기업행위 처리 필요 |
| Yahoo/yfinance | 도구 무료, 서비스 보장 없음 | 공개 서비스 권리·가격 확인 못함 | 비공식 wrapper. 공식 계약 quota 없음. adjusted/action/ETF/VIX 접근 가능성과 이용 허가는 다름 |
| Stooq | 무료 historical 페이지 | 공개 권리/계약/가격 미확인 | 약관 URL·조정/기업행위 범위·호출 quota 미확인. 브라우저 검증을 우회하지 않음 |
| Fed H.15 직접 | 자체 공공자료 $0 | 해당 Board 자체 자료는 public domain 조건 적용 가능 | 미10년 금리 후보이며 주가·ETF·VIX 대안은 아님. endpoint·달력·revision은 기술 검증 대기 |
| FRED | 접근료 $0 | series 소유권과 서비스 조건별 범위 확인 필요 | DGS10 등. 무료라는 이유로 공개 API/배포 파일을 일괄 승인하지 않음 |
| Cboe VIX | historical 페이지 접근료와 공개 사용 권리는 별개 | 정확한 EOD VIX·파생 공개 용도는 견적 필요 | 실제 VIX 지수 여부 확인. 선물·ETF로 대체하지 않음. 의도한 자동 수집 quota 미확인 |

Twelve Data는 공식 [pricing.md](https://twelvedata.com/pricing.md)에서 최저 tier를 확인했다. [상업 요금 화면](https://twelvedata.com/pricing-business)은 선택된 높은 credit variant를 보여줄 수 있다.
Alpha Vantage의 [premium 공개 HTML](https://www.alphavantage.co/premium/) select option에서 월간 75/$49.99, 150/$99.99, 300/$149.99, 600/$199.99, 1200/$249.99를 확인했다. 연납 option의 월표시 문구는 사용하지 않았다.
EODHD [개인](https://eodhd.com/pricing)·[상업](https://eodhd.com/commercial-pricing), Massive [개인](https://massive.com/stocks)·[상업](https://massive.com/business) 요금표를 분리했다.

기능 근거: [Twelve Data docs](https://twelvedata.com/docs), [Alpha Vantage Daily Adjusted](https://www.alphavantage.co/documentation/#dailyadj), [EODHD EOD](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)·[actions](https://eodhd.com/financial-apis/api-splits-dividends)·[limits](https://eodhd.com/financial-apis/api-limits), [Massive adjustment 설명](https://massive.com/knowledge-base/article/is-massives-stock-data-adjusted-for-splits-or-dividends)·[history](https://massive.com/knowledge-base/article/how-much-historical-stock-data-does-massive-have).
이 기능 비교는 실제 80개 금융 원천을 다운로드해 검증한 결과가 아니다.

## 저장·생성·공개의 권한 구분

| 공급처 | 원본 저장 | 파생 지표 생성 | 공개 웹·JSON 결과 | 원본/수익률 artifact 공개 |
|---|---|---|---|---|
| Twelve Data | plan·cache 기간 조건부 | 원자료 재구성 불가 등의 조건부 | Business·거래소·attribution·계약 범위 확인 필요 | 별도 redistribution 권리; EOD 외부 배포 custom |
| Alpha Vantage | 개인 범위와 조직 서비스 범위를 분리 | 개인 분석과 공개 파생 제공을 분리 | 별도 상업 서면 권리 미취득 | 미승인 |
| EODHD | 개인 private 저장 허용; 상업 서버 옵션 별도 | 개인 private 허용; 상업 범위는 계약 | Internal 요금만으로 외부 제공 승인 불가 | 개인 original/repackaged 공유 금지; 상업 별도 확인 |
| Massive | 개인 download/store 명시 | 개인 연구 scope; 상업 별도 | 개인 플랜은 다른 사용자를 위한 앱 불허 | 계약·원 제공처·해지 후 보관 조건 확인 필요 |
| Yahoo/yfinance | 데이터 권리는 도구 라이선스와 별개 | 개인 고지를 공개 권리로 확대하지 않음 | 미확인 → 미승인 | 미승인 |
| Stooq | 명시적 권리 미확인 | 미확인 | 미승인 | 미승인 |
| Fed 직접 H.15 | 예외 표시 없는 Board 자체 자료 가능 | 해당 public-domain 자료 가능 | 출처 표시·타사 자료 예외 조건 준수 시 가능 | 해당 자체 자료 가능. 로고·타사 자료 제외 |
| FRED | 서비스·series 조건별 | 소유자 조건별 | 의도한 공개 API 범위 미확정 | third-party proprietary 자료는 권리자 확인 |
| Cboe | 웹 약관의 제한적 개인 scope | 서비스 파생 용도의 별도 범위 확인 | 미승인 | 미승인 |

현재 M/PRI 신규 runtime 승인 공급처는 **0개**다. Fed 직접 원천은 법적 rate-source 후보이나 기술적으로 활성화하지 않았다. 일부 권한이 명시돼 있어도 조합 전체의 승인을 의미하지 않는다.
기존 28개는 기존 `frozen_v1_only / legacy_unverified`를 보존하며 이번에 권리를 재승인하지 않았다.

공식 약관 근거(모두 위 확인일 기준):

- [Twelve Data 약관](https://twelvedata.com/terms), [commercial/personal 안내](https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage): internal storage, non-display, derived, external display, redistribution을 분리하고 cache·거래소 조건을 확인한다.
- [Alpha Vantage 약관](https://www.alphavantage.co/terms_of_service/): 개인·비상업 기본 범위를 넘어서는 용도는 별도 서면 조건 확인이 필요하다.
- [EODHD 약관](https://eodhd.com/financial-apis/terms-conditions), [상업/개인 구분](https://eodhd.com/financial-apis/commercial-vs-personal-license-use): private 저장/분석과 original/repackaged 공유 제한을 구분한다.
- [Massive market-data 약관](https://massive.com/legal/market-data-terms-of-service): 페이지의 갱신일은 2026-11-03. 개인 저장/연구와 타 사용자 앱·조직 이용은 구분한다. 상업 상품 소개만으로 M/PRI 권리를 취득하지 않는다.
- [yfinance 공식 고지](https://github.com/ranaroussi/yfinance), [Yahoo 약관 URL](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html): wrapper 권리와 실제 데이터 권리를 구분한다. Yahoo 직접 본문은 앞선 동일 날짜 확인에서 HTTP 999로 실패했다.
- Stooq는 [검토한 historical entrypoint](https://stooq.com/db/h/)만 기록하고, 확인하지 못한 약관 URL을 만들어 넣지 않았다.
- [Fed 정책](https://www.federalreserve.gov/disclaimer.htm), [H.15](https://www.federalreserve.gov/releases/h15/): Board 자체 자료와 보호된 타사 자료·브랜딩을 구분한다.
- [FRED 약관](https://fred.stlouisfed.org/legal/terms/), [DGS10](https://fred.stlouisfed.org/series/DGS10): 서비스와 series 조건을 함께 확인한다.
- [Cboe 약관](https://www.cboe.com/terms/), [index licensing](https://www.cboe.com/data/global-indices-feed), [VIX history](https://www.cboe.com/tradable-products/vix/vix-historical-data): CSV 접근을 공개 파생 서비스 허가로 해석하지 않는다.

## 권장 전략과 비용의 해석

1. **당장 비용 0:** 기존 28개 기능 보존 + 신규 52개 unsupported. 새 raw/returns 파일을 GitHub나 웹에 공개하지 않는다. 기존 로컬 데이터 재현만 수행한다. 비공개라고 해서 개인 플랜으로 조직용 연구가 자동 허용되는 것도 아니다.
2. **먼저 문의할 후보:** Twelve Data Venture 최저 $149/월을 EOD 공개 파생 결과 용도의 기준 견적 후보로 삼는다. VIX·archive·웹 JSON API·반복 조회의 재구성 위험·해지 후 보관·cloud processor 범위를 서면 확인해야 한다. **$149가 전체 합법 서비스의 확정 비용이라는 뜻은 아니다.**
3. **대조 견적:** EODHD는 £399 Internal과 서버 옵션으로 공개 사이트 권리를 계산하지 않는다. public-derived custom scope를 문의한다. Massive는 $2,499 Stocks Business 및 별도 index/VIX quote, Alpha Vantage는 개인 $49.99와 별개인 상업 견적을 비교한다. 세금·환율·VIX 비용은 미확정이다.
4. **금리 대안:** Fed 직접 H.15를 별도 검증하면 rate 원천 자체의 비용은 $0일 수 있다. 기존 DGS10을 조용히 바꾸지 않고 단위·달력·시점·수정 이력을 독립 검증한다. 주가/SPY/VIX 권리는 여전히 필요하다.
5. **분리 경로:** 연구용은 gitignored `data/portfolio_expansion/{raw,research}/`와 로컬 probe만 사용한다. 공개용은 승인 ledger·immutable manifest hash를 통과한 release만 읽는다. 원본/returns/beta를 공개 GitHub에 실어야 한다고 가정하지 말고, 허가된 private artifact delivery/hosting과 공개 결과 API를 각각 계약에 명시한다. 현재 보수적인 공개 artifact gate는 완화하지 않는다.
6. **승격 조건:** written scope + source receipt/원본 SHA + 757실가격·기업행위·달력·revision + 필수 팩터·시나리오 검증 + 실제 확대 부하를 모두 통과해야 한다. 조건이 없으면 승인하지 않는다.

문의 내용은 `PORTFOLIO_PHASE3_VENDOR_INQUIRY_EN.md`에 공통 영문 본문과 업체별 추가 질문으로 작성했다. 초안만 저장했으며 발송하지 않았다.
