# M/PRI Phase 3 — 금융 데이터 공급처와 서버 안정성 검증

작업일 **2026-11-04 (Asia/Seoul)**.
기준 `feature/portfolio-universe-phase2`, commit `4be3b4ddcb955b0bdbaa2dbbfb14120378a36d4a`.
작업 브랜치 `feature/portfolio-data-stability-phase3`. 로컬 커밋만 수행하며 push는 별도 승인 대상이다.

## 결론

1. 신규 주가·기업행위·필수 팩터·공개 결과/저장/배포를 모두 포괄하는 M/PRI 권리는 취득하지 않았다. **기존 28개 full, 신규 52개 unsupported, 새 승인 0개**를 그대로 유지한다.
2. Phase 2 동일 스크립트를 5회 반복해 1회 HTTP 500을 재현했다. traceback은 FastAPI dependency → Starlette thread pool → AnyIO worker → Python `threading.start()`의 **`RuntimeError: can't start new thread`**였다. 금융 계산식 오류나 데이터 SHA 오류가 아니다.
3. 추가 실험에서 512MiB 가상주소 상한과 스레드/allocator 예약 공간의 충돌을 뒷받침하는 증거를 확보했다. 실제 RSS가 140MiB 미만이어도 오류가 발생했다. **가상주소 제한 실패를 Render 512MB 물리/cgroup OOM으로 판정하면 안 된다.**
4. allocator 설정을 줄인 로컬 대조군은 통과했지만, 스레드 토큰을 4개로 줄인 대조군에서도 실패했다. 운영 환경 수정이나 완전 해결로 표시하지 않는다. 원래 과거 단일 사건의 syscall errno는 보존되지 않았고 실제 Render/cgroup 검증은 남아 있다.
5. 기능 회귀 **140개 통과**, 실제 기존 데이터 기반 HTTP 부하 계측 완료. **운영 코드·데이터·설정은 변경하지 않았다.**

## 공급처 조사와 권장 전략

세부 [가격·기능·권리 비교표](PORTFOLIO_PHASE3_PROVIDER_REVIEW_KO.md), [CSV](PORTFOLIO_PHASE3_PROVIDERS.csv), [구조화 기록](PORTFOLIO_PHASE3_PROVIDERS.json)에 9개 원천의 공식 URL·확인일·정가·호출량·저장/파생/공개/원본 재배포 권리를 구분했다.
영문 [문의 초안](PORTFOLIO_PHASE3_VENDOR_INQUIRY_EN.md)은 공통 본문과 업체별 질문을 포함하며 **발송하지 않았다**.

| 검토 후보 | 확인된 비용의 의미 | 판단 |
|---|---|---|
| Twelve Data | 공식 tier 문서에서 Venture $149/월·610 credits/분부터. 선택 variant $499와 구분 | 먼저 EOD 파생 웹/JSON 결과·장기 archive·VIX·cloud hosting 범위를 문의할 후보. 전체 서비스 확정 견적 아님 |
| Alpha Vantage | 개인 premium $49.99/월·75회/분부터. 무료 25회/일 | 별도 상업 권리 견적 필요. 개인 premium으로 공개 제공 승인 불가 |
| EODHD | 개인 $19.99/월과 상업 GBP 가격을 분리. Internal £399, server download +£200, Enterprise £2,499 | Internal만으로 공개 사이트를 허가받은 것으로 계산하지 않음. 공개 파생 custom 견적·indicative 원천 품질 확인 필요 |
| Massive | 개인 Starter $29와 Stocks Business $2,499/월 구분 | 별도 VIX/index 범위 확인. 기본 bars는 배당 조정이 아니므로 총수익형 조정 검증 필요 |
| Fed H.15 직접 | 조건에 맞는 Board 자체 자료 비용 $0 | 금리 원천의 유력한 후보이나 기술 검증·신규 활성화는 하지 않음. 주가·VIX 문제는 남음 |
| Yahoo/yfinance·Stooq·FRED·Cboe | 무료 접근·series 조건·웹 약관을 각각 구분 | 새 공개 분석 서비스의 일괄 허가로 해석하지 않음 |

공식 근거는 [Twelve Data pricing.md](https://twelvedata.com/pricing.md)·[약관](https://twelvedata.com/terms), [Alpha Vantage premium](https://www.alphavantage.co/premium/)·[약관](https://www.alphavantage.co/terms_of_service/), [EODHD 상업 가격](https://eodhd.com/commercial-pricing)·[약관](https://eodhd.com/financial-apis/terms-conditions), [Massive business](https://massive.com/business)·[약관](https://massive.com/legal/market-data-terms-of-service), [Fed 정책](https://www.federalreserve.gov/disclaimer.htm)이다. 나머지 원천과 기능 문서 URL은 비교표에 기록했다.

**비용 제안은 구매가 아니다.** 전체 합법 서비스 비용은 주가·SPY/VIX·보관·결과 JSON API·artifact 전송·거래소 조건의 견적을 받아야 산정할 수 있다. 최저 tier 하나로 VIX/redistribution까지 포함됐다고 추정하지 않았다. 세금·환율·추가 수수료는 미확정이다.

연구 파일은 기존 gitignored `data/portfolio_expansion/{raw,research}/`와 루프백 진단 서버로 격리한다. 공개 서비스는 기존 approved registry/manifest 경로만 사용하고 원본·수익률 행렬의 GitHub 배포를 기본 전제로 삼지 않는다. 장기 보관·private cloud artifact hosting·공개 파생 결과를 각기 서면 확인한 다음 현재 보수적인 gate의 의미를 재검토할 수 있다. 이번에 gate를 완화하거나 비공개 사용을 무조건 허용한 것은 아니다.

## HTTP 500 재현과 원인 조사

### 원래 Phase 2 경로

변경하지 않은 `scripts/benchmark_portfolio_phase2.py`를 별도 프로세스로 5회 실행했다.
4회 통과, 1회 실패했다. 실패 시 서버 peak RSS는 **138.746MiB**였으며 traceback의 마지막 부분은 다음과 같다.

```text
fastapi.dependencies.utils.solve_dependencies
starlette.concurrency.run_in_threadpool
anyio._backends._asyncio.run_sync_in_worker_thread
worker.start()
threading._start_joinable_thread(...)
RuntimeError: can't start new thread
```

전체 실패 기록과 반복 결과는 `PORTFOLIO_PHASE3_INITIAL_REPEATS.json`에 보존했다.
원본 스크립트 자체는 수정하지 않았다.

`diagnose_portfolio_phase3_legacy.py`로 원래 `http_benchmark()`의 프로세스·요청을 계측했다. 기본 allocator/AS512를 추가 5회, arena2/AS512를 3회, 주소 무제한을 3회 실행했고 이 계측 반복에서는 모두 통과했다. rare failure가 매번 발생하는 것은 아니며 계측이 scheduling에 영향을 줄 수 있다. 결과는 `PORTFOLIO_PHASE3_LEGACY_DIAGNOSTICS.json`이다.

### V1/V2 HTTP 대조 행렬

`portfolio_phase3_probe.py`는 **실제 production 서버에서 import하지 않는** 별도 로컬 진단 app factory다.
명시적 `MPRI_PHASE3_LOCAL_PROBE=1`이 없으면 실행을 거부한다. harness는 127.0.0.1에만 bind한다.
V2 금융 계산은 기존 실제 V1 28개 연구 bundle만 `/_phase3/research/*`에서 호출한다.
실제 `/api/portfolio/v2/*`는 그대로이며 모든 trial 종료 시 `409`가 유지됐음을 확인했다.
연구 route를 production 코드에 추가하거나 공개 registry에 연구 자료를 승인하지 않았다.

각 조건은 새 서버 3회, 동시1/2/4, V1/V2 analyze/compare와 최대10보유 analyze/compare를 각각 24요청 실행했다.
**조건당 1,728요청, 합계 6,912 workload 요청**이다. cold·health·진단 조회는 이 숫자에 포함하지 않는다.

| 조건 | trial | non-200 / workload | thread failure trial | peak RSS | peak 가상주소 VmPeak |
|---|---:|---:|---:|---:|---:|
| AS512, 기본 allocator, AnyIO40 | 3 | 0 / 1,728 | 0 | 138.742MiB | 507.629MiB |
| AS512, `MALLOC_ARENA_MAX=2`, AnyIO40 | 3 | 0 / 1,728 | 0 | 138.832MiB | 390.336MiB |
| 주소 무제한, 기본 allocator, AnyIO40 | 3 | 0 / 1,728 | 0 | 138.961MiB | 643.637MiB |
| AS512, 기본 allocator, AnyIO4 | 3 | **274 / 1,728** | **2** | 139.531MiB | 509.953MiB |

실패는 마지막 조건의 trial2 136회·trial3 138회 HTTP500이다. V1과 V2 연구 요청 모두 영향을 받았다. trial 후 `/health`는 모두 200이었지만 이 사실을 workload 전체 정상으로 해석하지 않는다.
성공 응답은 기존 예제 전체 금융 필드/golden 또는 최대10보유 계약을 확인했으며 불일치 `harness_error`는 없었다.

첫 실패 관측에서 `VmSize=519852KiB`(507.668MiB), `VmRSS=140772KiB`(137.473MiB), OS threads 4였다.
AS 상한까지 약 4.33MiB만 남았고, 관측된 stack rlimit은 8MiB, process rlimit은 31,345, 호스트 pids.max는 `max`였다.
이후 VmPeak는 509.953MiB까지 올라갔다. 주소 무제한 조건은 비슷한 RSS에서도 가상주소가 643MiB를 넘었다.

### 통제된 주소 예약 실험

`probe_thread_address_space.py`는 금융 자료 없이 stdlib만 사용한다.
512MiB AS 제한 안에서 `mmap(PROT_NONE)`으로 주소 공간을 예약하여 headroom을 4MiB로 줄였더니 RSS는 **12,328KiB로 동일**했지만 `can't start new thread`가 발생했다.
예약 해제 후 같은 프로세스·같은 AS 제한에서 thread가 정상 생성됐다. 결과는 `PORTFOLIO_PHASE3_THREAD_PROBE.json`이다.

### 판단의 범위

- **확인됨:** 이번에 재현한 500의 직접 오류 지점은 AnyIO/Python의 OS worker thread 생성이다. 실제 금융 데이터 처리 이전 dependency thread 시작에서도 발생했다.
- **강하게 지지됨:** 인위적인 AS 상한에서 allocator arena·스레드 stack 등의 가상주소 예약 여유가 부족해지는 조건이 원인이다. 주소 무제한과 arena2 대조, 실제 에러 시점 VmSize, 통제 mmap 실험이 일관된다.
- **미확정:** 보존되지 않은 과거 Phase 2 단일 사건의 kernel errno, 실패한 mmap/clone syscall별 정확한 요청 크기·allocator 내부 기여 비율은 syscall trace로 확인하지 못했다. `---p` 대형 익명 영역을 모두 특정 allocator arena라고 단정하지 않는다.
- **미해결/승인 보류:** 실제 Render 512MB cgroup·0.1CPU, 장시간·새 실제 60~100가격 열, 동시 폭증·cold race 조건의 운영 안정성. 이번 결과를 Render 장애 해결 완료로 표시하지 않는다.

AnyIO4만으로 해결되지 않았다. `MALLOC_ARENA_MAX=2`는 **로컬 대조 변수**이며 `render.yaml`이나 운영 환경에 적용하지 않았다. 다음 실제 cgroup 검증에서 allocator/명시적 concurrency·backpressure를 별도로 검증할 후보일 뿐이다. 이번에 금융 엔진이나 오류 응답 정책을 변경하지 않았다.

## 메모리 제한 방식과 Render 차이

[Linux RLIMIT_AS](https://man7.org/linux/man-pages/man2/getrlimit.2.html)는 프로세스의 가상주소를 제한해 brk/mmap/mremap 및 stack 확장에 영향을 준다.
[스레드 생성](https://man7.org/linux/man-pages/man3/pthread_create.3.html)은 stack/자원 여유에 의존하며, [glibc allocator](https://sourceware.org/glibc/manual/latest/html_node/Memory-Allocation-Tunables.html)의 arena 수는 예약 주소량에 영향을 줄 수 있다.
[Starlette thread pool](https://starlette.dev/threadpool/)과 실제 진단값에서 기본 AnyIO limiter는 40 tokens였다. 이는 분석 worker 프로세스 40개를 뜻하지 않는다.

[cgroup v2 memory controller](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html)는 cgroup에 계상되는 anonymous/file/kernel 메모리 등을 제한한다. RSS 하나와도 동일하지 않다. `/proc` 가상주소의 미접근 예약 전체를 물리 사용으로 계산하는 AS512 실험과 구분해야 한다.
호스트 cgroup memory.max와 pids.max는 `max`였다. cgroup을 변경하지 않았고 Render 내부 controller/서비스 이벤트에 접근하지 않았다.
[Render 공식 compute 문서](https://render.com/docs/compute-plans)는 Free 0.1CPU/512MB를 명시하지만 정확한 운영 cgroup byte 값·overhead를 이번 로컬 호스트에서 확인한 것은 아니다.

진단 행렬은 uvicorn 시작 뒤 app factory에서 AS 제한을 설정한다. 원래 Phase 2 경로는 exec 이전 preexec에서 설정한다. 초기화·예약 layout 차이가 생길 수 있으므로 두 실험을 같은 재현율의 표본으로 합치지 않았다.

## 정상 조건의 응답시간과 메모리

주소 무제한·기본 allocator의 3개 trial에서 각각 측정한 **p95 범위**다. trial별 percentile을 합친 전체 percentile이 아니다.
각 행은 24요청 × 3trial = 72요청이며 V1/V2 cache가 같은 프로세스에 함께 존재한다.
V2는 private loopback replay이고 공개 승인 V2 서비스의 측정이 아니다.

| 동시 요청 | V1 analyze p95 | V1 compare p95 | V2 연구 analyze p95 | V2 연구 compare p95 |
|---:|---:|---:|---:|---:|
| 1 | 8.659–10.747ms | 14.768–16.781ms | 6.907–7.168ms | 12.039–13.028ms |
| 2 | 22.741–27.978ms | 45.059–47.094ms | 20.281–21.252ms | 36.840–40.323ms |
| 4 | 65.078–68.829ms | 112.529–125.773ms | 51.765–54.419ms | 101.103–105.401ms |

동시4·10보유 p95: V1 analyze 66.277–68.797ms / compare 126.219–131.810ms, V2 연구 analyze 53.133–63.224ms / compare 106.203–115.084ms.
첫 HTTP analyze: V1 95.345–108.730ms, V2 연구 8.854–10.505ms. V2는 앞선 V1 호출로 import가 따뜻해진 프로세스에서 bundle을 처음 읽는 경로다. 완전 독립 cold start 비교로 사용하지 않는다.

workload 직후 RSS 최댓값은 동시1에서 V1 analyze 135.164MiB / compare 135.297MiB, V2 analyze 135.574MiB / compare 135.590MiB였다.
동시4에서는 각각 138.273 / 138.473 / 138.930 / 138.930MiB였다. 이는 누적 cache를 포함한 프로세스 RSS이고 요청 하나의 추가 메모리가 아니다.
전 구간 peak RSS는 138.961MiB였다. 표의 latency는 성공 조건만 사용했으며 실패 응답의 짧은 지연을 정상 성능에 섞지 않았다.

원자료는 `PORTFOLIO_PHASE3_BENCHMARKS.json`, 요약은 `PORTFOLIO_PHASE3_SUMMARY.json`이다.
샘플링 간격은 약5ms이고 kernel VmHWM/VmPeak도 기록했다. 로컬 CPU·공유 호스트 부하·네트워크와 Render는 다르다.
Next 서버·실제 Render cold start·새 80가격 열·사용자 인증·외부 수집·지속 장기 soak는 포함하지 않았다.

## 테스트·보존·재현

- 전체 Python **140개 통과**, 기존 Starlette/httpx deprecation 경고 1개.
- 기존 28개 단독/예제·What-if HTTP golden과 독립 V2 연구 수식 회귀 유지. 기존 5개 파일 SHA256 일치.
- production app에 `/_phase3/diagnostics`, `/_phase3/research/analyze`, `/compare`가 없고 404임을 테스트했다. local probe는 명시적 context 없이는 실행 거부한다.
- 보호 경로 `data/portfolio/`, `data/portfolio_v2/`, `config/`, `src/portfolio/`, 시장/Frozen V1/운영 데이터·모델·엔진, `render.yaml`, 기존 golden fixture의 git diff가 없음을 확인했다.
- 신규 52개 unsupported, 선택 불가, 공개 V2 registry 비어 있음 확인. production 기능/프런트엔드 변경은 없으며 이 작업에서는 Python 회귀와 실제 HTTP 계측을 수행했다.

프로젝트 루트에서 재현:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/diagnose_portfolio_phase3_legacy.py --output /tmp/phase3-legacy.json --default-trials 5
.venv/bin/python scripts/benchmark_portfolio_phase3.py --output /tmp/phase3-matrix.json --trials 3 --requests 24
.venv/bin/python scripts/probe_thread_address_space.py
.venv/bin/python scripts/summarize_portfolio_phase3.py
```

벤치마크는 로컬 loopback socket과 `/proc`를 사용한다. 마지막 요약 명령은 저장된 `reports/design/PORTFOLIO_PHASE3_BENCHMARKS.json`으로 보고서 요약을 다시 만든다.
새 연구 bundle을 만들 때 기존 ID를 덮어쓰지 않는다. 금융 원본/배열은 gitignored 연구 경로에만 남고 커밋에는 성능·SHA·상태·오류 진단 기록만 포함한다.

## 남은 선행 조건

- 권리: 영문 초안의 storage, non-reconstructible derived output, public website/JSON, private hosting, optional raw artifact redistribution, VIX, 해지 후 보관을 각기 서면 확인한다. 그 전에는 신규 종목을 열지 않는다.
- 품질: 실제 허가된 가격·배당/분할·달력·revision을 수집해 757개 실가격과 필수 팩터를 검증한다. API 기술 접근이나 유료 결제만으로 승인하지 않는다.
- 안정성: 실제 제한된 cgroup/Render에 대한 별도 허용 범위에서 memory.current/peak/events, OOM/exit, concurrency, cold race, 장기 부하를 다시 확인한다. 이번에 제한을 운영 환경에 적용하거나 재배포하지 않았다.
- 구매·가입·문의 발송·새 유료 서비스·main/PR 병합·Render 재배포·GitHub push는 모두 0건이다.
