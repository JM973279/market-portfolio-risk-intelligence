# M/PRI Phase 5 — Render 실환경 검증 사전 준비

작업일2026-11-04 (Asia/Seoul). 기준 branch `feature/portfolio-server-stability-phase4`, commit `1db2dc2a1563c5c5096f32bc1640ac121e152a38`. 새 branch `feature/render-validation-phase5`.

## 판단

**로컬 회귀와 사전 문서는 준비됐지만 지금 실제 배포/부하 검증을 시작할 수는 없다.** 별도 배포·복구·제한된 요청 승인, rollback artifact 가용성 재확인, Free에서 가능한 내부 cgroup 계측의 구현·검증이 남았다. 이번 변경은 문서와 sanitized 관측 JSON뿐이다. 서비스 설정·재시작·재배포·공개 부하 시험·push·main/PR 병합·유료 서비스/결제는 하지 않았다.

Phase4 runbook의 Free shell 접근 전제를 보완했다. Free는 SSH와 Dashboard Shell이 없으므로, 실제512MiB cgroup 증거를 얻으려면 향후 별도 승인된 앱 내부의 제한된 로그 계측이 필요하다. CPU/RAM plan과 live status를 조회한 것을 실제 컨테이너 안정성 검증으로 표시하지 않는다.

## 기존 배포 상태 — 읽기 전용 실측

Render API GET과 공개 GET만 사용했다. 제어면 확인 시작은 **2026-11-04 05:38:47 UTC**, 공개 확인 시작은05:39:06 UTC다. 인증은 기존 로컬 CLI 설정에서 메모리로만 읽었고, 인증정보·환경변수 값·원시 응답을 보고서/Git에 저장하지 않았다. CLI 설정도 변경하지 않았다.

| 항목 | API | 웹 |
|---|---|---|
| 서비스 | mpri-portfolio-api | mpri-mvp-web |
| URL | https://mpri-portfolio-api.onrender.com/health | https://mpri-mvp-web.onrender.com/ |
| 공개 상태 | 200 JSON, status ok, as_of2026-10-23 | 200 HTML |
| 단일 요청 전체 시간 | 43,516.99ms | 52,601.77ms |
| live SHA | 97e78366a026e9221740526087ef8082a891fa28 | 동일 |
| branch | feature/mvp-release-readiness | 동일 |
| plan / 지역 / instances | Free / Singapore / 1 | 동일 |
| 자동 배포 / suspend | off / not suspended | 동일 |
| root / runtime | repository root / Python | frontend / Node |
| health path | /health | / |

두 live deploy ID는 API `dep-dbkp8krbc2fs73a0bjkg`, 웹 `dep-dbkp8gff3r2c73fi29l0`다. 과거 문서에만 의존하지 않고 현재 GET 결과로 확인했다. 설정 updatedAt은 읽기 전용 확인 전후 동일했다. API start command에서 worker1을 확인했고 원문 대신 start/build command SHA를 기록했다. 프로세스의 실제 thread 수는 shell이 없어 이번에 관측하지 못했다.

공식 Free compute 사양은 **0.1 CPU / 512 MB**다. 실제 CPU quota·cgroup memory.max는 미관측이며 MB 표기를 임의로512MiB로 바꾸지 않았다. 긴 health/root 응답은 idle spin-up과 양립하지만 원인을 확정하지 못한다. 웹 시간은 HTML body 전체 읽기까지 포함한다. warm 재측정·keep-alive·분석 POST·공개 Chromium 순회는 수행하지 않았다. 기존 서비스 설정/재시작 요청은 없었지만 일반 GET이 Free idle 서비스를 깨울 수 있다.

환경변수는 **이름만** 기록한다:

| API | 웹 |
|---|---|
| OMP_NUM_THREADS | NODE_VERSION |
| OPENBLAS_NUM_THREADS | PORTFOLIO_API_INTERNAL_URL |
| PORTFOLIO_API_CORS_ORIGINS | |
| PORTFOLIO_API_DOCS_ENABLED | |
| PYTHON_VERSION | |

Render 관리 API에 등록된 이름 목록이며 자동 주입 시스템 변수 전체나 env group의 실제 적용 값을 보증하지 않는다. CORS/URL/런타임 버전 등 환경변수의 실제 값은 저장하지 않았다. 향후 API1worker·BLAS1을 실제 process에서도 확인해야 한다.

증거: [Render 상태](PORTFOLIO_PHASE5_RENDER_STATE.json), [공개 health](PORTFOLIO_PHASE5_PUBLIC_HEALTH.json). 공개 요청은 **API GET1 + 웹 GET1**이며 분석/부하 요청은0이다.

## 실행·복구 준비 결과

[실환경 실행 계획](PORTFOLIO_PHASE5_EXECUTION_PLAN_KO.md)은 실제 cgroup 계측 설계, 동시1/2/4 단계, API/웹 합계 기본39회·cold 재시도 포함최대41회, 중단 기준을 정했다. 기존 Phase4의 큰 로컬 행렬을 공개 환경에 복제하지 않는다. 500/503/504를 유발하는 fault 주입은 로컬/승인된 격리 환경에 한정하고 운영 데이터·timeout을 변조하지 않는다.

[롤백 계획](PORTFOLIO_PHASE5_ROLLBACK_KO.md)은 현재 정상 SHA와 두 live deploy를 복구 기준으로 고정한다. Free 이전2개 artifact 제한, rollback 시 설정 적용 범위, 복구 health/분석 수치·SHA 기준을 명시했다. **실제 deploy/rollback 검증은 미실행**이다.

호환성 확인에서 다음 차이가 중요하다. 구 웹은 V1을 사용해 새 API와 계약이 맞지만, 새 웹은 catalog가 필요하다. 구 API의 catalog404와 새 API200을 로컬에서 확인했다. 따라서 API만 먼저 검증하고 기존 웹을 유지하는 것이 적절하다. 두 서비스를 모두 바꿨다면 **웹부터 rollback 후 API rollback**한다. 구 웹+새 API의 공개 브라우저 조합은 이번에 실행하지 않았다.

## 사전 회귀 결과

- Python 전체 **152 passed**, Starlette/httpx deprecation warning1개. Hidden Risk·베타·위험기여·Stress·What-if·V2 gate·리소스 오류 시험 포함.
- TypeScript `tsc --noEmit`, ESLint, charts, integration, Render config, production build 모두 통과.
- **로컬** Chromium E2E390/1280px 통과: KR/EN 회사명·NFKC ticker·키보드·unsupported 이유/차단·결과 무효화. 공개 서비스 E2E는 실행하지 않았다.
- 현재 정상97e783 소스를 별도 임시 디렉터리에 `git archive`로 추출해 같은 Python 환경의 TestClient로 비교했다. V1 health/universe/scenarios, before/after 전체 분석·compare 전체 응답, invalid422, 기존 OpenAPI paths/components가 일치한다.
- 기존 **28개 각각 단일100% 보유**의 전체 분석 응답 canonical SHA가 구 버전과28/28 일치한다. 실제 기존 데이터만 사용했으며 새 가격/권리/등록은 추가하지 않았다. 포트폴리오 전 조합을 전수 검사한 것은 아니다.
- manifest의5개 파일 실제SHA를 확인하고97e783의 bytes와도 대조했다. 기존 데이터·Frozen V1·시장 export·config는 유지됐다. Phase5에서 runtime code와 운영 설정을 변경하지 않았다. catalog는 기존28 full+신규52 unsupported, 공개 V2 release0 상태 그대로다.

기계 판독 결과와 기존28 응답 해시는 [회귀 기록](PORTFOLIO_PHASE5_REGRESSION.json)에 있다. 분석 수치는 before 변동성23.38%, after16.94%로 일치한다. 정확한 SHA 보존은 로컬 artifact에 대한 검증이며, 이번 공개 health만으로 서버의 모든 운영 파일을 다운로드·검증한 것은 아니다.

## 배포 전 남은 위험·승인 범위

1. **승인 미취득**: 최종 deploy commit·대상API·시간대·제한 요청예산·중단/복구 권한을 별도로 승인받아야 한다. 이번 branch의 push도 별도다. 웹 배포와 branch/환경 설정 변경을 묶어 추정하지 않는다.
2. **실제 cgroup 증거 없음**: Free shell 미지원. 향후 안전한 내부 계측 commit이 필요하고, 이를 추가하면 현재 source와 달라지므로 다시 테스트·승인을 받아야 한다. 유료 전환으로 해결하지 않는다.
3. **roll back availability**: 기존live 이력은 확인했지만 배포 시점의 artifact 사용 가능성은 미확정이다. 목표 artifact를 확보하지 못하면 배포를 보류한다. SHA rebuild는 동일 build의 보장이 아니다.
4. **자원·동시성**: 실제0.1CPU, natural traffic, 플랫폼 health가 계산 queue4개를 공유할 때503 또는 health 실패 가능성이 있다. 실행 중 thread 강제 취소 불가, cgroup OOM kill의 정상JSON 보장 불가. 로컬 RSS136MiB 수치를 Render 인증으로 간주하지 않는다.
5. **cold/비용 한도**: 이번 단일GET이 느렸다. warm 분석 성능·idle 복귀·Free workspace 잔여 시간/대역폭은 이번에 검증하지 않았다. Billing·결제 정보를 수집하거나 결제 상태를 추정하지 않았다.
6. **버전 비대칭**: 새 웹을 구 API와 조합하지 않는다. API 단독 검증과 정확한 복구 순서가 필요하다. 신규52개 공개 데이터 사용 권리 문제도 여전히 미해결이다.

공식 출처(2026-11-04 확인): [Compute plans](https://render.com/docs/compute-plans), [Free limitations](https://render.com/docs/free), [SSH/Shell compatibility](https://render.com/docs/ssh), [Rollback](https://render.com/docs/rollbacks), [Deploys](https://render.com/docs/deploys). 사양·플랫폼 제약과 실제 관측을 구분해 사용했다.
