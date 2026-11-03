# 데이터 수집·Frozen V1 추론 구현 결과 — 2026-11-03

진단 후 별도 운영 경로를 구현했다. 원격 main과 동기화된 d2197c4에서
`feature/frozen-v1-operational-data` 브랜치를 생성했으며 commit/push/merge/배포하지 않았다.

| 항목 | 한국 | 미국 |
| --- | --- | --- |
| 수집 제공처 | KRX KOSPI200/VKOSPI, BOK ECOS 국고3년/회사 AA-3년 | Yahoo SPY/VIX, FRED Moody's DBAA/Treasury DGS10 |
| 이번 수집 마지막 실제 관측일 | 모두 2026-11-02 | 모두 2026-10-30 |
| 수집 기준 거래일 | 2026-11-02 | 2026-11-02 |
| 신규 운영 추론 | 성공 | 과거 reference 불일치로 보류 |
| 현재 Risk Score | **40.2%** | **N/A** |
| 현재 공식 MSI / 임계값 | **0.753405 / 1.115125** | **N/A** |
| 별도 과거 캐시 재현 추론 | 성공, 기존 캐시 마지막 2026-10-15 (운영 기록과 별도 유형) | 성공, 마지막 2026-10-02: Risk 10.0%, MSI -0.863097, 공식 임계값 1.292548 |
| 과거 OOS 기록 | 2026-09-16까지 보존 | 2026-09-21까지 보존 |

관측일과 수집 시각을 구분한다. 실제 수집 실행은 2026-11-03 14:11 KST경이며
최종 export는 동일 source SHA/receipt를 네트워크 없이 재생하여 생성했다.
각 채널의 정확한 UTC 수집 시각은 operational-markets.json의 series[].retrievedAt,
추론 시각은 inferenceAt에 있다. 재생 실행 시각을 재수집 시각으로 기록하지 않는다.

## 미국 보류 원인과 한계

원본 cache를 같은 계산기로 재계산하면 모든 저장 feature/MSI/threshold가
rtol/atol=1e-9에서 일치한다. 새로 내려받은 원천 자료를 사용하면 다음 차이가 있다.

- SPY 과거 원천 5,489행에 작은 수치 차이가 있다. 최대 가격 차이는
  0.00018310546875 USD, 최대 1D return 차이는 0.0000016384434다.
  provider/라이브러리의 조정가격 정밀도 차이가 가능한 원인이지만 확정하지 않는다.
- VIX와 기존 비결측 신용 원천은 일치한다. 원래 2026-10-05 credit는 결측이었고,
  연구 cleaner가 10/02의 1.47을 이월했다. 신규 수집에서는 10/05의 실제 1.46이
  관측되므로 기존 Credit_Level과 0.01 차이가 생긴다.
- 따라서 이는 API 실패나 모델 hash 변경이 아니다. 원천 vintage/뒤늦은 관측 때문에
  엄격한 기존 연구 수치 대조가 실패한 것이다. 작은 차이를 무시하거나 기존 원천을
  덮어쓰지 않았다. revision 수용 정책을 별도 검증하기 전 신규 US 점수를 발행하지 않는다.
- 미국 배포 모델의 정확한 학습 receipt가 없어 cutoff 2026-09-16은 scaler prefix
  근사 대조에 의한 추정이며, 확정된 학습 실행 시각이 아니다.
- 11/02의 필수 실제 관측도 이번 응답에는 없다. 웹에서 10/30 원천 관측 여부와 날짜별 가용성을 확인할 수 있지만
  현재 Risk/MSI로 이월하지 않는다. 공개 공유용 JSON에서는 원천 수치를 제외한다.

수치 차이 원문: [us_revision_review.json](us_revision_review.json).

## 변경 파일과 동작

- `market_engine/operations/run.py`: 고정 공식 계산기/제공처 재사용, 수집 receipt,
  원천/코드/reference/model SHA 검증, feature 순서·기존 StandardScaler 검증,
  reference 재현 대조, exact-date 추론, 누락 거래일 검증, 원자적 JSON 출력,
  오프라인 receipt 재생. 학습·OOS 평가·원본 운영 refresh/API는 실행하지 않는다.
- `market_engine/operations/contract.json`, `requirements.txt`, `README.md`, `__init__.py`:
  고정 모델·코드·feature 계약, 분리된 의존성 및 실행/출처/이용 제한 문서.
- `frontend/public/data/operational-markets.json`: 기존 연구 JSON과 별도 운영 export.
- `frontend/src/components/operational-market.tsx`: 한국·미국·출처 페이지에 현재 점수,
  마지막 유효 과거 추론, 원천별 날짜와 수집 시각, 최근 60개 날짜의 관측 여부·결측,
  모델 검증 및 이용 조건 표시. 관측일 선택은 OOS 선택과 분리한다.
- `frontend/src/components/{dashboard-view,research-panels}.tsx`:
  국가 카드에 검증된 운영 점수와 기준일을 표시하고 과거 OOS/breadth 구간을 구분한다.
- `frontend/src/lib/{dashboard-data,dashboard-types}.ts`, `frontend/src/app/globals.css`:
  별도 운영 데이터 읽기/타입과 표시 스타일. 기존 연구 시계열/성능 자료는 변경하지 않는다.
- `.gitignore`: `data/operations/` 원천·실행 산출물을 별도 로컬 보관.
- `tests/test_operational_markets.py`: 모델 schema/hash, 원천 결측, 학습 구간,
  비유한 feature, 과거 revision, 현재 exact-date/null 계약 검증.
- `tests/test_signal_divergence_monitor.py`: 기존 테스트가 임시 JSON 경로를 지정해도
  실제 연구 CSV를 갱신하던 부작용을 확인했다. 입력도 임시 root로 복사하도록 격리했다.
  해당 CSV는 최초 SHA와 정확히 일치하는 바이트로 복구한 뒤 최종 테스트를 통과했다.
- `reports/operations/`: 진단, revision 수치, 보존·검증 및 이 결과 보고서.

## 검증 및 보존

- 전체 Python 테스트 **95개 통과**. 기존 Starlette/httpx deprecation 경고 1건.
- TypeScript, ESLint, chart helper, production build 통과.
- 기존 Portfolio API/what-if/demo/server 회귀 테스트도 전체 통과.
- 시작 시 기록한 **1,525개 기존 data/model/report/src 파일 SHA 모두 동일**.
  원본 V1 저장소, Frozen V1, 기존 OOS/검증 결과, `src/portfolio/`,
  `data/portfolio/`, `/portfolio` 구현을 보존했다.
- 수집된 source SHA를 확인한 오프라인 재생에서 양 시장의 전체 추론 history가
  최초 수집 실행과 동일하다. 미국은 검증된 과거 cache history만 일치한다.
- 기본 샌드박스 DNS와 FastAPI TestClient 실행 제약은 허용된 외부 네트워크/테스트
  실행으로 재검증했다. 브라우저 시각 QA는 수행하지 않았다.

검증 증거: [validation.json](validation.json).

## 남은 운영 제약

현재 수동 수집/추론/export와 오프라인 재생을 제공한다. 웹은 정적 export를 읽으므로
수집 후 rebuild/restart해야 한다. 자동 스케줄러나 배포는 추가하지 않았다.
원본 V1 코드/캐시 checkout 의존성이 있으며, hash가 달라지면 자동 승인하지 않는다.
미국 revision 수용 정책과 학습 provenance 보강은 남아 있다.

공개 API 접근을 재배포 허가로 해석하지 않는다. Moody's DBAA는 저작권·재배포
제한을 명시하며 Yahoo/KRX 데이터에도 별도 조건이 있다. ECOS 상세 재배포 조건은
동적 포털로 인해 이번 조사에서 확정하지 못했다. 출처 원문과 확인 범위는
[운영 README](../../market_engine/operations/README.md)에 정리했다.

공개 저장소 공유 준비에서 원천 수치를 제외한 요약 export로 변경했다. 최신 공유 점검은
[SHARING_KO.md](SHARING_KO.md)를 참조한다. 위 push 미수행 기록은 초기 로컬 구현 완료 시점의 상태다.
