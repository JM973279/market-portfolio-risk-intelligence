# Phase 5 — 이전 정상 버전 복구 계획 (미실행)

기준일2026-11-04. 현재 배포 및 복구 목표 SHA는 **`97e78366a026e9221740526087ef8082a891fa28`**다. 이 문서는 배포·재시작·rollback 실행 승인이 아니다. 실패 시 복구까지 포함한 별도 승인을 먼저 확보한다. Git reset/force-push/main 병합으로 배포를 되돌리지 않는다.

## 보존할 대상

| 서비스 | 현재 live deploy / 향후 복구 목표 | branch |
|---|---|---|
| API `srv-dbkp73mgekts73eq0m20` | `dep-dbkp8krbc2fs73a0bjkg` | feature/mvp-release-readiness |
| 웹 `srv-dbkp8fvf3r2c73fi28fg` | `dep-dbkp8gff3r2c73fi29l0` | feature/mvp-release-readiness |

두 deploy의 SHA 일치를 Render GET으로 다시 확인했다. 이전 API deploy `dep-dbkp746gekts73eq0n2g`도 같은 SHA지만 최종 정상 설정이 반영된 **현재 live API deploy**를 우선 목표로 고정한다. source SHA만 같다고 deploy별 설정이 같다고 가정하지 않는다.

Free rollback은 최근 이전 2개 deploy 및 보존 artifact 범위 내에서 가능하다. 현재 live deploy가 신규 배포 후 rollback 대상으로 실제 표시되는지 **배포 직전 및 직후** 확인한다. artifact retention에 대한 API 이력 필드만으로 확정하지 않는다. 실패가 반복돼 목표가 밀려날 수 있으므로 불필요한 시험 deploy는 하지 않는다. artifact가 없을 때는 같은 SHA의 수동 rebuild가 대안이지만 dependency 재해석 등으로 동일 artifact를 보장하지 못한다. 별도 승인과 재검증 없이 실행하지 않는다. 복구 수단이 확보되지 않으면 신규 배포를 시작하지 않는다.

## 버전 조합과 순서

| 웹 | API | 사전 근거 / 판정 |
|---|---|---|
| 현재97e783 | 현재97e783 | 현재 공개 health/root200, 과거 배포 검증 기록 존재 |
| 현재97e783 | Phase4 1db2dc2 | 기존 V1 route/schema와 전체 before/after/compare 응답 일치. API 우선 검증 후보. 이 조합의 공개 브라우저 검증은 미실행 |
| Phase4 1db2dc2 | Phase4 1db2dc2 | 로컬 Chromium390/1280px 및 수치 회귀 통과 |
| Phase4 1db2dc2 | 현재97e783 | **호환 불가**: 새 웹의 `/api/portfolio/v2/catalog`가 구 API에서는404. 검색/분석 준비 실패 가능 |

권장 배포 순서는 **API만 우선**, 기존 웹 유지다. 웹 확장은 API 검증 후 별도 승인한다. 둘 다 올린 경우 복구는 **웹→API** 순서로 진행한다. 새 웹이 아직 남아 있는데 API부터 구 버전으로 내리지 않는다. API 긴급 장애로 이 순서를 유지할 수 없다면 일시 UI 실패를 명시하고 담당자 승인하에 두 서비스 복구를 조정한다.

## 승인 후 복구 절차

1. 신규 요청·자동 시험을 중단한다. 오류 상태별 수, 수치 차이, 대상 commit/deploy ID, sanitized 메트릭과 OOM/restart 이벤트를 보존한다. 토큰·환경변수 값·일반 사용자 로그는 보고서/Git에 저장하지 않는다.
2. M/PRI 두 서비스만 대상으로 하고, 실제 현재 live deploy와 목표 ID/SHA를 확인한다. auto deploy가 기존처럼 off인지 확인한다. 환경변수 이름·설정 fingerprint는 보존하되 비밀 값은 안전한 기존 관리 경로에서만 확인한다.
3. 웹도 바뀌었다면 Dashboard Deploys의 목표 웹 deploy에 **Rollback to this deploy**를 선택하고 완료를 확인한다. 기존 웹이 그대로라면 재배포/rollback하지 않는다.
4. API의 목표 `dep-dbkp8krbc2fs73a0bjkg`로 rollback한다. live 전환 후 Render GET으로 새 rollback deploy의 SHA가97e783인지 확인한다. 원래 deploy ID 자체가 다시 live ID가 된다고 가정하지 않는다.
5. Dashboard rollback은 자동 배포를 off로 바꾸지만 API rollback은 자동 배포를 끄지 않는다. 어떤 방식을 사용해도 최종 off를 확인한다. compute plan 등 일부 설정은 rollback되지 않으며, 환경그룹 값도 별도 동작한다. 목표 deploy의 start/health/env 동작과 현재 서비스 설정의 차이를 확인한다. 이번 작업에서는 설정 변경 자체를 하지 않았다.
6. 아래 복구 기준을 작은 요청 수로 확인하고 통과 전에는 부하를 재개하지 않는다. 실패하면 추가 deploy/유료 전환을 반복하지 말고 원인·불가항목을 보고한다.

## 복구 성공 기준

- Render control plane에서 API/웹 모두 live, SHA97e783, 지정 branch, Free·1 instance·자동 배포 off. 이전과 같은 서비스 ID·주소이며 다른 서비스에 변경이 없어야 한다.
- API `/health`: HTTP200, JSON `status=ok`, `as_of=2026-10-23`. 웹 `/`: HTTP200 HTML. cold readiness는 최대3번, 15초 이상 간격·60초 timeout으로 한정하고 무한 polling하지 않는다.
- API universe28개, scenarios3개. before/after analyze와 compare 각각200; 입력 오류422. 기존 before volatility23.38%, after16.94%, NVDA 기여30.43%→28.37%, What-if10행을 포함해 **응답 전체**를 기준 canonical SHA/fixture와 비교한다.
- `config/portfolio-snapshot.sha256.json`의 5개 파일 SHA 검사를 통과한다. 공개에는 manifest endpoint가 없으므로 승인된 내부 계측/배포 artifact 검사 또는 기존 require_snapshot 성공 증거와 검증된 source를 함께 사용한다. health만으로 별도 시장 export 전체의 SHA를 증명했다고 하지 않는다.
- 시장 operational export는 기준 commit의 `frontend/public`와 동일해야 한다. 기존 배포 기록의 operational export SHA는 `14d6ebc441b40666b2eb06a80648acc521bf4ad7d162bcc2179b545ec07bbcd7`다. 이번 사전 작업은 새 공개 export 요청 없이 로컬 byte 보존만 확인했다.
- 구 버전 API의 `/v2/catalog`404는 예상된다. 구 버전 웹은 V1 universe를 사용하므로 동작해야 한다. 복구 후 신규52개 검색 UI나 V2 409를 구 API의 필수 성공 기준으로 요구하지 않는다.
- 승인된 범위의 브라우저에서 Hidden Risk/Stress/What-if와 오류 안내를 확인한다. API/schema·합산 수치만으로 브라우저 전체 호환을 확정하지 않는다. 예상 밖500/503/504, process 재시작, 수치 불일치가 없어야 한다. 단일 smoke 성공이 장시간 안정성 증명은 아니다.

실행 증거는 [사전 상태](PORTFOLIO_PHASE5_RENDER_STATE.json), [로컬 회귀](PORTFOLIO_PHASE5_REGRESSION.json)에 분리했다. **실제 rollback 테스트는 미실행**이다.

공식 참고(2026-11-04 확인): [Rollback 동작·retention·설정 범위](https://render.com/docs/rollbacks), [Free 이전2개 제한](https://render.com/docs/free), [특정 commit 수동 배포](https://render.com/docs/deploys).
