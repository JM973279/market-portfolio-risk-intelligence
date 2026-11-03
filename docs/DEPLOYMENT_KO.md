# MVP 배포 준비 및 승인 절차

작성: 2026-11-03. **아직 실제 배포하지 않았으며 배포 URL도 없다.**
저장소/로컬 설정에서 기존 호스팅 프로젝트·도메인·배포 인증을 확인할 수 없었다.
아래는 검토 가능한 Render 제안 구성이다. 계정의 실제 서비스/과금 상태를 조회한 결과는 아니다.

## 대상과 실행 구조

`render.yaml`: Singapore 같은 리전의 두 서비스. `feature/mvp-release-readiness`를 지정했고 자동 배포는 off다.
Blueprint를 처음 생성하면 즉시 서비스 생성·과금·최초 배포가 시작될 수 있으므로 **승인 전 실행 금지**.

| 서비스 | 실행 | 외부 접근 |
|---|---|---|
| `mpri-mvp-web` | Node 22.22.1, Next production, `0.0.0.0:$PORT` | Render HTTPS URL, 실제 이름/URL은 생성 시 확정 |
| `mpri-portfolio-api` | Python 3.14.4, FastAPI/uvicorn 1 worker, `0.0.0.0:10000` | private service, 공개 API URL 없음 |

브라우저 → 같은 HTTPS 출처 `/api/portfolio/*` → Next rewrite → private HTTP API.
모바일의 localhost, 공개 HTTP API 혼합 콘텐츠, 브라우저 CORS 문제가 생기지 않는 경로다.
API는 `data/portfolio/` 고정 스냅샷(2026-10-23)만 읽으며 시장 운영 추론을 실행하지 않는다.
한국/미국 페이지는 승인된 `frontend/public/data/operational-markets.json`을 읽는다.
새 원천 수집·미국 보류 정책 변경·자동 추론·데이터 갱신 스케줄러는 포함하지 않는다.

## 환경변수와 네트워크

- API `PYTHON_VERSION=3.14.4`, `PORTFOLIO_API_CORS_ORIGINS=""`(서버 프록시만 사용).
- 웹 `NODE_VERSION=22.22.1`, `PORTFOLIO_API_INTERNAL_HOSTPORT`: Blueprint가 API의 hostport를 연결한다.
- `PORTFOLIO_API_INTERNAL_URL`을 따로 지정하면 hostport보다 우선한다. 로컬 기본값은 `http://127.0.0.1:8000`.
- 내부 주소는 **next build 시 rewrite manifest에 반영**된다. 주소/환경 변경 후 반드시 rebuild한다.
- `NEXT_PUBLIC_PORTFOLIO_API_URL`은 미설정으로 유지한다. 직접 브라우저 연결을 선택할 경우에만 HTTPS 주소와 정확한 CORS origin을 별도로 검증한다.
- 금융 데이터 API 키, `.env`, 모델, 원본 연구 checkout, ML 훈련 패키지/GPU는 이 시연 서버 실행에 필요 없다.
- API `requirements.portfolio.txt`는 현재 검증 환경의 실행 의존성을 버전 고정했다. 기존 연구 requirements는 그대로다.
- API 시작 전 snapshot hash 검증 실패 시 시작하지 않는다. 요청 시에도 동일 검증, `/health` 및 분석은 503.
- 웹 health check `/api/portfolio/universe`는 실제 API와 snapshot 검증까지 통과해야 200이다.
- private network의 다른 서비스는 API에 접근할 수 있다. 승인 시 같은 workspace/region과 기존 서비스의 신뢰 범위를 확인한다.

## 비용 예상

[Render 공식 가격표](https://render.com/pricing) 및 [Blueprint 사양](https://render.com/docs/blueprint-spec) 확인 기준(2026-11-03):
각 0.5 CPU/512MB 서비스 약 USD 7/월 × 2 = **기본 약 USD 14/월**.
계정 workspace 요금, 빌드/트래픽 초과, 세금, 환율, 도메인은 별도다. 실제 결제 화면에서 확정해야 한다.
512MB는 초기 시연 제안이며 실제 동시접속·메모리 상한은 아직 부하 검증하지 않았다.
메모리 부족이면 임의 증설하지 말고 비용 증가를 보고한다. 무료 sleep 서비스는 시연용 기본안에서 제외했다.

## 로컬 재현 및 승인 후 순서

```bash
# root / terminal A
.venv/bin/uvicorn src.portfolio.server:app --host 127.0.0.1 --port 8000
# terminal B
cd frontend
npm ci
npm run build
npm run start -- --hostname 127.0.0.1 --port 3001
# root / terminal C
.venv/bin/python scripts/check_demo_api.py --api-url http://127.0.0.1:8000
```

브라우저 QA: 별도 테스트 디렉터리에 Playwright/Chromium을 설치하고 `PLAYWRIGHT_MODULE`에 모듈 경로를 지정할 수 있다.
기본은 `require('playwright')`와 Playwright 관리 Chromium이다. 특수 Linux 라이브러리 경로/실행 파일은
`LD_LIBRARY_PATH`, `CHROMIUM_EXECUTABLE`로 지정한다. 운영 의존성에는 Playwright를 설치하지 않는다.

```bash
MPRI_WEB_URL=http://127.0.0.1:3001 node scripts/check_release_browser.cjs
MPRI_WEB_URL=http://127.0.0.1:3001 node scripts/check_portfolio_revision.cjs
MPRI_WEB_URL=http://127.0.0.1:3001 node scripts/check_portfolio_browser.cjs
```

1. 승인 대상: 변경 diff/테스트, Git push 및 main 병합 범위, Render workspace/서비스 이름/region/월 예산/공개 범위.
2. 승인 후에만 feature 공유·PR 검토·main 병합을 수행한다. 기존 PR #4/#5의 기록을 수정하지 않는다.
3. 배포할 commit을 고정한다. 실제 Blueprint 화면에서 Python/Node 지원 버전과 예상 요금을 재확인한다.
4. API 먼저 실행·준비 확인 → 웹 build/시작. 같은 region private hostport 연결과 HTTPS를 검증한다.
5. 아래 검증을 통과한 후 시연 URL을 공유한다. 자동 배포는 계속 끈다.

## 배포 후 검증

- 공개 URL에서 9개 경로 200, 메뉴 선택 상태, KR/EN, 실제 휴대폰 HTTPS 접속 확인.
- `/api/portfolio/universe`와 `/scenarios` 200, 28개 자산·3개 시나리오.
- 예제 분석: 전 23.38%, 후 TLT30% 16.94%, NVDA 위험기여도 30.43 → 28.37%, What-if 10행.
- 입력/평가금액 변경 즉시 기존 결과 제거, 진행 중 요청 후 수정한 경우 이전 응답 무시.
- 빈/중복/미지원 ticker/잘못된 합계·금액 422 또는 전송 전 차단, API 장애는 안내 문구.
- 한국 2026-11-02 Risk40.2%, MSI0.753405, 임계1.115125. 연구 OOS와 운영 표시 분리.
- 미국 최신 N/A·revision 보류 및 과거 2026-10-02 Risk10.0% 날짜 구분.
- API/웹 로그 오류·메모리·지연 확인. 제공처 이용조건/공개 snapshot 재배포 권한도 배포 책임자가 확인한다.

## 롤백

배포 전 두 서비스의 이전 commit/deploy ID, 환경변수 이름·설정, snapshot manifest hash를 기록한다(비밀값은 Git에 남기지 않는다).
문제 시 자동 배포 off 확인 → 웹과 API를 **동일한 직전 검증 release 쌍**으로 rollback → health/핵심 경로/샘플 재검증.
내부 주소가 달라지면 웹 rebuild. 데이터 복구·재학습·미국 정책 완화를 롤백으로 대신하지 않는다.
최초 배포라 이전 release가 없으면 서비스 중지/공개 접근 차단하고 수정 후 재검증한다.

## 미완료 외부 검증

현재 실제 Render 계정·청구·DNS·TLS·private service discovery·클라우드 pip/npm clean build는 실행하지 않았다.
Docker daemon도 사용할 수 없지만 제안 구성은 Docker를 사용하지 않는 native runtime이다.
로컬 production 통합과 공식 Blueprint JSON schema 검증은 통과했다.
클라우드 실행 성공은 승인 후 실제 배포 검증에서만 확정할 수 있다.
