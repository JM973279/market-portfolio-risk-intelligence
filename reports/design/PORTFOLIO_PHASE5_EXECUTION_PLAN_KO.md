# Phase 5 — Render 실환경 검증 실행 계획 (미실행)

2026-11-04 작성. Phase 4 runbook을 검토한 대체 실행안이다. 이번 작업에서 허용된 공개 요청은 기존 API health와 웹 root 각 1회뿐이며 이미 완료했다. 아래 배포·계측·분석·동시 요청은 **별도 승인 후** 수행한다.

## 진입 조건

- 대상은 M/PRI API `srv-dbkp73mgekts73eq0m20`, 웹 `srv-dbkp8fvf3r2c73fi28fg`만이다. 기존 다른 서비스는 제외한다.
- Phase 4 source `1db2dc2a1563c5c5096f32bc1640ac121e152a38`와 실제 배포할 최종 commit을 구분한다. Phase 5는 문서/증거만 추가한다. 계측 코드가 필요하면 별도 구현·검토·테스트한 commit에 다시 승인을 받는다.
- 우선 **API만 업데이트하고 기존 웹은 유지**하는 최소 변경 순서를 권장한다. 자동 배포 off·기존 branch·Free plan·1 instance·worker1·BLAS1 제약을 유지한다. Blueprint 적용이나 branch 변경은 별도 승인 없이는 하지 않는다.
- 현재 정상 SHA `97e78366a026e9221740526087ef8082a891fa28`의 API/웹 build artifact와 deploy ID를 배포 직전에 다시 확인한다. Free는 이전 2개 deploy만 rollback하므로 반복 시험 배포로 기준 artifact를 밀어내지 않는다. 조회 가능한 이력은 artifact 보존 자체의 증명이 아니다.
- CPU/RAM 공식 plan 사양은 Free 0.1 CPU/512 MB다. 실제 cgroup 한도 byte 수를 읽기 전에는 536870912 bytes라고 가정하지 않는다.

## 실제 cgroup 계측 방법과 차단 조건

Render Free는 SSH와 Dashboard Shell이 **지원되지 않는다**. 따라서 Phase 4 runbook의 proc/cgroup 명령을 Free shell에서 실행하는 방법은 사용할 수 없다. 이번에 SSH 접속이나 유료 전환을 시도하지 않았다.

현실적인 무료 경로는 **향후 승인된 앱 내부 계측을 일회성으로 추가하여 비공개 운영 로그로 수집**하는 것이다. 공개 diagnostics endpoint·연구 route·환경변수 dump는 추가하지 않는다. 현재 Phase 5에는 앱 계측을 구현/배포하지 않았다. 구현 범위와 배포 승인이 확보되기 전에는 실제 cgroup 검증을 시작하지 않는다.

향후 계측 설계:

1. startup에서 `/proc/self/cgroup`과 `/proc/self/mountinfo`를 사용해 실제 cgroup membership/mount를 찾고, 현재 group과 읽을 수 있는 상위 group의 유한 memory 한도 중 최소치를 확인한다. v2 `memory.max/current/peak/events`, `pids.max/current/events`, `cpu.max`, `cpu.stat`을 읽는다. v1이면 대응 `memory.limit_in_bytes`, `memory.usage_in_bytes`, `memory.max_usage_in_bytes`, `memory.failcnt`, CPU quota/period와 pids 파일을 사용한다. 읽기 실패/부재/무제한/부모 불가시성을 각각 기록한다.
2. `/proc/self/status`의 RSS/HWM/VmSize/VmPeak/Threads, `/proc/self/limits`의 address-space·process limit, monotonic timestamp, 승인 commit 식별자를 기록한다. 환경변수의 이름·값, 헤더/인증정보, 요청 holdings/사용자 정보는 로그에 넣지 않는다. 동적 cgroup 경로나 mount 원문도 남기지 않는다.
3. startup·각 단계 전후와 실행 중 1초 간격, 총 5분 이내로 제한한다. 샘플링 timer는 기존 event loop를 사용하고 새 계측 thread를 만들지 않는다. 파일 읽기는 작고 제한된 범위만 하며 event loop 지연도 평가한다. peak 파일이 없으면 1초 표본이 순간 peak를 놓칠 수 있음을 보고한다. 플랫폼 CPU/memory metrics와 timestamp를 대조하되 aggregate metrics를 cgroup hard-limit 증명으로 대체하지 않는다.
4. 기존 로그 조회 권한으로 필요한 sanitized metric만 가져온다. 일반 로그 전체를 Git에 보관하지 않는다. telemetry 종료·로그 보존·접근 권한을 사전 검토한다. 네트워크로 계측값을 외부 전송하지 않는다.
5. 실제 유한 한도와 OOM event delta를 못 읽으면 “Render Free 사양 확인, 실제 cgroup 제한 미확인”으로 기록한다. 계측 불가를 이유로 결제나 서비스 생성을 하지 않는다. Linux의 별도 512MiB cgroup 시험은 보완 증거이며 Render 검증을 대신하지 않는다.

`RLIMIT_AS=512MiB`는 virtual address 상한이며 실제 resident/cgroup charge 제한과 다르다. RSS가 작아도 stack/allocator 주소 예약으로 thread 생성이 실패할 수 있다. cgroup OOM kill은 Python이 503으로 처리할 수 없고, CPU throttling과 pids 제한도 별도 관측해야 한다. 현재 프로세스의 RSS만으로 서비스 전체 cgroup 메모리를 대표하지 않는다.

## 승인 후 공개 요청 예산

먼저 전용 비운영 환경이 **이미 존재하고 사용이 승인됐는지** 확인한다. 없다면 새 서비스를 만들지 않고, 기존 서비스에서 아래 제한을 실행할 시간대·책임자·중단/복구 승인을 별도로 받는다. 자동 재시도·무한 반복·장시간 soak는 금지한다.

| 단계 | 요청 수 | 동시성 / 확인 |
|---|---:|---|
| 준비 | API GET 4 | health, universe, scenarios, catalog 각 1회 |
| smoke | API POST 6 | before/after analyze, compare 각 1; invalid 1; 미승인 V2 analyze/compare 각 1 |
| 정상 소규모 A | API POST 8 | analyze 4 + compare 4, 동시1 |
| 정상 소규모 B | API POST 8 | analyze 4 + compare 4, 동시2 |
| 정상 소규모 C | API POST 8 | analyze 4 + compare 4, 동시4 |
| 단계 후 및 최종 | API GET 4 | A/B/C 뒤와 최종 health 각 1 |
| 웹 | GET 1 | root HTML 확인, 공개 Chromium 자동 탐색은 제외 |

기본 **39회**, cold readiness 재시도 최대 2회까지 포함해 **총 41회**다. metrics/control-plane 조회는 별도 읽기 전용이며 위 API workload와 분리한다. Phase 4의 조건별 1,728요청을 공개 환경에서 재실행하지 않는다. health 재시도는 cold start로 확인된 경우에만 15초 이상 간격, 요청 제한시간60초로 하며 200 이후 latency 측정에서 분리한다. 계산 client timeout은30초다. 각 정상 단계 사이 최소15초 관찰한다.

최대10개 보유의 **동일하지 않은 current/proposed** compare를 사용해 중복 계산 최적화만 시험하지 않도록 한다. 기존 실제 28개만 사용하고 정확한 요청 fixture와 해시를 승인 시 고정한다. 성공은200, invalid422, 공개 V2 미승인409가 예상값이다. 현 public V2 release는 0이므로 정상 V2 분석을 공개 서비스에 억지로 활성화하지 않는다.

## 500 / 503 / 504 검증과 중단

- 정상 공개 부하에서는 500/503/504를 인위적으로 만들지 않는다. 상태·detail code·Retry-After·시간·가능하면 플랫폼 request ID로 앱 오류와 proxy 오류를 구분한다. HTML503이나 cold-start 응답을 Portfolio resource503으로 분류하지 않는다.
- 자원 부족503, capacity503, deadline504, unknown defect500의 강제 검증은 로컬 Phase 4 fault/단위 시험으로 수행한다. 동일 code 경로가 컨테이너에서 동작하는지까지 필요하면, 별도 승인된 격리 환경과 일회성 시험 설계가 선행돼야 한다. production timeout을 줄이거나 fault route를 배포하지 않는다.
- normal workload 중 첫 unknown500, 503/504, 수치/SHA 불일치, OOM/event 증가, process 재시작, health 실패에서 즉시 다음 단계와 재시도를 중단한다. 명시적503/504도 “정상200 통과”로 합산하지 않는다. 모든 상태별 분모와 p50/p95/max를 분리한다. 소표본 p95는 참고값이다.
- 정상 steady RSS350MiB 이하/peak400MiB 미만을 임시 예산으로 둔다. cgroup current가 **실제 유한 한도의80% 이상**, RSS400MiB 이상 또는 pids90% 이상이면 중단한다. 해당 메트릭이 관측 불가하면 통과로 판정하지 않는다. baseline 이미 기준 초과면 부하를 시작하지 않는다.
- API deadline25초 이전 정상 완료, frontend30초 타임아웃 안에서 UI가 오류를 표시하는지 로컬 회귀와 대조한다. Free0.1CPU의 응답시간은 로컬 성능을 보증하지 않는다. health도 공유 queue를 사용하므로 동시4 구간에 추가 polling을 넣지 않는다. 플랫폼 자체 health와 자연 트래픽이 capacity를 소비할 가능성을 기록한다.
- 실패 시 [롤백 절차](PORTFOLIO_PHASE5_ROLLBACK_KO.md)를 따른다. 복구까지 승인받았는지 확인하며, 이번 Phase 5에서 rollback을 실행하는 것은 금지다.

공식 근거(확인일 2026-11-04): [Free 제한](https://render.com/docs/free), [compute plan](https://render.com/docs/compute-plans), [Free shell 미지원](https://render.com/docs/ssh), [rollback](https://render.com/docs/rollbacks). 실제 배포·cgroup 검증은 아직 실행하지 않았다.
