# Portfolio 유니버스 확장 1단계 기반 구현

작업일: 2026-11-04 (Asia/Seoul). 브랜치: `feature/portfolio-universe-design`.
기준 설계: `PORTFOLIO_UNIVERSE_EXPANSION_KO.md`.

## 구현 범위

- 기존 V1 `/universe`, `/analyze`, `/compare`, `/scenarios`, 계산·분류·10개 보유 제한을 보존했다.
- `GET /api/portfolio/v2/catalog`: 버전·snapshot ID·기준일·시장·USD·방법론과 종목별 capability를 제공한다. 가격 행렬은 전달하지 않는다.
- 기존 28개만 `full / frozen_v1_only`로 제공한다. 이는 기존 엔진의 지원 범위이며 신규 공개 데이터 이용 허가가 아니다. 출처는 기존 snapshot metadata를 참조하고, 이용 권리는 `legacy_unverified`, `new_public_use_approved=false`로 명시한다. 종목 ID는 V1에 한정한 안정 ID이며 확인하지 않은 거래소 MIC를 만들어내지 않는다.
- 신규 후보 목록은 비어 있다. 카탈로그 후보가 추가되어도 서버가 `unsupported`, 모든 capability false, `selectable=false`, `NO_APPROVED_RELEASE`를 강제한다. 실제 지원 종목 증가는 0개다.
- KR/EN 티커·회사명·별칭 검색, NFKC 정규화, 티커 exact/prefix 우선, 시장·주식/ETF·상태 필터, 최대 30개 결과 combobox를 구현했다. 키보드 선택·Escape·ARIA 목록·390px 모바일 입력을 지원한다.
- UI는 승인된 V1 경로만 선택·분석 버튼 활성화가 가능하다. 입력 수정 즉시 기존 결과를 무효화하며, 알 수 없는/권리 미확인 종목의 사유를 표시한다. API의 기존 허용 목록도 독립적으로 신규 종목을 422 차단한다.
- `src/portfolio/expansion.py`: 네트워크 호출이 없는 오프라인 receipt 모델과 검증 함수를 추가했다. source·license reference·공개 사용 확인·조회/발표 시각(미제공 이유)·조정/정밀도·코드/의존성 버전·기업행위·거래상태·식별 검증을 기록한다.
- 독립적으로 검증된 757개 달력을 전달받아 가격 날짜 일치·순서·중복·유한성·양수·급변·미래 관측·시장/통화를 검사한다. 휴장 보간이나 가격 clipping은 하지 않는다. 급변은 별도 검토 대상으로 격리한다.
- 팩터 756일 pairing·유한성·분산·회귀 결과와 명시적 팩터/시나리오 검증 조건으로 `full / partial / unsupported`와 capability를 산출한다. partial에 전체 What-if/Stress를 붙이지 않는다. **오프라인 full도 runtime 선택 승인이 아니다.**
- release 생성/검증 함수는 신규 snapshot ID 디렉터리에만 artifact와 SHA256 manifest를 작성한다. 기존 ID 덮어쓰기·경로 탈출·심볼릭 링크 검증을 차단하고 streaming hash를 사용한다. 기준일·built_at·시장/통화·방법론·이전 ID·revision 사유·격리/검토 상태를 기록한다. 실패한 불완전 디렉터리는 검증을 통과하지 못하며 runtime에서 읽지 않는다.
- 원천 자료 경로 `data/portfolio_expansion/raw/`는 gitignore 처리했다. 기존 수집 CLI는 실행하지 않았다.

## 검증

- 변경 전 저장한 golden: 28개 각각 100% 포트폴리오 + before/after 예제 + 전체 What-if. HTTP API에서 전체 JSON 필드·순서·수치·반올림을 비교한다. golden 파일은 신규 구현 전 기존 엔진에서 생성했다.
- 기존 기준: before 변동성 23.38%, after 16.94%, NVDA 위험기여 30.43% → 28.37%, 고정 Stress 3개와 What-if 10행 보존.
- 전체 Python **118개 통과** (기존 Starlette/httpx deprecation 경고 1개). frontend ESLint·TypeScript·차트·데이터 연동·Render 설정 검사 및 production build 통과.
- Chromium E2E **통과**: 390/1280px, KR/EN 회사명, NFKC 전각 티커, 키보드 선택, 권리 미확인 사유·선택 차단, 입력 후 결과 무효화. 기존 고정 데이터 5파일 SHA256도 모두 일치했다.
- `frontend/scripts/check-portfolio-search.mjs`는 로컬 production 서버에 대해 390/1280px, 한영 회사명·전각 티커·키보드·입력 결과 무효화·권리 미확인 선택 차단을 검증한다. 차단 종목은 브라우저 응답에만 주입하는 합성 fixture이며 실제 catalog에는 저장하지 않는다.
- 브라우저 검증 도구/라이브러리는 `/tmp`에 준비하며 프로젝트 의존성을 추가하지 않는다. 재현 시 Playwright 경로를 `MPRI_PLAYWRIGHT_MODULE`, 필요하면 Chromium 경로를 `MPRI_CHROMIUM_PATH`로 지정한다. 로컬 API 8000, production 웹 3000이 필요하다.
- 기존 `data/portfolio/` 5개 파일의 SHA를 고정 manifest와 대조하며, Frozen V1·시장 모델·기존 엔진·Render 설정·main은 수정하지 않는다.

## 다음 미국 pilot 단계의 선행 조건

1. 가격·기업행위·팩터 및 지수 구성 원천의 저장/가공/파생 분석 결과 공개 허용 범위를 증빙하고 승인한다. 이번 작업에서 새 원천 권리를 취득하거나 확인 완료로 표시하지 않았다.
2. 실제 provider 심볼·거래소·통화·class·지수 membership vintage와 ETF 선정 기준을 확인한다. 목표 60~100개는 승인 후 확정한다.
3. 별도 raw run 경로에 원본과 receipt를 저장한다. 검증된 거래일 달력·발표 cutoff·조정 방식·정밀도·분할/배당 대조와 revision diff adapter를 구현한다. 이번 기반은 달력을 입력받으며 원천 수집이나 기업행위 대조를 자동 수행하지 않는다.
4. 신규 종목과 팩터의 실제 757가격/756수익률을 검증하고, DGS10 휴장 예외 정책을 명시적으로 버전화한다. 현재 기반의 팩터 gate는 동일 756일을 엄격하게 요구하므로 임의 결측 면제를 하지 않는다.
5. 승인 release의 returns/beta/진단/scenario를 읽는 별도 V2 analyze/compare adapter와 snapshot 단위 cache를 구현한다. **이번에는 V2 금융 계산 endpoint와 partial 결과 패널을 열지 않았다.** partial은 검색 가능한 상태 구조이며 현재 분석 선택은 차단한다.
6. 실제 승인 데이터의 수익률·회귀·Stress를 독립 수식으로 검증하고, 공통 기간·통화·snapshot capability를 포트폴리오 단위로 재판정한다. 혼합 통화는 계속 차단한다.
7. 실제 pilot 데이터로 cold/warm·동시 1/2/4 요청·compare·RSS/cgroup·hash I/O를 측정한다. 목표 steady ≤350MiB, peak <400MiB 및 첫 요청 <30초를 확인한다. 이번 28개 기반 테스트로 확대 성능을 보증하지 않는다.
8. 위 조건 충족 후에만 신규 runtime 지원과 공개 rollout을 별도 검토한다. 기존 Render 서비스, main, 배포 설정은 이번에 변경하지 않는다.

이 단계는 데이터 승인/승격을 위한 기반 구현이다. 공개 신규 지원, 계약·유료 전환·PR 병합·배포는 수행하지 않는다.
