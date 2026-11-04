# M/PRI Phase 4 — Portfolio API 서버 안정화

작업일: 2026-11-04 (Asia/Seoul). 기준 commit `ba0889326c541b0abc09a53fc4b2027fcad3f0f6`, 기준 브랜치 `feature/portfolio-data-stability-phase3`, 작업 브랜치 `feature/portfolio-server-stability-phase4`.

## 결과와 범위

Phase 3 보고서·진단을 읽고, 기준 commit의 독립 소스 복사본과 수정본에 같은 HTTP workload를 실행했다. AS512 기본 조건의 HTTP 500은 **269/1,728 (15.57%) → 0/1,728**이었다. 수정본은 AS512 기본·AnyIO4·주소 무제한의 총 **5,184건 모두 200**, 최대 RSS **136.24MiB**, OS 스레드 **2개**였다. 이 수치는 기존 실제 28개 기반의 로컬 시험이며 Render 성능 보증이 아니다.

기존 28개, 데이터 SHA, Frozen V1, 시장 운영 파이프라인, Render 설정은 변경하지 않았다. 신규 52개는 unsupported, 공개 V2 승인 release는 여전히 0개다. 실제 Render 배포·운영 부하·외부 공급처 문의·계정 가입·구매·main/PR 병합·GitHub push는 하지 않았다.

## 확인된 원인과 수정

기준 서버의 FastAPI 동기 dependency/endpoint는 Starlette `run_in_threadpool` → AnyIO worker 생성 → Python thread start 경로를 사용했다. 동기 응답 검증도 스레드풀을 이용할 수 있다. 기본 AnyIO limiter는 40개다. 동시 요청에 따라 새 worker가 생성될 때 `RuntimeError: can't start new thread`가 실제 500으로 전달됐다. 이번 기준 재현에서도 같은 traceback이 보존됐다.

AS512에서는 RSS 140MiB 미만인데도 VmPeak 약 510MiB에 도달했다. glibc arena와 스레드 stack/예약 주소가 RSS와 별도로 주소공간을 차지한다. AnyIO 토큰만 4로 줄여도 실패했지만 `MALLOC_ARENA_MAX=2` 대조군은 통과했고 주소 무제한에서도 실패하지 않았다. 이는 **해당 로컬 재현에서 가상주소 제한과 스레드 생성의 충돌**을 뒷받침한다. 과거 단일 사건의 syscall errno는 복구할 수 없으며, 실제 Render OOM이나 pids 제한을 원인으로 확인한 것은 아니다.

수정한 실행 구조:

- HTTP handler를 async wrapper로 등록해 AnyIO implicit pool을 우회한다. 동기 금융 core는 offline/demo 호출을 위해 유지한다. 스냅샷 무결성 검사와 계산을 같은 실행 작업으로 처리한다.
- startup에서 계산 thread **1개**를 미리 만든다. `ThreadPoolExecutor(max_workers=1)`과 semaphore로 전체 요청을 **4개(실행 1 + 대기 3)**까지 제한한다. worker 생성 실패 시 사용자 계산을 먼저 enqueue하지 않는다.
- 대기+계산의 deadline은 **25초**다(프런트엔드 30초보다 짧음). 초과·client task 취소 뒤에도 실제 계산이 끝날 때까지 slot을 보유한다. 대기 작업은 abandoned 표시 후 실제 dequeue 시 생략한다. Future를 즉시 cancel해 내부 queue에 취소 항목이 무한 축적되는 패턴도 방지했다.
- Python 계산 thread를 강제 종료할 수 없으므로 실행 중 계산은 계속될 수 있다. 대체 worker를 만들지 않는다. 계산이 영구 정지하면 용량·health가 회복되지 않을 수 있고 process 재시작이 필요하다. shutdown도 실행 중 계산의 안전한 강제 종료를 보장하지 않는다.
- 동일한 current/proposed compare만 결과를 한 번 계산해 재사용한다(V1/V2). 서로 다른 요청 간 결과 cache는 추가하지 않았다. 분석 수식·가중치·베타·위험기여·Stress·What-if 계산 규칙은 동일하다.
- 성공 응답 schema와 **전체 OpenAPI가 기준과 정확히 동일**하다. canonical SHA-256은 `5be81f806db00e56d04192da1cc8cb1d5eac1dcceb62a0a31391da2a5f68e4aa`다.

| 상황 | HTTP / 처리 |
|---|---|
| 정상 분석 | 200, 기존 응답 유지 |
| 잘못된 입력 | 422, 기존 validation 유지 |
| 공개 V2 release 미승인 | 409, 기존 권리 gate 유지 |
| 스냅샷/데이터 불능 | 기존 503 유지 |
| 용량 초과 | 503 `portfolio_capacity_exhausted`, Retry-After: 1 |
| MemoryError / ENOMEM / EAGAIN / thread 생성 실패 | 503 `portfolio_resource_exhausted` |
| executor 초기화 실패 | 503 `portfolio_executor_unavailable`, health도 503 |
| 요청 deadline | 504 `portfolio_deadline_exceeded` |
| 알 수 없는 결함 | 실제 500 유지, traceback 기록 |

health도 동일한 bounded 경로와 SHA 검사를 사용한다. 계산 backlog가 가득 차면 health는 503을 반환한다. 충분한 메모리가 남아 있어도 일시적으로 unready일 수 있으며 실제 Render health 정책과 함께 관찰해야 한다. OS cgroup OOM kill/SIGKILL에는 Python 오류 응답을 보장할 수 없다.

## 동일 workload 전후 비교

각 조건 새 프로세스 3회, 동시 요청 **1/2/4**, V1/V2 analyze/compare와 최대 10보유 analyze/compare 각각 24요청: 조건당 1,728건. cold/health/diagnostic 요청은 이 분모에 포함하지 않았다. BLAS/OMP thread 1, uvicorn worker 1이다. 기준 6,912건 + 수정본 5,184건. 로컬 V2 수치 계산은 **기존 실제 28개 연구 replay bundle**과 루프백 전용 route를 사용했다. 공개 V2 analyze/compare는 전후 모두 미승인 409이며 신규 종목이나 임의 가격을 사용하지 않았다.

| 조건 | 기준 500 / 요청 | 수정 후 500 / 요청 | peak RSS MiB 전→후 | VmPeak MiB 전→후 | 최대 OS thread 전→후 |
|---|---:|---:|---:|---:|---:|
| AS512 기본 | 269/1,728 | 0/1,728 | 139.58→136.24 | 509.96→360.86 | 5→2 |
| AS512 AnyIO4 | 272/1,728 | 0/1,728 | 139.60→136.20 | 509.95→360.86 | 5→2 |
| 주소 무제한 기본 | 0/1,728 | 0/1,728 | 138.91→136.19 | 643.63→360.86 | 5→2 |
| AS512 arena2 (기준 대조군) | 0/1,728 | 미실행 | 138.81 | 390.42 | 5 |

AS512 기본의 각 workload/trial **p95 범위**(전체 표본을 합친 p95가 아님):

| 동시 요청 | 기준 p95 ms | 수정 후 p95 ms | 최대 응답 ms 전→후 |
|---|---:|---:|---:|
| 1 | 8.425–26.561 | 6.934–17.601 | 30.805→18.104 |
| 2 | 22.360–69.829 | 17.292–51.750 | 71.062→52.071 |
| 4 | 62.656–198.766 | 33.132–72.949 | 223.669→73.323 |

기준 latency에는 실패 응답도 포함된다. 공용 로컬 개발 환경의 관측치이며 CPU 차이/스케줄링/Render Free 제약에 대한 SLA로 해석하지 않는다. 원시 기록: [수정 전](PORTFOLIO_PHASE4_BEFORE.json), [수정 후](PORTFOLIO_PHASE4_AFTER.json), [요약](PORTFOLIO_PHASE4_SUMMARY.json).

## 오류·복구 시험과 회귀

[실제 HTTP fault 기록](PORTFOLIO_PHASE4_FAULTS.json)은 production에 연결되지 않는 루프백 전용 fixture다. 두 명시적 local/fault 환경 flag가 필요하며 timeout만 시험용 0.5초로 줄였다. 운영값은 25초다.

- RLIMIT_AS512 아래에서 실제 mmap 주소 예약으로 여유를 줄여 **실제 ENOMEM**을 발생시켰다. 응답용 여유를 복구한 뒤 503을 확인했고 health는 200으로 복구했다. 물리 메모리를 채우는 시험은 아니다.
- 1초 작업에 8개 동시 요청: **503 4개 + 504 4개**. timed-out 계산이 아직 실행 중일 때 health503, 실제 완료 후 health200 및 정상 analyze200. 미처리 queue가 무한 증가하지 않는 단위 시험 포함.
- 알 수 없는 결함은 500, invalid422, 공개 V2 unsupported409 확인. AnyIO `to_thread.run_sync`를 금지한 시험에서도 모든 Portfolio HTTP 경로가 정상 동작했다. startup thread 실패는 health503으로 확인했다.
- **Python 전체 152 passed**, 기존 Starlette/httpx deprecation warning 1개. 기존 140개 + 실행 구조 시험 12개. Hidden Risk·베타·위험기여·Stress·What-if·V1/V2·권리·snapshot 검증 포함.
- frontend ESLint, `tsc --noEmit`, charts, integration, Render config, production build 모두 통과.
- Chromium production E2E 통과: 390/1280px, KR/EN 회사명, NFKC ticker, 키보드, unsupported 사유/선택 차단, 결과 무효화.
- 커밋 대상 16개 파일의 비밀정보·인증키·토큰·연락처·로컬 사용자 경로 패턴과 크기를 점검했다. 원시 traceback의 로컬 경로는 치환했고 `.env`/연구 데이터/1MiB 이상 파일은 포함하지 않았다. 패턴 검사는 비밀정보 부재의 수학적 보증은 아니다.
- 기준 대비 `data/**`, `tests/fixtures/**`, `render.yaml` diff 없음. 시장/Frozen V1 코드는 수정하지 않았다. SHA 및 금융 golden fixture를 교체하지 않았다.

## 512MiB 검증 한계와 후속 절차

이번 시스템의 `/sys/fs/cgroup`는 read-only이고 `memory.max=max`였다. Docker는 WSL 연동이 없는 Windows shim이라 local cgroup 컨테이너를 실행할 수 없었다. 따라서 **실제 512MiB 물리/cgroup 검증은 미완료**다. AS512 성공과 RSS 136MiB 관측만으로 해결 완료/Render 검증 완료라고 표시하지 않는다.

AS는 프로세스 virtual address space 한도, cgroup memory는 실제 charge된 페이지/cache 등을 제한한다. pids.max/RLIMIT_NPROC는 메모리와 별도인 task/thread 한도이며 실제 errno/메트릭을 함께 관찰해야 한다. AS 시험만으로 이 한도들을 재현하지 못한다. 다음 단계는 [승인 후 Render 검증 절차](PORTFOLIO_PHASE4_RENDER_RUNBOOK_KO.md)를 사용한다. 이번에는 Render 설정이나 서비스를 변경하지 않았다.

재현(로컬 전용):

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python -m pytest -q
.venv/bin/python scripts/benchmark_portfolio_phase4.py --output /tmp/phase4.json --trials 3 --requests 24
.venv/bin/python scripts/check_portfolio_phase4_faults.py /tmp/phase4-faults.json
```

기준 비교는 기준 commit을 `git archive`로 별도 임시 디렉터리에 추출하고 기존 Phase 3 benchmark를 실행했다. 새 harness의 Phase 3 공통 함수 수정은 probe factory 선택을 허용하는 한 줄뿐이며 기존 default는 유지한다. probe/fault route는 production app에서 import하지 않는다. 연구 bundle은 기존 gitignore 아래에만 생성하며 Git에 포함하지 않는다.

기술 근거: [Starlette thread pool](https://www.starlette.dev/threadpool/), [Python concurrent.futures](https://docs.python.org/3/library/concurrent.futures.html), [Python asyncio timeout](https://docs.python.org/3/library/asyncio-task.html#asyncio.wait_for), [Linux cgroup v2 memory controller](https://docs.kernel.org/admin-guide/cgroup-v2.html#memory), [Render compute plans](https://render.com/docs/compute-plans). Phase 3 조사와 이번 실제 설치된 Python/FastAPI 코드·계측을 함께 근거로 사용했다.
