# M/PRI — Risk in Motion 디자인 설계

기준: feature/portfolio-universe-phase7 / ee301f6. 기존 Phase 7B 미커밋 파일은 보존한다. 로컬 개발만 수행하며 commit/push/배포는 하지 않는다.

## Design Audit

기존 UI는 밝은 색상의 동등한 카드와 작은 수치·설명, 반복되는 패널로 우선순위가 약하다. 홈의 시장별 카드+차트는 시간적 신호 관계를 따로 읽게 만든다. Portfolio는 STEP 1~6의 긴 수직 흐름으로 입력과 결과를 오가야 한다. 가격/위험의 이중 축은 지표 성격을 읽기 어렵게 한다.

## Design System

배경 #070D16, 표면 #101B29, 상승 표면 #162435, 본문 #F2F6FA, 보조 #93A6BA. 브랜드 cyan #18C9D2, 시계열 ice #69C8F5, 보조 silver #C9D5E2. 경고 amber #F3B54A와 위험 red #F06464는 의미를 보존한다. 보라/핑크/네온/유리 표현은 제거한다. Pretendard 로컬 폰트를 유지하고 숫자 tabular 정렬, 4/8px 간격 체계, 1px 저대비 선, 명확한 focus ring을 적용한다. 애니메이션은 짧은 패널 상태 전환만 사용하며 reduced-motion을 존중한다.

## 구현 범위

1. 공통 shell: 정돈된 브랜드·탐색, 페이지 위치·스냅샷 표시, KR/EN 유지, skip link, 모바일 Escape 닫기.
2. 홈: Global Risk Overview, 큰 Risk Explorer(동일 날짜의 독립 레인), 관측 검증 컨텍스트, 저장된 확산도 기반 Risk Build-Up, Cross-Market Stress, Recent Observations. 기존 연구·검증·사례 링크와 내용 보존.
3. Explorer: Risk Score/MSI 전환, 1M/3M/6M/1Y/ALL, 관측 hover/keyboard slider, 선택일의 양시장 실제 값과 결측, 각 모델의 임계값 표시. 기간·지표 선택 session 유지. 독립 모델의 원시 점수 차이나 새로운 acceleration/proximity 점수는 계산하지 않는다.
4. Portfolio: 좌측 Holdings Editor, 우측 diagnosis/scenarios/what-if 워크스페이스. 분석/비교 계약과 입력 변경에 따른 결과 무효화 유지. 위험 기여도·상관·집중도·팩터·손실 구조를 재사용하고 What-if 비교를 강화한다. 시장 문맥은 접이식으로 보존.
5. 미국/한국/확산도/검증/사례/출처/방법론: 공통 dark 시스템과 일관된 차트·표·상태·접이식 설명 적용.

## 데이터 경계

currentOperationalPoint를 그대로 재사용한다. 현재 미국 Risk Score/MSI가 blocked이면 N/A이고 과거 점수를 이월하지 않는다. 운영 export, historical OOS, 한국 breadth 연구의 날짜를 따로 표시한다. 차트의 historic stress flag는 원본 표식이며 새 사건 판정이 아니다. Portfolio는 Frozen V1 28개만 분석 가능, 후보 상태 그대로. 신규 7B 연구 지표를 공개 API에 연결하지 않는다. SHAP export가 현재 없으므로 값·순위를 생성하지 않고 연결 미지원과 기존 요인 설명을 구분한다.

## 검증 계획

기존 Python 전체와 API 계약, 프런트엔드 lint/TypeScript/chart/integration/render/build를 실행한다. 실제 로컬 Chromium에서 모든 페이지, 언어 전환, 기간/지표/관측 slider, 모바일 overflow/탐색, Portfolio 검색·차단·입력 무효화·분석·What-if, 오류/empty 상태와 키보드를 확인한다. 결과와 확인하지 못한 항목은 최종 결과에 기록한다.

## 데이터 구현 범위 확정

- Explorer는 기존 global-markets.json만 사용하며 운영 이력을 과거 OOS 선에 이어붙이지 않는다.
- 운영 패널은 currentOperationalPoint 검증을 재사용한다. 미국 N/A, 한국 40.2% / MSI 0.753은 기존 export 그대로다.
- Build-Up은 기존 한국 extreme_count와 persistent/모니터링 상태를 사용한다. 임의 acceleration/proximity/cross-market difference 점수를 추가하지 않는다.
- stress=1은 얇은 황색 표식으로만 표시한다. 새로운 스트레스 사건 판정으로 확장하지 않는다.
- SHAP export가 없어 설명과 연결 미지원 안내만 제공한다. 기존 요인·방법론 설명과 Portfolio 팩터 표를 보존한다.
- Portfolio는 기존 응답만 표시한다. Phase 7B 연구용 VaR/ES/MDD는 공개 계약에 없어 연결하지 않는다.

## 최종 구현 결과

### 페이지와 컴포넌트

- `/`: RiskOverview, RiskExplorer, CurrentObservationRail 신규 구현. 기존 카드 두 개+분리 차트를 시간 탐색 중심의 비대칭 레이아웃으로 대체했다. Build-Up, Cross-Market Context, 최근 운영 관측 로그와 접이식 성능/사례/인사이트를 연결했다.
- `/portfolio`: 좌측 Holdings Editor + 우측 진단/시나리오/What-if 작업 탭. 입력 수정→결과 무효화, 같은 기준의 before/after, 선택 불가 후보 차단을 유지했다. 시장 문맥은 접이식으로 남겼다. 카탈로그·시나리오·분석 초기 요청은 개별 성공 결과를 보존해 부분 오류 때 입력 목록까지 사라지지 않게 했다.
- `/us`, `/korea`, `/breadth`, `/validation`, `/cases`, `/sources`, `/methodology`: 기존 내용/계산/다운로드/선택 기능을 유지하며 공통 shell·색상·차트·표·설명·상태 체계를 적용했다.
- 공통: desktop workspace bar, 모바일 메뉴 focus trap/Escape 복귀, 본문 skip link, reduced-motion, 고대비 focus ring, 기존 로컬 폰트 사용. 이미지·네온·글로브·추가 UI 라이브러리를 도입하지 않았다.
- 인터랙션: Explorer Risk Score/MSI 및 기간 전환·session 유지·pointer 관측·키보드 슬라이더·정확한 날짜 결합, 기존 차트 hover/slider, 근거 접기/펼치기, accessible workspace tabs, 로딩 skeleton, empty/error와 재시도, 모바일 분석 완료 시 결과 영역 이동.
- 모바일은 단순 축소 대신 전용 차트 좌표계와 날짜 레이블 수를 사용한다.

### 변경 파일

- `frontend/package.json`: `test:explorer` 스크립트만 추가, 새 의존성 없음.
- `frontend/src/app/globals.css`: 공통 다크 디자인 시스템·반응형·접근성 스타일.
- `frontend/src/components/dashboard-shell.tsx`, `dashboard-view.tsx`: 공통 탐색 및 홈 구성.
- `frontend/src/components/risk-overview.tsx`, `risk-explorer.tsx`, `frontend/src/lib/risk-explorer.ts`: 신규 홈과 순수 데이터 표시 보조 함수.
- `frontend/src/components/market-chart.tsx`, `research-panels.tsx`: 기존 차트/표를 다크 팔레트로 조정. 계산과 데이터 출처 보존.
- `frontend/src/components/portfolio/portfolio-view.tsx`, `portfolio-panels.tsx`, `portfolio.module.css`: 전문 워크스페이스·기존 분석 시각화·상태 처리.
- `frontend/scripts/check-risk-explorer.mjs`: exact-date, null gap, MSI 개별 축·Risk Score 고정 축 검증.
- `scripts/check_fintech_ui_browser.py`: 기존 Chromium과 설치된 websockets를 사용하는 로컬 CDP 브라우저 검사. 외부 사이트를 열지 않는다.
- 본 설계/결과 문서 및 `FINTECH_UI_VALIDATION.json`.

### 실제 검증 결과

- Python 전체 **304 passed**, 기존 Starlette/httpx deprecation warning 1건. 첫 실행은 SIGTERM으로 종료되어 재실행한 최종 결과를 기록했다.
- eslint, TypeScript `tsc --noEmit`, test:charts, test:explorer, test:integration, test:render, production build 모두 통과.
- 기존 API 계약 캡처를 ee301f6 기준과 대조: 기존 28개 단일 종목 응답 해시와 before/after/compare, health/universe/scenarios, 기존 OpenAPI 경로·스키마 모두 동일.
- 실제 Chromium 156: 1440/768/390px × 9개 페이지, 가로 overflow 없음, main/h1 유일성, 입력 접근 가능 이름과 빈 버튼 이름 검사 통과.
- 실제 API로 한국 후보 차단·전각 티커 검색·입력 변경 시 이전 결과 제거·재분석·스트레스·What-if 실행을 확인했다. 23.4%→16.9% 헤드라인은 기존 실제 before/after 응답을 반올림한 표시이며 새 수치가 아니다.
- Explorer 선택 유지와 키보드 관측일 변경, 영어 유지, 탭 키보드, 지연 요청 skeleton, 차단 요청 error·empty 및 retry, 모바일 Escape 포커스 복귀, reduced-motion 확인 포함 **32개 브라우저 검사 통과**, JavaScript 예외 0개.
- 핵심 본문/보조 색상과 Surface 대비는 각각 **15.97:1 / 6.94:1**. 페이지 전체의 모든 합성 배경에 대한 WCAG 인증이나 스크린리더 수동 감수는 수행하지 않았다.
- 스크린샷을 직접 확인해 모바일 축 글자가 작은 문제를 수정한 후 재검사했다. 로컬 검토 파일: `/tmp/mpri-ui-check/1440-home.png`, `390-home.png`, `1440-portfolio.png`, `desktop-whatif.png`, `portfolio-error.png`. 가격·분석 원본 응답과 스크린샷을 저장소에 추가하지 않았다.
- Chromium에 필요한 누락 공유 라이브러리는 /tmp에만 내려받아 압축 해제했다. 시스템 설치·프런트엔드 패키지 추가·운영 서비스 변경은 없었다.

### 보존·안전 상태

개발 시작 시 브랜치는 feature/portfolio-universe-phase7, HEAD ee301f6였고 Phase 7B는 미커밋 파일이었다. 작업 중 저장소 상태가 **feature/mpri-nextgen-ui / 453bb94**로 바뀌었으며 Phase 7B가 해당 로컬 커밋에 포함된 것을 확인했다. 이 상태를 되돌리거나 다시 커밋하지 않았다. 453bb94 대비 src/data/config/analysis/tests 및 Phase 7B 보고서에 diff가 없음을 확인했다. 이번 UI 작업으로 commit/push/main 병합/배포를 수행하지 않았다.

Frozen V1, Stress Validation, backend API, 실제 데이터 export, Phase 7B 가격 엔진·권리 장부는 변경하지 않았다. 현재 미국 N/A, 연구/운영 날짜 구분, 미승인 종목 분석 차단은 그대로다. 원본 로그의 과거 점수는 현재값 대신 사용하지 않는다.

### 미완료·후속 범위

SHAP export/가속도 등 추가 지표와 Portfolio 공개 VaR/ES/MDD는 데이터 계약에 없어 생성하지 않았다. 라이브 갱신이나 신규 종목 승인을 하지 않았다. Firefox/Safari, 실제 iOS/Android 기기, 수동 스크린리더 전체 감수는 미실행이며 현재 Chromium 검증이 이를 보증하지 않는다.

### 로컬 미리보기

기존 서비스와 충돌을 피하도록 API 8107, 웹 3107을 사용한다. 검증용 서버는 완료 후 종료했다. 재실행은 별도 터미널에서:

```bash
# 터미널 1: 저장소 루트
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m uvicorn src.portfolio.server:app --host 127.0.0.1 --port 8107

# 터미널 2: 저장소 루트에서 frontend로 이동
cd frontend
PORTFOLIO_API_INTERNAL_URL=http://127.0.0.1:8107 npm run dev -- --hostname 127.0.0.1 --port 3107
```

브라우저: http://127.0.0.1:3107 / 포트폴리오: http://127.0.0.1:3107/portfolio

Sites 스킬은 로컬 개발/검증 범위로만 적용했다. 사이트 등록·소스 동기화·업로드·배포는 하지 않았다.
