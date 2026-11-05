# Phase 7 설계 및 로컬 구현

기준: 913cbc4 / feature/portfolio-universe-phase7 / 2026-11-05 (Asia/Seoul).

## 구조 조사와 재사용
catalog.json은 V1 한글명과 미국 후보 52개를 보관한다. catalog.py는 Frozen V1 28개와 후보를 합치되 후보를 항상 차단한다. registry.json에는 활성 릴리스·승인 소스가 없다. expansion.py의 영수증, 757거래일 검증, 불변 릴리스와 SHA 검사를 재사용한다. v2.py/v2_api.py의 권리 게이트, 연구/공개 분리, US/USD 제한은 유지한다. analytics.py의 공분산·상관·변동성과 factors/stress/whatif의 기존 계산은 변경하지 않는다. API bounded executor와 스냅샷 검사를 재사용한다. 프런트 AssetSearch의 NFKC 검색·필터·키보드·선택 차단을 확장한다.

## Universe
기존 /v2/catalog 응답은 80개로 유지. 별도 /v2/discovery는 한국 수동 연구 후보 파일을 합치고 서버 검색·페이지네이션을 제공한다. 한국 seed는 전체 KRX 목록이나 현재 상장 사실을 보증하지 않는다. 공급자 가격·시세·팩터를 포함하지 않는다. 종목 마스터 대량 수집은 권리 확인 후 별도 어댑터로 진행한다.

식별자는 market:MIC:local-code:listing-epoch를 권장한다. 현재 한국 후보 ID의 epoch는 pending이며 공식 ISIN·상장일 확인 전 분석에 사용하지 않는다. 기존 US ID는 호환성을 위해 유지한다. 티커는 문자열이며 한국 선행 0을 보존한다. 상장폐지·거래정지·이전상장·티커 재사용은 status와 유효기간, 새 listing ID로 관리하고 이전 기록을 삭제하지 않는다. 동일 티커 다중 매칭은 자동 선택하지 않는다. KR은 KRW, US는 USD. 혼합통화는 승인된 환율·휴장일·평가시각 정책 전까지 미지원이다.

## 분석 확장
기존 V1 및 V2 응답을 보존하고 별도 오프라인 risk_metrics 함수를 추가한다. 일간 단순 수익률, 표본 공분산(ddof=1), 연율 변동성(sqrt(252)), 일간 역사적 VaR/ES(기본 95%), 초기 NAV=1을 포함한 최대 낙폭을 계산한다. 손실은 -수익률, VaR/ES는 이익만 있는 표본에서 0으로 하한 처리. ES는 VaR 원시 분위수 이상 손실 관측치 평균(동점 포함). 고정 비중 일별 재조정 가정. 누락·비유한 값·중복·정렬 오류는 보간 없이 거부한다. 방법론 버전·관측수·기간·품질을 결과에 기록한다. 이는 신규 종목 승인이나 한국 팩터 모델 검증이 아니다.

베타는 기존 절편 포함 단변량 OLS, rate는 bp, volatility는 pt 단위를 재사용한다. 한국은 현지 시장/금리/변동성 팩터, 조정주가·배당·권리락, 거래 달력·장마감·타임존·수정 이력 검증이 선행되어야 한다. 스트레스 시나리오와 What-if는 같은 snapshot/methodology/currency에서만 비교한다. 신규 지표는 공개 응답에 자동 삽입하지 않고 검증 후 버전 계약으로 추가한다.

## 승인 흐름과 검증
권리(저장/파생결과/재배포/종목·팩터별 범위) → 식별자·상장상태 → 기업행동 → 독립 거래 달력 → 757 가격/756 수익률 → 팩터와 시나리오 → V1 비교·수치 검증 → 불변 연구 릴리스 → 별도 공개 승인 순서. catalog 상태·검증 영수증만으로 registry를 변경하지 않는다. 운영 수집·유료 가입·Render 변경·push·배포는 수행하지 않는다.

## 구현 범위와 남은 일
이번 단계는 discovery 기반, 소규모 한국 seed, 검색 페이지 이동, 오프라인 추가 위험 지표 및 회귀 검증이다. 전체 미국/한국 종목 마스터, 실가격 ingestion, 한국 분석 엔진, 환율 분석과 공개 V2 활성화는 권리·방법론 검증 후 진행한다. 실제 분석은 기존 Frozen V1 28개이며 신규 승인 0개이다. 공급자 검토 및 최종 검증 결과는 별도 Phase 7 문서에 기록한다.

## 최종 검증 결과

- Python 전체: 264 passed, 신규 17개 포함. 기존 Starlette/httpx 지원 중단 예고 경고 1건. 샌드박스에서 TestClient 이벤트 루프가 정지하여 동일 로컬 검사를 sandbox 밖에서 실행했다.
- frontend: eslint, tsc --noEmit, production build, test:charts, test:integration, test:render 모두 통과. Render 검사는 로컬 설정 검증이며 서비스 접근/변경이 아니다.
- 기준 커밋을 /tmp에 archive해 기존 계약 캡처와 현재 캡처를 비교했다. health/universe/scenarios, before/after/compare, 기존 OpenAPI 경로·스키마, 28개 단일 자산 결과 SHA가 모두 동일하다. 원본 응답은 /tmp에만 두고 저장소에는 검증 요약과 해시만 기록했다.
- 브라우저 E2E는 Playwright 모듈을 찾지 못해 미실행. 모바일 레이아웃·포커스·페이지 이동의 실제 브라우저 검증은 남아 있다.
- data/portfolio_v2/catalog.json, registry.json, source_rights_review.json, Frozen V1 데이터, Stress Validation 코드, render.yaml은 변경하지 않았다. main 수정/병합, commit/push, 배포, 운영 데이터 변경, 신규 유료 사용은 하지 않았다.

재현 명령 (저장소 루트):

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m pytest -q
.venv/bin/python scripts/check_portfolio_phase6_contract.py /tmp/phase7-contract.json
cd frontend
npm run lint
npx tsc --noEmit
npm run build
npm run test:charts
npm run test:integration
npm run test:render
```

## 변경 파일

- data/portfolio_v2/kr_candidates.json: KOSPI 6개·KOSDAQ 4개 주식 및 한국 ETF 6개 수동 후보. 현행 상장 사실/명칭/거래소 식별자는 공급자 검증 전이다.
- src/portfolio/catalog.py, api.py: 기존 카탈로그 유지, 별도 discovery 검색과 입력 검증.
- src/portfolio/risk_metrics.py: 오프라인 위험 지표 및 동일 표본 What-if 차이.
- frontend/src/lib/portfolio-api.ts: discovery 페이지 수집과 중복 티커 차단.
- frontend/src/components/portfolio/asset-search.tsx: UI 페이지 이동·전체 개수·한글 상태·기준일.
- tests/test_portfolio_phase7.py: 페이지 완전성·필터·차단·입력 오류·알려진 수익률 경로·위험 지표 검증.
- reports/design/PORTFOLIO_PHASE7_PROVIDERS_KO.md, PORTFOLIO_PHASE7_VALIDATION.json 및 본 문서: 공급자 비교, 재현 정보와 결과.

## 배포 판정

신규 공개 분석 출시는 NO-GO. 가격·팩터 권리 승인 0개, 한국 방법론 미승인, 전체 종목 마스터와 실가격 검증 미완료, 브라우저 E2E 미완료가 차단 사유다. 검색 UI/API 변경도 이번 작업의 로컬 산출물이며 배포는 별도 승인 범위다. 다음 단계는 공급자별 실제 사용 범위에 맞는 권리 증빙 확보, 전체 마스터/상장 이벤트 어댑터, 독립 달력·기업행동 검증, 한국 팩터/시나리오 정책 검증, 격리 연구 릴리스·비교 후 공개 승인이다. 현재 UI는 작은 seed를 페이지 단위로 모두 읽어 클라이언트 필터링한다. 전체 시장 규모로 확장할 때는 이미 추가한 서버 q/market/kind/status/offset/limit 검색 API를 직접 호출하도록 전환한다.
