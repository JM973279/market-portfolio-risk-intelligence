# M/PRI 메인 — Signal Atlas + Temporal Lens

브랜치 `feature/mpri-nextgen-ui`, HEAD `453bb94`. 기존 미커밋 UI 작업을 보존하고 메인 화면만 추가 구현했다. commit, push, Render 배포를 수행하지 않았다.

## 이전 화면과 달라진 점

- 메인의 고정 좌측 사이드바, 큰 문구 Hero, 우측 관측 패널, 반복 카드 구성을 제거했다.
- 상단 탐색에 시장 현황·미국·한국·Portfolio를 배치하고 나머지 페이지는 전체 메뉴로 연결했다. 한국어/영어, 키보드·Escape 조작을 지원한다. 메인에서만 이 탐색 구조를 적용했다.
- 화면 진입 즉시 미국·한국의 최신 예측 위험 점수(Risk Score), MSI, 실제 점수 관측일, 수집 기준일과 자료 상태를 확인한다. 제목은 ‘시장 위험 현황’이며 추상적인 마케팅 문구를 사용하지 않는다.
- 과거 시계열과 확산도 행렬을 하나의 시간 선택 상태에 연결했다. 테두리 카드 대신 구분선·행 정렬·큰 수치로 위계를 구성했다.
- 기본 표시는 양국 예측 위험 추이 + 한국 확산도 6개 행 + 저장된 지속 악화 판정이다. MSI 또는 네 시계열 동시 표시로 전환할 수 있다.
- 데스크톱 기본은 6개월, 모바일 기본은 3개월이다. 모바일 1개월 기본은 실제 과거 예측 점수가 없는 구간이라 초기 시각화가 비었으므로, 실제 기록을 볼 수 있는 기본 기간으로 보완했다. 사용자가 저장한 기간은 우선 복원한다.

## 구현 인터랙션

1. **전체 기간 탐색**: 미국·한국의 실제 과거 예측 점수를 독립된 축의 두 소형 시계열로 제공한다. 빈 구간과 두 시장의 시작일 차이를 보존한다.
2. **구간 드래그**: 전체 기간에서 포인터로 구간을 선택한다. 시작/종료 조절자를 별도로 제공해 키보드·터치로도 조정한다. 클릭은 기존 구간 길이를 유지하며 선택 지점으로 이동한다.
3. **기간 선택**: 1/3/6개월, 1년, 전체와 선택일 중심 확대/축소. 시간 경계는 실제 자료 범위 안으로 제한하고 최소 두 관측일을 유지한다.
4. **연동 시각화**: 선택 구간에 따라 양국 예측 점수·MSI와 한국 확산도 행렬이 함께 바뀐다. hover로 날짜 값을 확인하고 클릭으로 날짜를 고정한다.
5. **관측일 탐색**: 날짜 직접 입력, 관측일 슬라이더, 이전/다음 버튼과 키보드 조작. 자료가 없는 날짜를 직접 선택하면 N/A를 표시한다.
6. **확산도 행렬**: 6개 지표의 기존 백분위와 null을 그대로 표시한다. 황색은 원본 백분위 90% 이상, 빈칸은 자료 없음이다. 지속 악화 행은 기존 persistent 값만 사용한다.
7. **관측 근거**: 같은 날짜의 실제 양국 값·공식 MSI 임계값, 선택 확산도 지표의 종목 비율/백분위, 한국 연구의 저장된 판정, 자료 출처를 펼쳐 확인한다.
8. **선택 유지**: 기간·표시 지표·선택일을 sessionStorage에 저장하고 유효한 자료 구간에서 복원한다. 사용자 보유 종목 등은 저장하지 않는다.

## 데이터 정확성

- `currentOperationalPoint`를 변경 없이 재사용한다. 미국의 검증 보류 상태는 Risk Score/MSI N/A이며, 과거 점수를 대신 표시하지 않는다. 한국은 기존 운영 자료의 관측일·40.2%·MSI 0.753을 그대로 표시한다. 이 값이 오늘의 실시간 값이라고 표현하지 않는다.
- 최신 운영 현황과 과거 연구 자료를 분리한다. 운영 점수를 역사적 OOS 선에 이어 붙이지 않는다.
- 예측 위험 점수는 향후 10거래일 내 시장 스트레스 위험의 예측 지표, MSI는 해당 관측일의 관측 스트레스 수준으로 설명한다. 예측 점수를 보정된 발생 확률로 표현하지 않는다.
- MSI는 시장별 별도 축과 기존 날짜별 임계값을 사용한다. 독립 모델 간 점수 차이나 위험 순위를 산출하지 않는다.
- `signalPath`, `finiteValue`, `metricDomain`, 정확한 날짜 조회 보조 함수를 재사용했다. null 구간은 선을 끊고 0은 유효한 값으로 처리한다. 보간·재학습·임계값 변경·새 가속도/축적 점수를 만들지 않았다.
- 행렬 값은 기존 monitor export의 백분위/종목 비율/persistent를 사용한다. 가격으로 새 지표나 백분위를 계산하지 않는다. 미세한 색상 매핑은 표현 방식이며 모델 수치가 아니다.
- 하단 상태는 **한국 연구 판정**으로 명시한다. 양국의 통합 판정이나 글로벌 위험 등급이 아니다.
- SHAP 원본이 없어 새 설명값·기여도 순위를 생성하지 않는다.

## 이번 변경 파일

기존 파일 중 이번 작업에서 추가 변경한 파일은 아래 2개뿐이다. 다른 페이지의 이전 미커밋 디자인 변경을 이번 작업의 변경으로 다시 계산하지 않았다.

- `frontend/src/components/dashboard-shell.tsx`: 메인 경로에만 전용 상단 탐색과 레이아웃 적용. 다른 경로의 기존 shell 유지.
- `frontend/src/components/risk-overview.tsx`: 메인 구성 교체.

신규 파일:

- `frontend/src/components/home-navigation.tsx`
- `frontend/src/components/signal-atlas.tsx`
- `frontend/src/components/signal-atlas.module.css`
- `frontend/src/lib/atlas-data.ts`
- `frontend/scripts/check-signal-atlas.mjs`
- `scripts/check_signal_atlas_browser.py`
- 본 문서 및 `SIGNAL_ATLAS_VALIDATION.json`

작업 시작 시 frontend/src, src, data, config, analysis, tests의 파일 SHA를 /tmp에 보관했다. 위 기존 2개 파일을 제외한 기존 파일의 SHA가 모두 동일함을 확인했다. 따라서 Frozen V1, Phase 7A·7B, Stress Validation, API, 실제 export와 다른 페이지 본문은 이번 작업에서 변경하지 않았다.

## 검증

- Python 전체 **304 passed**, 기존 Starlette/httpx deprecation 경고 1건.
- eslint, TypeScript(`tsc --noEmit`), production build 통과.
- 기존 test:charts / test:explorer / test:integration / test:render 통과.
- 신규 `check-signal-atlas.mjs`: 기간 경계, 관측일 선택, null/0, 원본 백분위, 90% 색상 임계, 실제 export 비변경 검사 통과.
- API 계약 캡처를 기존 기준 결과와 대조: 28개 단일 자산 응답 해시와 기존 before/after/compare·health/universe/scenarios·OpenAPI 경로/스키마 동일.
- 실제 Chromium 1440×1000 / 390×844: 최신 수치·날짜·검증 상태, 사이드바/Hero/우측 패널 제거, 원본 날짜별 수치, 결측일 N/A, 네 시계열 전환, 확대/축소, 실제 포인터 드래그, 세션 복원, 키보드 날짜 이동, 관측 근거, 한국어/영어, 메뉴 Escape와 9개 페이지 링크, 가로 overflow·입력 이름·유일 main/h1 검사.
- JavaScript 예외 없음. 브라우저 검사 요약은 별도 JSON과 /tmp 결과에 기록한다. Chromium 검사는 전체 WCAG 인증이나 실제 모바일 기기 감수를 대신하지 않는다.

## 스크린샷

실제 Chromium으로 생성했으며 원본 PNG는 `/tmp/mpri-signal-atlas/`에만 두었다.

- `1440-main.png`: 1440px 초기 화면
- `1440-full.png`: 데스크톱 전체 메인
- `390-main.png`: 390px 초기 화면
- `390-full.png`: 모바일 전체 메인
- `1440-selected.png`, `390-selected.png`: 기간/날짜 탐색 후 화면
- `1440-en.png`, `390-en.png`: 영어 화면

데스크톱·모바일 스크린샷을 직접 확인했다. 화면 크기에서 실제 자료가 보이도록 기본 구간과 정보 배치를 조정했고 허구의 값을 추가하지 않았다.

## 로컬 확인

본 작업은 별도 포트 3118에서만 검증했다. 검증용으로 띄운 서버는 완료 시 종료하며, 기존 로컬 서비스는 종료하지 않는다.

```bash
cd frontend
npm run dev -- --hostname 127.0.0.1 --port 3118
```

http://127.0.0.1:3118 에서 메인을 확인할 수 있다. 메인은 기존 정적 export를 사용하므로 별도 Portfolio API 서버 없이 조회된다. 다른 페이지 추가 수정과 전체 사이트 한국어 교체는 보류했다.
