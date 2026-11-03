# Render 무료 배포 완료

검증일: 2026-11-03. 실제 Render CLI/API 배포 및 공개 HTTPS Chromium 검증 완료.

- 웹: https://mpri-mvp-web.onrender.com
- Portfolio API health: https://mpri-portfolio-api.onrender.com/health
- GitHub 브랜치: `feature/mvp-release-readiness`
- API/웹 실제 배포 commit: `97e78366a026e9221740526087ef8082a891fa28`
- 두 서비스 모두 **Singapore / Free / 1 instance**, 자동 배포 off.
- 소스 수정 없이 지정 커밋을 배포했다. main 병합·유료 전환·결제수단 등록 없음.

## 서비스 및 실행

| 서비스 | Render ID | 최종 배포 ID | health |
|---|---|---|---|
| mpri-portfolio-api | srv-dbkp73mgekts73eq0m20 | dep-dbkp8krbc2fs73a0bjkg | /health:200 |
| mpri-mvp-web | srv-dbkp8fvf3r2c73fi28fg | dep-dbkp8gff3r2c73fi29l0 | /:200 |

API를 먼저 생성하고 health 및 실제 분석/비교를 검증한 뒤 웹을 생성했다.
API root는 저장소 루트, 웹 root는 frontend. Build/Start는 기존 render.yaml 명령을 사용했다.
API Python3.14.4, 웹 Node22.22.1. API1worker, BLAS1, docs/OpenAPI 비활성.
웹 환경변수 `PORTFOLIO_API_INTERNAL_URL=https://mpri-portfolio-api.onrender.com`을 build 전에 설정했다.
`NEXT_PUBLIC_PORTFOLIO_API_URL`은 미설정으로 브라우저 상대 경로/서버 proxy를 사용한다.
실제 웹 origin을 API `PORTFOLIO_API_CORS_ORIGINS=https://mpri-mvp-web.onrender.com`에 넣고
같은 지정 commit으로 API를 재배포했다. CORS allowed preflight200, 다른 origin preflight400을 확인했다.

## 실제 검증

- 두 서비스 latest deploy status live, commit SHA 정확히 일치.
- API health `{"status":"ok","as_of":"2026-10-23"}`.
- 자산28개/시나리오3개, 분석/비교200, 잘못된 입력422.
- 실제 Chromium의 공개 웹에서 샘플5개 분석 요약·위험기여도·상관행렬·팩터·Stress3개 각각 API와 일치.
- before 변동성23.38%, TLT30% after16.94%, NVDA 기여도30.43% →28.37%, What-if10행.
- holdings/금액/제안 변경 무효화, 지연 응답 무시, Compare current 동기화 통과.
- 실제 서버 응답 검증과 별도로 브라우저에 500/503/422/연결 실패/null Stress를 주입한 오류 안내 회귀도 통과.
- 9개 경로200/선택 상태, KR/EN, 360/390px 모바일 emulation 및 메뉴 이동 통과.
- 한국 운영2026-11-02 Risk40.2%, MSI0.753, 공식 임계1.115 표시.
- 미국 최신N/A·reference 검증 보류, 별도 과거2026-10-02 Risk10.0%와 OOS 분리 유지.
- 배포된 operational JSON은 지정 commit의 로컬 파일과 byte/SHA256 일치:
  `14d6ebc441b40666b2eb06a80648acc521bf4ad7d162bcc2179b545ec07bbcd7`.
- 페이지 JavaScript 예외 및 예기치 않은 console error0.

## 보호 및 비용

서비스 생성 전 기록과 비교하여 기존 ai-ratescope/ratescope/finance-lens/ratescope-in3w의
repo·branch·root·autoDeploy·suspended·serviceDetails 설정이 모두 동일함을 확인했다.
기존 서비스에는 수정/재배포/재시작/중지 요청을 하지 않았다.
Frozen V1·Portfolio 엔진·snapshot5개·미국 정책 변경 없음. API key/token은 결과/보고서/Git에 포함하지 않았다.
CLI 인증은 사용자 로컬 설정에만 보관하며 이 보고서에는 인증정보가 없다.

사용자가 확인한 초기 사용량: Free hours0.62/750, bandwidth1MB/5GB, pipeline0/500분, services4/25.
결제수단 미등록은 사용자 확인을 근거로 했으며 CLI로 독립 조회한 것은 아니다.
이번 생성은 Free2개뿐이고 유료 compute/Performance pipeline/디스크/DB/도메인을 추가하지 않았다.
배포 후 잔여 사용량은 CLI/API로 조회할 수 없으므로 Billing에서 확인해야 한다.

무료 서비스는15분 유휴 후 휴면하며 재기동에 약1분 걸릴 수 있다.
시연 전에 API health200을 기다린 뒤 웹/Portfolio를 연다. 초기 연결 실패 안내가 나오면 기동 후 새로고침한다.
무료 시간은 workspace 전체 공유이며 소진 시 기존 무료 서비스에도 중단 영향이 있다.
CORS는 브라우저 출처 제한이며 공개 API 자체를 인증으로 보호한 것은 아니다.
물리 휴대폰 및 장시간 idle 복귀는 별도 최종 리허설이 필요하다.

## 운영·복구

자동 배포 off 유지. 추후 수동 배포는 승인된 commit을 명시한다.
웹/API 주소 변경 시 환경변수·CORS를 함께 바꾸고 웹 rebuild가 필요하다.
두 서비스는 같은 검증 release 쌍을 유지한다. 문제가 생기면 기존 서비스가 아닌 M/PRI만 대상으로 복구한다.
API는 최초 live 배포가 dep-dbkp746gekts73eq0n2g였고, 최종 CORS 반영 배포가 위 표의 ID다.
최초 웹에는 이전 live release가 없으므로 무조건 rollback 가능하다고 가정하지 않는다.
고정 snapshot/운영 export 갱신은 별도 검증 작업이며 클라우드에서 실시간 수집·재학습하지 않는다.

기계 판독 검증 결과: `RENDER_DEPLOYMENT_VERIFICATION.json`.
이 배포 보고서는 로컬에만 추가했고 추가 GitHub push·main 병합은 하지 않았다.
