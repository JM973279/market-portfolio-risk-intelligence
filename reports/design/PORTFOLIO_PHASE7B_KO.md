# Phase 7B — Market Price Data Engine 로컬 구현 결과

기준 커밋 `ee301f6`, 브랜치 `feature/portfolio-universe-phase7`. 이번 단계는 **연구용 로컬 가격 원본 수집·정규화·검증·재현과 분석 연결**을 구현했다. 실제 외부 공급자에 연결하거나 신규 실가격을 내려받지는 않았다. 공개 API·운영 서비스·승인 registry는 연결하지 않았다.

## 1. 기존 구조 조사와 재사용

- Phase 7A discovery는 Frozen V1 28개 + 미국 연구 후보 52개 + 한국 연구 후보 16개로 구성된다. 후보의 검색 가능 여부와 분석 승인을 분리하며, 한국 후보의 `pending` ID와 명칭을 검증된 식별자로 간주하지 않는다. 이 목록은 전체 시장 마스터가 아니다.
- Frozen V1은 `data/portfolio`의 가격·팩터·시나리오·스냅샷·universe와 SHA 설정에 고정되어 있다. 기존 `analytics.py`, `factors.py`, `stress.py`, `whatif.py`, Stress Validation과 공개 API 코드를 변경하지 않았다.
- `risk_metrics.py`의 단순 수익률 기반 변동성·공분산·상관·VaR·ES·최대 낙폭과 동일 표본 What-if를 그대로 호출한다.
- `expansion.write_release/verify_release`의 불변 디렉터리·manifest·SHA 검사를 연구 산출물 저장/재현에 재사용한다. 새 연구 릴리스는 항상 `quarantined`다.
- [Phase 7A 공급자 검토](PORTFOLIO_PHASE7_PROVIDERS_KO.md)와 `source_rights_review.json`을 재사용했다. 권리 재승인·유료 구독·API 키 발급은 하지 않았다.

## 2. 구현 기능과 파일

| 파일 | 구현 내용 |
|---|---|
| `src/portfolio/price_engine/contracts.py` | 시장·MIC·통화·주식/ETF·상장 유효기간, 공급자 심볼 매핑, 연구 처리 권리 근거, 수집/공표 영수증, 명시적 거래 세션, 기간·품질 정책, 구조화 예외 |
| `src/portfolio/price_engine/adapters.py` | PriceAdapter Protocol, Capture와 원본 SHA, CSV/Alpha Vantage/KRX 원본 정규화, 중복 보존, 소스·심볼·통화 충돌 차단, UTC 수집 시각, 로컬 파일 읽기 |
| `src/portfolio/price_engine/engine.py` | 품질 보고서, 검증된 수정주가→수익률, 기존 risk_metrics/compare_risk_metrics 연결. 모든 결과 research_only 및 공개 분석 불가 |
| `src/portfolio/price_engine/storage.py` | 기존 gitignore 연구 경로 전용 저장, 원본 bytes·영수증·매핑·달력·의존성·코드 버전·정규화·검증 보고서 저장, 원본 재파싱과 검증 결과 재현 |
| `src/portfolio/price_engine/__init__.py` | 공개 라우터와 분리된 연구 패키지 |
| `scripts/portfolio_price_engine.py` | ingest/replay CLI, config 상대 경로 입력, 공개 활성화 옵션 없음 |
| `tests/test_portfolio_price_engine.py` | 외부 socket 연결을 금지한 합성 원본 기반 테스트 40개 |
| 본 문서와 `PORTFOLIO_PHASE7B_VALIDATION.json` | 구현 범위·실측 결과·제약·후속 계획 |

### 식별자·정규화

`asset_id`를 분석 키로 사용한다. 별도 Instrument와 SymbolMapping에 MIC, 통화, 종류, 상장/상장폐지 구간, 공급자 심볼과 유효기간·근거를 기록한다. 한국 숫자 코드는 문자열로 유지한다. 기존 discovery 후보를 자동으로 매핑하거나 승인하지 않는다. 동일 ID의 다른 매핑 또는 공급자가 구별할 수 없는 같은 심볼의 다중 ID는 거부한다. 일별 파일을 여러 개 수집할 수 있으나 겹친 날짜를 임의로 덮어쓰거나 마지막 값으로 축약하지 않는다.

CSV 입력 계약은 UTF-8의 `date,symbol,currency,close,adjusted_close`다. date는 YYYY-MM-DD, 가격은 천 단위 구분자 없는 수치다. 결측/잘못된 수치는 품질 검사에서 격리하며, 행 구조·날짜·소스 심볼 오류는 구조화 예외로 거부한다. 정규화는 일별 종가/수정종가 범위이며 OHLCV 전 필드나 장중 체결을 구현하지 않았다.

### 거래 달력·최신성

자동 평일 생성기를 제공하지 않는다. 시장/MIC별로 독립적으로 확보하고 검토한 TradingCalendar를 입력해야 한다. 달력에는 커버리지, 근거, 버전, 현지 관측일, timezone, 실제 close_at 및 공급자 가용 시각 available_at을 기록한다. 임시 휴장·한국 연휴·주말은 세션 부재로, 조기 폐장·미국 DST는 명시 시각으로 처리한다. 달력 파일의 `reviewed` 값과 근거는 검토자의 진술이며 엔진 자체의 독립 인증이 아니다.

latest 모드는 기준 시각까지 가용한 마지막 세션과 비교하며 달력이 기준 현지 날짜까지 커버하지 않으면 차단한다. 아직 마감/갱신되지 않은 세션은 결측으로 요구하지 않는다. historical 모드는 명시된 과거 구간만 검증하고 최신 데이터라는 보증을 하지 않는다. 세션별 가용 지연 값은 공급자·상품별 검증 후 입력해야 한다.

US/USD와 KR/KRW를 각각 처리한다. 혼합 시장·통화는 `FX_POLICY_REQUIRED`로 거부한다. 환율은 별도 원본/권리/달력/빈티지/평가시각 검증 후 현지 통화 수익률과 결합해야 한다. 환율 다운로드·변환·시장 간 강제 교집합 또는 forward-fill은 구현하지 않았다.

### 품질 기준

기본 최소 757개 가격 → 756개 수익률. 테스트에서는 명시적으로 짧은 정책을 사용하며, 기본 창을 검증하는 별도 757개 합성 테스트도 있다. 요청 구간의 기대 거래일과 가격 날짜를 정확히 비교한다. 결측·중복·휴장일 가격·미가용 가격·미래 수집·수집 시점 이전 가용성 불일치·비양수/비유한 값·조정 수익률 절댓값 50% 초과를 차단한다. 보간·클리핑·가격 대체·원종가의 수정주가 대체는 하지 않는다.

총수익 조정(total_return), 조정 근거, 기업행동 검토 근거가 모두 있어야 연구 분석으로 전달한다. split_only/raw/unknown은 통과하지 않는다. 원종가와 수정종가는 따로 보존한다. **분할·배당 원장으로 수정계수를 독립 재계산하는 기능은 미구현**이다. 입력 근거의 사실 여부·법적 충분성을 자동 판정하지 않으며, 실제 corporate action 대조는 후속 데이터 검증에 남는다.

실패는 code/asset_id/details로 보고한다. 예: MISSING_SESSIONS, DUPLICATE_OBSERVATION, STALE_PRICES, INVALID_PRICE, TOTAL_RETURN_ADJUSTMENT_UNVERIFIED, EXTREME_ADJUSTED_MOVE_REQUIRES_REVIEW. 원본 byte 해시뿐 아니라 영수증별 capture ID, 정규화 해시도 기록하며 수집 이후 DataFrame이 바뀌면 재승인하지 않는다.

## 3. 공급자별 실제 연결 여부

| 공급자/입력 | 구현 | 실제 연결·실가격 검증 |
|---|---|---|
| 로컬 CSV | 파일 bytes 수집→정규화→검증→위험 지표→저장/재현 | 합성 파일로 E2E 검증. 신규 실가격 CSV는 입력하지 않음 |
| Alpha Vantage | DAILY_ADJUSTED 형식 JSON archive 파서, 메타 심볼 대조, 에러/한도 응답·중복 JSON 키 거부 | HTTP 호출 없음, 유료 endpoint 사용 없음. 실제 응답의 스키마·기업행동 정확성 검증 미완료 |
| KRX | OutBlock_1/BAS_DD/ISU_CD/TDD_CLSPRC 계약의 연구 archive 파서. ISIN이 들어오는 경우 그 값을 명시적으로 매핑해야 함 | HTTP 호출 없음. 실제 종목별·ETF별 스키마 대조 미완료. raw close만 보존하며 수정주가 없어 분석 차단 |
| 금융위, Twelve Data, Massive, Yahoo, Stooq, FRED, Cboe | 기존 공급자 검토 재사용 | 신규 어댑터·연결·수집 없음 |

공식 문서 확인은 데이터 endpoint 호출과 구분했다. Alpha Vantage 문서는 adjusted daily 상품이 premium임을 명시한다. KRX 공개 소개 페이지는 일별 주식/ETF 상품을 확인할 수 있으나 동적 출력 스키마를 브라우징 결과에서 확인하지 못했다. 따라서 KRX 파서를 운영 스키마 검증 완료로 표시하지 않는다.

- [Alpha Vantage 공식 문서](https://www.alphavantage.co/documentation/)
- [KRX 서비스 목록](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd)
- [KRX 주식 서비스](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC)
- [KRX ETF 서비스](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES003_S2.cmd?BO_ID=nrEpCLaZpoLCTzPUMxuF)

연구 저장/계산도 source별 ResearchPermission의 두 허용값과 근거가 필요하다. 이는 공개 데이터 권리 장부를 대체하지 않는다. 네트워크 transport, 인증, 요청 재시도, 공급자 rate limit·자동 backfill·갱신 스케줄러는 구현하지 않았다.

## 4. 재현·실행 방법

CLI config JSON에는 `permissions`, `mappings`, `calendars`, `window`, 선택 `policy`, `archives`를 넣는다. 각 archives 항목에는 adapter(csv/alpha_vantage/krx_openapi), asset_id, path, receipt가 필요하다. 각 상세 계약은 contracts.py에 정의되어 있으며 테스트 `test_cli_local_capture_and_replay`가 실행 가능한 config를 구성한다.

```bash
.venv/bin/python scripts/portfolio_price_engine.py ingest /path/to/config.json \
  --run-id research-001 --code-version ee301f6+phase7b-local \
  --revision-note 'authorized local archive review'
.venv/bin/python scripts/portfolio_price_engine.py replay research-001
```

품질 통과 시 exit 0, 격리/입력 실패 시 exit 2다. 저장은 `data/portfolio_expansion/research/price_engine/<run_id>`에만 수행한다. 기존 gitignore 적용 대상이며 공개 release root를 인자로 받지 않는다. 심볼릭 링크/경로 우회를 거부하고 같은 run_id를 덮어쓰지 않는다. 새 수정본은 previous_snapshot_id와 revision_note를 기록한 별도 릴리스로 만든다. 실패 원본도 연구 저장 권리가 있고 변경되지 않은 입력이면 quarantined 상태로 저장/재현할 수 있다.

sources.json에는 원본 bytes(base64)·수집/공표 영수증·매핑·연구 사용 근거, replay.json에는 달력·기간·정책·Python/pandas/numpy/pydantic 및 코드 버전이 저장된다. manifest SHA 검증 후 원본을 다시 파싱하고 normalized.csv·품질 결과를 대조한다. 의존성/엔진 버전이 달라지면 조용히 재해석하지 않고 실패한다. SHA는 변경 탐지 수단이며 공급자의 원본 진위 또는 법적 사용 권한을 증명하는 전자서명은 아니다.

프로그램 내 분석 인터페이스:

```python
from src.portfolio.price_engine.engine import analyze_research
result = analyze_research(collection, calendars, window, weights,
                          proposed=proposed_weights)  # stable asset_id → decimal weight
```

매 호출 시 검증을 다시 실행한다. 입력 전체가 통과한 동일 시장·동일 통화·정렬된 공통 세션의 수정주가만 `pct_change(fill_method=None)`로 변환한다. 검증 후 기존 risk_metrics 계산을 호출한다. 결과에는 기준 구간·정책·품질·원본 해시와 기존 방법론 버전이 포함된다. 공개 /analyze 또는 /v2/analyze, 팩터·베타·스트레스, registry 활성화에는 연결하지 않았다.

## 5. 오프라인 검증과 실제 가격 검증의 차이

합성 가격/달력/공급자 형식으로 파서·차단 조건·계산·재현을 검증했다. 테스트 자료의 permission/identity/calendar 근거는 `synthetic:`로 표시하며 실제 라이선스나 거래소 검증으로 해석할 수 없다. 신규 외부 가격 정확성, 거래소 공식 달력과의 전체 대조, 배당/분할 조정계수, 공급자 정정·과거 상장종목·누락/가용성 SLA는 검증하지 않았다. 기존 Frozen V1 결과 회귀 검증은 신규 공급자 데이터 검증과 별개다.

## 6. 테스트 결과

- 신규 오프라인 테스트 **40 passed**: US/KR 주식·ETF, 최소757개, 휴장일·주말, DST/조기폐장 세션 표현, 가용 cutoff, 결측/중복/지연/이상치, 조정·기업행동 근거, 매핑 충돌, 혼합통화 차단, 공급자 에러, 동일 bytes의 서로 다른 수집 영수증, 원본 변조·경로 우회, 수정본 독립 저장, 2자산 공분산/What-if 및 CLI ingest/replay.
- 전체 Python **304 passed**, 기존 Starlette/httpx deprecation 경고 1건. 전체 검사는 Phase 7A와 동일한 TestClient 샌드박스 정지 제약을 피한 로컬 실행이며 새로운 네트워크 연결 테스트는 금지했다.
- 프런트엔드 eslint, tsc --noEmit, test:charts, test:integration, test:render, production build 모두 통과. 프런트엔드 소스는 변경하지 않았다. 브라우저 Playwright E2E는 이번 단계에서 미실행이다.
- `ee301f6`를 /tmp에 archive해 현재와 기존 계약을 캡처 비교했다. 기존 28개 단일 자산 결과 해시, before/after/compare, health/universe/scenarios 및 기존 OpenAPI 경로·스키마 동일. 상세 요약은 검증 JSON에 기록한다. 원본 계약 응답은 /tmp에만 유지한다.

재현:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m pytest -q
cd frontend
npm run lint
npx tsc --noEmit
npm run test:charts
npm run test:integration
npm run test:render
npm run build
```

## 7. 신규 분석 가능 종목 수와 안전 상태

신규 공개 분석 가능 **0개**, 기존 Frozen V1 **28개 유지**. 연구용 합성 식별자에서 계산 경로가 통과한 것을 실제 종목 지원 수로 세지 않는다. 신규 검증 실가격 종목도 **0개**다. 연구 품질 통과 보고서에도 public_analysis_allowed=false, selectable=false와 권리/방법론 공개 차단 사유가 남는다.

기존 데이터·Stress Validation·카탈로그·registry·source_rights_review·Render 설정을 변경하지 않았다. main 변경·병합, commit, GitHub push, 배포, 운영 데이터 변경과 유료 서비스 사용은 하지 않았다.

## 8. 남은 작업 및 Phase 7C 권장 범위

1. 연구 저장·처리 및 외부 파생 분석·재배포별 권리 근거를 분리해 확보한다. 기존 승인 장부는 별도 승인 전까지 비워 둔다.
2. 우선 무료/허가된 단일 공급자의 실제 소규모 원본을 확보해 HTTP 응답 스키마·심볼/ISIN·상장구간·통화·정정 이력을 대조한다. Alpha Vantage premium을 자동 사용하지 않는다.
3. 미국·한국 거래소 공식 근거에서 버전 관리 가능한 세션 파일을 구축하고 휴장·임시휴장·조기폐장·데이터 지연 시각을 검증한다. 가격 날짜 자체로 검증 달력을 만들지 않는다.
4. 분할·배당·분배금·권리락 원장을 수집하고 총수익 조정계수를 독립 대조한다. KRX raw 가격을 조용히 대체하지 않는다.
5. 권리 확보 후에만 네트워크 collector의 인증 보관·timeout·rate limit·재시도·중복 page·백필·증분 갱신·스케줄링을 구현한다. 새 빈티지는 불변 연구 릴리스로 저장한다.
6. 실제 US/KR 표본에서 독립 품질 검증과 기존 모델 비교를 수행한다. 한국 팩터·스트레스와 FX 정책은 별도 승인/계약으로 개발한다.
7. 공개 제공은 권리·시장 방법론·전이 승인·V1 회귀를 모두 통과한 뒤 별도 승인으로 진행한다. 이번 결과만으로 신규 공개 분석을 출시할 수 없다.
