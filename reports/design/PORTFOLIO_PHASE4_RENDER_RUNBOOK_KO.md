# Phase 4 — 별도 승인 후 실제 Render 검증 절차

이 문서는 실행 준비용이다. **현재 배포/기존 서비스 변경/운영 부하/push를 승인하는 문서가 아니다.** 승인된 commit과 대상 환경이 정해진 뒤에만 진행한다. 새 유료 서비스·데이터 구매는 필요 없으며 자동으로 생성하지 않는다.

1. 승인 대상 commit, 기존 데이터 manifest SHA, rollback commit, 서비스 담당자를 기록한다. 운영을 대체하지 않는 승인된 시험 환경을 우선 사용하고, 시험 환경이 없으면 운영 요청을 보내기 전에 범위와 중단 기준을 별도로 승인받는다. 연구 probe/fault app을 Render에 배포하지 않는다.
2. 기존 `render.yaml`의 API worker 1, `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`을 실제 프로세스에서도 확인한다. auto deploy를 켜거나 브랜치/main을 변경하지 않는다. 새 dependency/allocator 설정은 이번 수정에 필요 없다.
3. 현재 프로세스와 cgroup 경로를 확인한다. `/proc/self/cgroup`, `/proc/self/limits`, `/proc/<api-pid>/status`, 해당 cgroup의 `memory.max`, `memory.current`, `memory.peak`(지원 시), `memory.events`, `pids.max`, `pids.current`를 전후 수집한다. 공유 cgroup에는 다른 프로세스 charge도 포함될 수 있다. VmPeak와 RSS, cgroup charge를 구분하고 실제 한도가 512MiB인지 숫자로 기록한다. `/proc/<api-pid>/task`와 BLAS thread 상태도 확인한다. 앱의 메인+계산 thread는 로컬에서 2개였으나 플랫폼 부가 process와 구분한다.
4. 공개 production API만 이용해 cold/warm health·catalog·V1 analyze/compare를 기존 fixture로 확인한다. 잘못된 입력422, 미승인 V2 409를 확인한다. V2 정상 수치 검증은 승인 release가 있을 때만 수행한다. 현재 신규 52개는 unsupported이므로 실제 공개 V2 성공을 예상하거나 연구 bundle을 등록하지 않는다. SHA mismatch/메모리 fault를 운영 데이터에 주입하지 않는다.
5. 승인된 시험 구간에서 최대10보유 입력으로 동시1→2→4, 각 24요청을 먼저 한 번씩 실행한다. 각 단계 사이 health·수치·에러·RSS/cgroup peak·thread·p50/p95/max를 확인하고 다음 단계로 진행한다. client timeout은 최소30초, 무제한 재시도는 금지한다. 서비스 idle/cold-start 지연은 warm latency와 분리한다.
6. 목표 예산은 기존 512MiB 계획의 정상 steady RSS 350MiB 이하, peak 400MiB 미만, cgroup OOM/event 증가 없음, unknown500 없음이다. 이는 추가 검증 기준이며 현재 Render에서 달성했다고 주장하지 않는다. 계산 deadline25초, 클라이언트30초 안의 처리/명시적504를 확인한다. 예상 가능한503/504도 정상200 성과에 섞지 말고 원인별 기록한다.
7. OOM/재시작/unknown500, 한도 접근 또는 수치/SHA 불일치 시 즉시 추가 요청을 중단하고 로그를 보존한다. health가 계산 backlog 때문에503일 수 있으므로 과도한 probe가 계산 queue를 채우지 않게 하고 플랫폼 health 정책을 관찰한다. 장기 정지 thread는 강제 취소가 안 되므로 담당자 승인 절차에 따라 이전 승인 commit으로 복구/재시작한다. 자동 확장·유료 업그레이드로 우회하지 않는다.
8. 시험 후 기준 SHA/health/수치·권리 gate를 다시 확인하고 최종 요청 수, 상태별 분모, 최고 RSS/cgroup charge, OS thread, latency, 이벤트 delta를 기록한다. 실제 cgroup 증거가 없으면 “512MiB 실제 환경 미확인”으로 유지한다.

로컬 보완 대안은 Linux Docker/cgroup 지원이 준비된 **별도 승인 환경**에서 `--memory=512m --memory-swap=512m`, worker1/BLAS1로 같은 production 앱을 실행하고 위 계측을 하는 것이다. 현재 시스템에 Docker 설치/WSL 활성화나 cgroup 변경은 하지 않았다. local RLIMIT_AS 실험은 이 시험을 대체하지 않는다.
