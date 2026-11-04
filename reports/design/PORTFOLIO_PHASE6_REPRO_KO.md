# Phase 6 — 로컬 재현 안내

실제 Render 요청/배포 없이 수행한다. 기존 버전은97e78366a026e9221740526087ef8082a891fa28 archive, 신규는85f5f20dc51ad2b6b748e3991a36ea3192ae246a와 동등한 runtime이다. 새 스크립트는 source를 고치지 않고 실제 HTTP/production build를 비교한다.

1. 정상 commit을 `git archive`로 `/tmp/mpri-phase6-old`에 추출한다. 현재 checkout/브랜치나 운영 소스를 reset하지 않는다. 아래 `MPRI_TASK_ROOT`는 현재 저장소 절대 경로로 설정한다.
2. 현재 venv Python과 현재 설치된 frontend dependencies를 사용한다. 구 frontend의 node_modules는 자체 임시 디렉터리에 복사한다. 외부 symlink는 Turbopack root 제약으로 실패할 수 있다. 두 frontend 각각 `npm run build`, 신규는 TypeScript/lint/chart/integration/Render config도 실행한다. 이는 과거 cloud artifact 재현이 아니라 source compatibility 검증이다.
3. 기존 release root에서 다음과 같이 계약 baseline을 생성한다. JSON에는 기존 실제 데이터의 파생 결과가 있으므로 임시 파일로만 유지한다. Git에는 response hash/요약만 포함한다.

```bash
cd /tmp/mpri-phase6-old
"$MPRI_TASK_ROOT/.venv/bin/python" "$MPRI_TASK_ROOT/scripts/check_portfolio_phase6_contract.py" /tmp/phase6-old-contract.json
```

4. 별도 로컬 터미널들에서 기존/신규 웹을 각각3001/3000으로 실행한다. 두 build의 API upstream은 기본 loopback8000을 사용한다. API는 기존 root의 Python app을8000에서 worker1/BLAS1로 실행한다. `RENDER=true` 또는 공개 API override를 쓰지 않는다. 로컬 웹에서만 오류 응답을 주입한다.
5. 아래 명령을 기존웹+기존API와 신규웹+기존API에 실행한다. 버전 label과 flag는 실제 실행 소스에 맞게 지정한다. baseline은3단계 파일이다. Playwright/Chromium 경로는 로컬 설치에 맞춘다.

```bash
cd "$MPRI_TASK_ROOT"
PLAYWRIGHT_MODULE=/tmp/mpri-browser-check/node_modules/playwright \
CHROMIUM_EXECUTABLE="$MPRI_LOCAL_CHROMIUM" \
MPRI_WEB_URL=http://127.0.0.1:3001 \
MPRI_WEB_VERSION=old MPRI_API_VERSION=old \
MPRI_BASELINE_PATH=/tmp/phase6-old-contract.json \
MPRI_RESULT_PATH=/tmp/phase6-old-old.json \
node scripts/check_portfolio_phase6.cjs
```

신규웹+기존API는 URL3000, WEB_VERSION=new, API_VERSION=old, `MPRI_EXPECT_CATALOG_404=1`로 실행한다. API를 기존→신규로 바꿀 때는 **로컬 API process만 종료**하고 신규 root에서 같은8000/worker1/BLAS1로 시작한다. 웹은 유지한다. 기존웹+신규API와 신규웹+신규API는 API_VERSION=new, catalog flag 없이 실행한다. Chromium 공유 라이브러리가 별도 위치에 있다면 LD_LIBRARY_PATH를 로컬에서만 설정한다.

6. 새 계약 capture도 신규 root에서 실행해 기존 V1 paths/components·전체 before/after/compare·28개 단일분석 hash를 대조한다. 스키마의 새 V2 definitions는 별도로 구분하며 기존 schema를 교체하지 않는다.
7. 다음은 모두 로컬 프로세스다. fault deadline0.5초는 private fixture에만 적용되고 production25초는 그대로다.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/benchmark_portfolio_phase4.py --output /tmp/phase6-normal.json --trials 1 --requests 12
.venv/bin/python scripts/check_portfolio_phase6_faults.py /tmp/phase6-fault-matrix.json
.venv/bin/python scripts/check_portfolio_phase4_faults.py /tmp/phase6-overload.json
```

신규 runtime source/응답 golden/데이터를 테스트를 통과시키려고 바꾸지 않는다. 시험 후 로컬 server process를 종료한다. 기존 Render token·환경 값·일반 사용자 로그를 테스트 결과에 넣지 않는다. 실제 운영 artifact/rollback 가용성은 이 시험으로 확인할 수 없으며 [본 보고서](PORTFOLIO_PHASE6_KO.md)의 NO-GO 조건을 유지한다.
