# M/PRI 중단·재개 기록

작성일: 2026-11-04 (Asia/Seoul). 프로젝트를 당분간 중단한다. 이 기록은 새로운 기능/배포 승인이 아니다.

## 현재 소스와 백업

- 저장소: `tina77302/market-portfolio-risk-intelligence`.
- 작업 브랜치: `feature/render-safety-phase6`.
- Phase6 검증 완료 SHA: **`5916fff0db455db9c65138227bb4b786fb955b56`**. 중단 작업 시작 시 로컬 HEAD와 원격 브랜치 SHA가 일치했고 git status는 clean이었다.
- 이 문서만 추가 커밋해 **동일 브랜치에 push**한다. 자기 자신의 commit SHA는 파일 내용에 넣을 수 없으므로 최종 SHA는 종료 응답 및 `git rev-parse HEAD` / `git ls-remote --heads origin refs/heads/feature/render-safety-phase6`로 확인한다. Phase6 소스 커밋은 위 SHA로 고정한다.
- 로컬/원격을 재개할 때 무조건 reset하거나 main에 병합하지 않는다. 먼저 `git status`, `git branch --show-current`, `git log -3 --oneline`을 확인한다.
- `.env`, 인증정보, 연구용 raw/replay 데이터, venv/node_modules, `/tmp` Chromium 도구는 Git 백업 대상이 아니다. 삭제하지 않았지만 재개 시 임시 도구가 남아 있다고 가정하지 않는다. 실제 승인 데이터 없이 새 종목을 지원으로 바꾸지 않는다.

## Phase 1–6 결과

| 단계 | 완료한 일 / 보류 사항 | 보고서 |
|---|---|---|
| 1 | KR/EN 종목 검색·모바일·V2 카탈로그·지원 상태·검증/SHA 기반. 기존28개 보존 | [Phase1](../design/PORTFOLIO_UNIVERSE_PHASE1_KO.md) |
| 2 | 후보52개, V2 분석/비공개 실제28개 replay·검증 기반. **신규 승인0개**, 목표60–100개 분석 지원은 권리/데이터 gate에서 보류 | [Phase2](../design/PORTFOLIO_UNIVERSE_PHASE2_KO.md) |
| 3 | 공급처 가격/권리 비교·문의 초안, AnyIO thread 생성500 경로와 가상주소 제한 진단. 권리 계약·문의 발송 없음 | [Phase3](../design/PORTFOLIO_PHASE3_KO.md) |
| 4 | 계산1thread·대기최대3·deadline25초·명시적503/504·500 유지. 로컬 정상부하5,184건 통과, 기존 수치/schema 보존 | [Phase4](../design/PORTFOLIO_PHASE4_KO.md) |
| 5 | Render 읽기 전용 상태·SHA, cgroup 계측/실행 예산/롤백 계획, 기존28개 응답 일치. 실제 배포/rollback 미실행 | [Phase5](../design/PORTFOLIO_PHASE5_KO.md) |
| 6 | 웹/API4조합 실제 로컬 production E2E, 동시1/2/4·오류/복구, artifact 조회 한계 검증. 실제 배포 **NO-GO** | [Phase6](../design/PORTFOLIO_PHASE6_KO.md) |

최신 검증: Python152 passed(기존 deprecation warning1), TypeScript/lint/charts/integration/Render config/production build 통과. Chromium390/1280px에서 기존+기존, 기존웹+신규API, 신규+신규 통과. 신규웹+기존API는 catalog404로 Portfolio/Stress/What-if 차단을 확인했다. 시장 위험 화면은4조합 모두 통과했다. Phase6 정상 로컬 부하864건 전부200, peak RSS135.82MiB, OS thread2. 이는 Render 인증이 아니다.

## 미해결 문제와 NO-GO 사유

1. Render deploy list/detail GET에 artifact 재사용 가능 필드가 없다. live 이력이나 source SHA 존재만으로 rollback 성공/권한을 보장할 수 없다. 배포 직전 Dashboard의 artifact/rollback 가능 상태 확인이 필요하다.
2. 실제 Render512MiB cgroup charge·hard limit·OOM/pids/CPU quota를 관측하지 못했다. Free SSH/Shell은 미지원이다. 로컬 RLIMIT_AS512는 가상주소 제한이며 물리/cgroup 시험을 대체하지 않는다.
3. 실행 중 Python thread 강제 취소 불가, 자연 트래픽/health가 queue를 채울 가능성, OOM kill 시 JSON 오류 보장 불가. Free cold start와0.1CPU 성능은 별도 실환경 검증 대상이다.
4. 새 웹은 `/api/portfolio/v2/catalog`가 없는 구 API와 호환되지 않는다. **배포 API→웹, 두 서비스 복구 웹→API** 순서를 지킨다. 기존 웹을 유지한 API 단독 배포/복구 조합은 로컬 검증을 통과했다.
5. 기존28개 full/frozen_v1_only, 신규52개 unsupported, public V2 release0. 공개 사용 권리·실제 가격/기업행위/필수 팩터가 없으면 확대 승인하지 않는다. 기존28개의 legacy 상태를 새 라이선스 취득으로 해석하지 않는다.

## Phase 7 재개 순서 (제안, 미승인·미실행)

1. branch/HEAD/clean 상태·원격 SHA·기존5파일 manifest 및 운영 SHA를 재확인하고 Phase6 보고서/증거를 읽는다.
2. 사용자와 배포 목표 commit·대상API·계측 방식·시간대·중단/복구 담당자·승인 범위를 확정한다. 본 기록은 push 외 실제 배포/공개 시험/계측 활성화를 허가하지 않는다.
3. 기존 rollback artifact와 설정/소스 접근성을 읽기 전용으로 다시 확인한다. 불가하면 배포 보류. source rebuild는 artifact 복구와 구분한다.
4. 필요 시 별도 범위로 제한된 내부 cgroup 로그 계측을 설계·구현·로컬 테스트한다. 새 thread/공개 diagnostics endpoint/환경 값 dump를 만들지 않는다. runtime이 바뀌면 새 commit 테스트와 승인 필요.
5. 조건 충족 및 명시적 승인 후에만 API 우선 검증, 이후 웹 별도 승인. Phase5 공개 요청 예산 최대41회·동시1→2→4와 중단 기준을 사용하고 로컬864건을 공개 환경에 반복하지 않는다.
6. 실패 시 승인된 복구 절차를 사용한다. artifact/실환경 증거·승인이 없으면 NO-GO를 유지한다. 데이터 권리 확보·종목 확대는 별도 작업이다.

관련: [실행 계획](../design/PORTFOLIO_PHASE5_EXECUTION_PLAN_KO.md), [롤백 절차](../design/PORTFOLIO_PHASE5_ROLLBACK_KO.md), [Phase6 로컬 재현](../design/PORTFOLIO_PHASE6_REPRO_KO.md).

## 로컬 실행·테스트

재개 시 의존성이 없다면 기존 lock/requirements로 로컬 환경을 복원한다. 새 유료 API/계정은 필요 없다. 아래 명령은 저장소 루트 기준이며 **Render에 실행하지 않는다**.

```bash
# API: 로컬 터미널1
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python -m uvicorn src.portfolio.server:app --host 127.0.0.1 --port 8000 --workers 1

# 웹: 별도 로컬 터미널2, 기본 API upstream은 loopback8000
cd frontend
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
# 개발 모드가 필요할 때만: npm run dev -- --hostname 127.0.0.1 --port 3000
```

테스트는 서버 실행과 별도 터미널에서 한다.

```bash
.venv/bin/python -m pytest -q
cd frontend
npx tsc --noEmit
npm run lint
npm run test:charts
npm run test:integration
npm run test:render
npm run build
```

Chromium/Playwright는 시스템 로컬 설치 경로를 지정한다. `frontend/scripts/check-portfolio-search.mjs`는 API8000/웹3000 실행 후 `MPRI_PLAYWRIGHT_MODULE`, `MPRI_CHROMIUM_PATH`로 실행한다. 네 가지 version matrix와 AS512 fault/부하는 Phase6 재현 문서를 따른다. `/tmp` 경로·공유 라이브러리가 사라졌다면 복원 후 실행한다. 기존 보고서의 테스트 통과를 새 환경의 통과로 간주하지 않는다.

## 기존 Render와 롤백 기준

| 항목 | API | 웹 |
|---|---|---|
| 서비스 | mpri-portfolio-api | mpri-mvp-web |
| ID | srv-dbkp73mgekts73eq0m20 | srv-dbkp8fvf3r2c73fi28fg |
| URL | https://mpri-portfolio-api.onrender.com/health | https://mpri-mvp-web.onrender.com/ |
| 정상 deploy 기준 | dep-dbkp8krbc2fs73a0bjkg | dep-dbkp8gff3r2c73fi29l0 |
| branch | feature/mvp-release-readiness | 동일 |

정상/rollback 기준 SHA는 **`97e78366a026e9221740526087ef8082a891fa28`**. 마지막 control-plane 확인은 Phase6(2026-11-04)이며 Free/Singapore/1 instance/자동 배포 off였다. 재개 시 다시 확인한다. GitHub 작업 branch를 운영 branch와 혼동하지 않는다. health200/as_of2026-10-23, universe28/scenario3, before23.38%/after16.94% 및 전체 응답/SHA가 복구 기준이다. 현재 배포는 Phase6 신규 코드가 아니다.

## 이번 종료 점검

- 기존28개 snapshot5파일 실제 SHA 및 승인5916fff의 bytes 일치. Frozen V1/시장 운영 데이터·runtime·Render 설정 변경 없음.
- 실행 경로와 명령 파일명을 확인한 결과 이 프로젝트의 잔여 로컬 uvicorn/Next 개발 서버 없음. 실행 중 에이전트 도구는 종료하지 않았다. 다른 프로젝트 프로세스·Docker 컨테이너는 조회/종료/변경하지 않았다.
- 공개 상태 확인: API health와 웹 root **각1회 GET**, 분석/부하 요청0. 결과는 아래 최종 기록 참조. 최소 상태 확인은 장기 가용성·분석 전 기능 검증이 아니다.
- 로컬 의존성·연구파일·모델·credentials·임시 디렉터리를 일괄 삭제하지 않았다. 재개에 필요한 Git 추적 소스/보고서는 원격 백업하고 비밀정보/비공개 연구자료는 포함하지 않는다.

최종 health 기록(2026-11-04 UTC): API06:13:44 요청에서200/ok/as_of2026-10-23. 웹 첫 요청은45초 TimeoutError, 추가1회06:15:31 GET에서 **200 HTML**(응답 시작 약644ms)을 확인했다. 원인은 cold start 등으로 확정하지 않았다. 총 API1회+웹2회, 재시작/재배포0. 웹 전체 동작이나 분석 전 기능을 재검증한 것은 아니다.
