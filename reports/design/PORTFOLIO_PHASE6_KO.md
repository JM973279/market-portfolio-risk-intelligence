# M/PRI Phase 6 — Render 배포 안전성과 웹/API 호환성

2026-11-04 (Asia/Seoul). 기준 branch `feature/render-validation-phase5`, commit `85f5f20dc51ad2b6b748e3991a36ea3192ae246a`. 작업 branch `feature/render-safety-phase6`.

## 최종 판단: NO-GO (현재 실제 Render 배포)

**API 선배포의 로컬 호환성 조건은 통과했다.** 그러나 기존 Render artifact의 재사용 가능성과 실제512MiB cgroup 동작은 확인되지 않았다. 별도 배포·복구 승인도 없다. 따라서 현재 실제 배포는 **NO-GO**다. 이는 로컬 검증 실패라는 뜻이 아니라 필수 실환경 증거가 아직 없다는 판단이다. 아래 조건을 확보한 뒤 제한된 실환경 검증을 다시 승인받을 수 있다.

이번에는 테스트·진단 스크립트와 보고서만 추가했다. runtime code, Frozen V1, 시장 파이프라인, 데이터, 운영 설정은 변경하지 않았다. 공개 application 요청0, Render 수정/재시작/재배포/rollback0, paid 생성·결제0, main/PR 병합0, push0이다. Render 접근은 GET만 사용했다.

## 검증한 버전과 방법

- 기존 API/웹: 정상 운영 SHA `97e78366a026e9221740526087ef8082a891fa28`를 `git archive`로 추출한 소스.
- 신규 API/웹: 기준85f5f20 소스. Phase5가 문서만 추가했으므로 runtime은 Phase4 `1db2dc2a1563c5c5096f32bc1640ac121e152a38`와 같다.
- **두 웹 모두 production build**, loopback3001(기존)/3000(신규), 실제 Next rewrite → loopback8000 API를 사용했다. API를 기존→신규로 교체하며 네 조합을 실행했다. 정상 API 응답을 브라우저 mock으로 대체하지 않았다.
- Chromium **390/1280px** 각각에서 정상 분석 요약·베타·상관행렬·Stress3개·What-if10행, 잘못된 가중치 차단/결과 무효화, 시장 KR/US 화면, 오류/복구를 검증했다. 정상 V1 universe/scenarios/before/after/compare **전체 JSON**은 기존 API 계약과 일치했다.
- 422/500/503/504·연결 실패는 브라우저 route에만 주입해 안내와 결과 제거를 검증했다. 실제 서버 오류 경로는 별도의 루프백 fault 프로세스에서 검증했다. 정상 응답·오류 주입·실제 오류 시험을 구분했다.
- 기존 웹 최초 임시 빌드에서 외부 node_modules symlink를 Turbopack이 거부했다. 동일 의존성을 임시 트리 내부로 복사한 뒤 소스/설정 수정 없이 빌드 통과했다. 이 로컬 재빌드는 과거 Render artifact의 binary reproduction 증명이 아니다. 두 버전 모두 현재 설치된 동일 의존성을 사용했다.

## API·웹 호환성 매트릭스

| 웹 + API | Portfolio/Stress/What-if | 시장 위험 화면 | 오류 처리 / 계약 | 판정 |
|---|---|---|---|---|
| 기존 + 기존 | 통과 | 통과 | 통과 | PASS |
| **기존 + 신규** | **통과** | 통과 | 기존 V1 계약 일치, 오류 안내 통과 | **PASS: API 선배포 가능 조합** |
| 신규 + 신규 | 통과 | 통과 | 통과 | PASS |
| 신규 + 기존 | catalog404로 세 기능 차단 | 통과 | V1 API 자체는 일치. UI 오류 표시·선택/분석 차단, crash 없음 | **INCOMPATIBLE** |

각 판정은 두 viewport에서 확인했다. 페이지 JavaScript 예외0. 시장 KR 현재 Risk40.2%, MSI0.753, 임계1.115, 날짜2026-11-02를 유지했다. US 현재4개 N/A와 과거2026-10-02 Risk10.0% 분리를 확인했다. 시장 화면은 Portfolio API가 달라도 동일한 운영 export를 사용한다.

새 웹은 초기 Promise.all에서 `/api/portfolio/v2/catalog`를 요구한다. 기존 API에는 해당 route가 없어404가 발생하면 분석 요청 자체가200이어도 universe/analysis state가 설정되지 않는다. 초기 Hidden Risk·Stress·What-if가 나타나지 않고 Analyze/Compare가 비활성화된다. fallback을 임의 추가하거나 권리 gate를 완화하지 않았다. 오류 주입 통과를 이 조합의 기능 호환 성공으로 표시하지 않는다.

증거: [4조합 E2E 결과](PORTFOLIO_PHASE6_COMPATIBILITY.json), [계약/28개 보존](PORTFOLIO_PHASE6_REGRESSION.json). 새 스크립트 `scripts/check_portfolio_phase6.cjs`는 loopback 대상만 허용한다.

## 롤백 준비 상태

Render GET 시각 **2026-11-04 06:03:05 UTC** 기준:

| 서비스 | 현재 live deploy | SHA / 상태 |
|---|---|---|
| API srv-dbkp73mgekts73eq0m20 | dep-dbkp8krbc2fs73a0bjkg | 97e783… / live |
| 웹 srv-dbkp8fvf3r2c73fi28fg | dep-dbkp8gff3r2c73fi29l0 | 97e783… / live |

두 서비스는 기존 branch `feature/mvp-release-readiness`, Free, Singapore,1 instance, 자동 배포 off다. Phase5와 설정 updatedAt/branch/root/자동 배포가 동일했다. start/build command는 원문 대신 SHA, 환경변수는 이름만 보관했다. API 이전 deploy dep-dbkp746gekts73eq0n2g는 같은 SHA의 deactivated 상태다. 복구 목표는 최종 설정이 반영된 현재 live ID다.

- 기존 source는 로컬에 존재하며, 원격 `feature/mvp-release-readiness`도97e783을 가리킴을 `git ls-remote`로 확인했다. 기존 API 로컬 실행·웹 로컬 rebuild도 통과했다. Render의 Git provider 접근 권한, 당시 환경 값, 과거 build 재현까지 증명한 것은 아니다.
- deploy **목록 GET과 개별 detail GET**에 artifact/rollback 가용성 필드가 없었다. live/deactivated 이력만으로 artifact retention 또는 rollback action 권한을 확정할 수 없다. API POST를 시도해 권한을 시험하지 않았다.
- 공식 rollback 기능은 존재하고 Free는 이전2개 deploy 범위로 제한된다. **우리 목표 artifact의 재사용 가능 여부는 미확인**이다. Dashboard의 목표 artifact/rollback 가능 표시와 확인 단계까지 배포 직전에 읽기 전용 확인해야 한다. 확인 페이지에서 실제 rollback을 실행하지 않는다. 현재 live는 다음 deploy 뒤 이전 artifact가 되므로 불필요한 deploy 반복을 피한다.
- artifact가 없을 때 source SHA 수동 rebuild는 대안일 뿐 동일 artifact가 아니다. 의존성/환경/외부 build 조건이 달라질 수 있다. 이번 로컬 rebuild 통과가 운영 rollback 성공 보장은 아니다.

[선별된 Render 증거](PORTFOLIO_PHASE6_RENDER_READINESS.json). 실제 rollback은 수행하지 않았다.

### 한 서비스만 rollback할 때

- API만 신규로 올리고 기존 웹을 유지했다면 API rollback은 기존+기존으로 돌아가므로 호환된다.
- 둘 다 신규일 때 **웹만 먼저 rollback**하면 기존웹+신규API로 남아 검증된 조합이다. 이후 API를 rollback할 수 있다.
- 둘 다 신규인데 **API만 rollback**하면 신규웹+기존API로 바뀌어 Portfolio가 차단된다. 이 조합을 정상 복구 완료로 표시하면 안 된다. 웹도 복구하거나 사전 승인된 호환 대책이 필요하다.

## 서버 안정성 재검증

Phase4의 `PortfolioExecutor`는 worker1·전체 in-flight4(실행1+대기최대3), queue+compute25초 deadline을 유지한다. async HTTP wrapper를 통해 AnyIO implicit pool을 우회한다. timeout/client task 취소 시 실제 작업이 끝나거나 dequeue될 때까지 slot을 보유하고 replacement thread를 생성하지 않는다. 동일 compare 입력에 대한 단일 계산도 유지했다.

### 정상 실제 데이터 부하 (모두 로컬)

기존 Phase4 harness를 사용해 AS512 기본/AS512 AnyIO4/주소무제한 각각 새 프로세스1회, V1/V2 analyze/compare 및 최대10보유 analyze/compare를 동시1/2/4로 각12요청 실행했다. **조건당288건, 합계864건 모두200**이다. cold·health·diagnostics는 분모에서 제외했다. V2 수치 부하는 기존 실제28개 private research replay이고 공개 registry는 미승인 상태를 유지했다.

| 조건 | 오류 / 요청 | peak RSS MiB | VmPeak MiB | 최대 OS thread |
|---|---:|---:|---:|---:|
| AS512 기본 | 0/288 | 135.82 | 360.86 | 2 |
| AS512 AnyIO4 | 0/288 | 135.72 | 360.86 | 2 |
| 주소무제한 | 0/288 | 135.82 | 360.86 | 2 |

AS512 기본의 workload별 p95 범위: 동시1 **6.944–14.692ms**, 동시2 **16.280–29.895ms**, 동시4 **32.073–64.529ms**. 각 workload12건의 nearest-rank p95는 max와 같으며 전체 합산 p95나 SLA가 아니다. 다른 로컬 검증 작업과 CPU를 공유한 개발 환경 관측치다. 서버 main1+계산1로 OS thread2, BLAS1/uvicorn1worker였다.

### 500·503·504 실제 오류 경로

새 local fault matrix에서 **동시1/2/4 각각** 실제 주소 예약 ENOMEM→503, unknown defect→500, sleep deadline→504를 확인했다. 각 셀 요청 수는 동시 수와 같고9셀/21요청이다. 모든 셀 뒤 health200, 최종 실제 분석200으로 복구했다. 시험 deadline은0.5초, production은25초 그대로다. 최대 오류 응답시간은 ENOMEM9.994ms, unknown5008.119ms, timeout506.980ms였다. fault 시험 peak RSS 약136.01MiB/OS thread2다.

별도 기존 Phase4 overload 시험도 재실행했다. 동시8 slow요청→**5034개+5044개**, 실행 중 slot 유지로 health503, 실제 종료 후 health200·분석200. 동시4까지 정상 요청이 전부200이라는 사실과 capacity4 초과 시503이라는 동작을 구분했다. 오류를200으로 감추지 않는다. 실행 중 thread를 강제 중단할 수 없으며 영구 정지·OS OOM kill의 응답/복구는 보장되지 않는다.

증거: [원시 정상 부하](PORTFOLIO_PHASE6_BENCHMARK.json), [요약](PORTFOLIO_PHASE6_BENCHMARK_SUMMARY.json), [동시1/2/4 fault](PORTFOLIO_PHASE6_FAULT_MATRIX.json), [overload/복구](PORTFOLIO_PHASE6_FAULTS.json).

## 실제512MiB cgroup 검증 가능 여부

**이번에 불가능/미확인**이다. Render Free는 SSH/Dashboard Shell이 지원되지 않는다. 현재 production에는 내부 cgroup 계측이 없다. 로컬 cgroup2는 memory.max=max이고 현재 사용자에게 group 디렉터리 write 권한이 없다. 로컬 AS512는 주소공간 제한이며 실제 Render의 charge·CPU quota·pids/OOM을 재현하지 않는다. Free plan의 공식512 MB 표기를536870912 bytes로 간주하지 않는다.

안전한 대안은 별도 승인된 **짧은 startup/event-loop 내부 계측을 private 로그에만 기록**하는 것이다. Phase5 설계대로 actual membership/mount와 읽을 수 있는 부모 제한, memory.current/max/peak/events·pids·cpu와 RSS/thread를 기록하되 환경 값·요청·token·원시 경로를 남기지 않는다. 새 thread나 공개 diagnostics endpoint는 만들지 않는다. 현재 commit에는 runtime 계측을 추가하지 않았다. 향후 구현하면 새로운 commit으로 테스트/승인이 필요하다. 로그 조회가 불가능하거나 실제 hard limit을 못 읽으면 검증 완료로 표시하지 않는다. 별도 Linux512MiB cgroup 시험은 보완 대안이며 Render 인증을 대신하지 않는다. 유료 전환/새 서비스 생성은 하지 않는다.

## 사전 회귀와 보존

- Python 전체 **152 passed**, 기존 Starlette/httpx deprecation warning1. TypeScript, lint, charts/integration/Render config, 신규 production build 통과. 기존 production build도 통과했다.
- Chromium 네 조합×390/1280px = **8개 조합/viewport** 실행. 3개 호환조합 통과, 1개 비호환조합의 예상 차단을 확인했다. “4조합 기능 전부 통과”로 집계하지 않는다.
- 기존28개 단일100% 보유 전체 분석 response SHA와 before/after/compare 전체 응답이97e783과 동일하다. V1 paths와 기존 components schema도 동일하다. 가능한 모든 포트폴리오 조합을 전수 검증한 것은 아니다.
- 커밋 대상12개 파일의 비밀정보·인증키·개인정보 패턴 및 기존 로컬 인증값 포함 여부를 점검했다. 일치 항목이 없었고 환경 값·원시 서비스 응답·1MiB 이상 파일을 포함하지 않았다. 패턴 검사는 완전한 비밀정보 부재 보증은 아니다.
- manifest의5개 snapshot byte/SHA가 기존 운영 SHA와 일치한다. Frozen V1·시장 export·config·runtime source 변경 없음. 신규52개 unsupported·공개V2 release0을 유지했다. 데이터 다운로드·수집·승인0.

## 안전한 순서와 중단·복구

1. 사용자 승인, 목표 최종 commit, rollback artifact/실행 권한과 설정 접근, 계측 방식, 담당 시간대·복구 담당자를 확보한다. 누락되면 NO-GO 유지.
2. 기존 웹을 유지하고 **API만** 승인 commit으로 배포한다. 변경 범위를 자동 배포나 branch 전환으로 넓히지 않는다. deployment ID/SHA와 source를 확인하고 cold readiness와 warm 성능을 분리한다.
3. 실제 메모리·CPU·pids·OOM 증거와 기존웹+신규API smoke를 확인한 뒤, Phase5의 최대41회 예산·동시1→2→4를 별도 승인 범위 내에서 수행한다. 이번864건을 공개 환경에서 반복하지 않는다. 플랫폼 health와 자연 트래픽도 queue를 소비하므로 시험 중 추가 polling을 넣지 않는다.
4. API 검증 후에만 **웹 배포를 별도 승인**한다. 새 catalog 로드·28개 full·52개 차단·모바일·시장 화면을 확인한다. API만 올린 상태로 종료하는 것도 가능하다.
5. normal workload 첫 unknown500/503/504, 수치/SHA mismatch, health 실패, OOM/event 증가·재시작에서 즉시 추가 요청을 중단한다. RSS400MiB 이상, actual cgroup80% 이상, pids90% 이상도 중단한다. 측정 불가는 통과가 아니다. 503/504를200과 합산하지 않는다.
6. 신규웹도 올라갔다면 **웹→API rollback**. 기존웹이 그대로면 API만 복구한다. 목표97e783, health200/as_of2026-10-23, universe28/scenario3, before23.38%/after16.94%, compare전체와 시장 export를 재검증한다. 구 API catalog404는 예상이므로 구 웹과 함께 확인한다. 복구 자체가 승인 범위에 들어 있어야 하며 이번에는 실행하지 않았다.

기존 [Phase5 실행 계획](PORTFOLIO_PHASE5_EXECUTION_PLAN_KO.md)·[롤백 절차](PORTFOLIO_PHASE5_ROLLBACK_KO.md)를 이 호환성 실측과 함께 사용한다. 별도 승인이 필요한 항목은 **push, runtime 계측 구현 후 배포, API 배포, 제한된 공개 검증, 웹 배포, 실패 시 실제 rollback/재시작·설정 변경**이다. main/PR 병합·결제·유료 서비스·신규 종목 승인은 포함하지 않는다.

공식 확인일2026-11-04: [Rollback/retention/설정](https://render.com/docs/rollbacks), [Free 제한](https://render.com/docs/free), [Shell 지원 범위](https://render.com/docs/ssh), [deploy 목록 API](https://api-docs.render.com/reference/list-deploys). 실제 artifact 권한/retention은 이 문서들만으로 확정하지 않았다.
