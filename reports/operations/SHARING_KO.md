# GitHub 공유 전 검증 — 2026-11-03

작업 브랜치: `feature/frozen-v1-operational-data`.
원격 `main` fetch 결과 기준 커밋은 `d2197c47f9ad05e7759522ebd5c312e90c0bfd91`이며
공유 준비 시점 HEAD와 동일(0 ahead / 0 behind)하다. 원격에 동일 feature 브랜치는 없었다.
따라서 이번 변경과 최신 main 사이에 충돌할 upstream 변경은 없다.

## 보안 및 포함 범위

- 변경·신규 후보 파일을 대상으로 기존 환경의 실제 인증정보 값과 private key,
  AWS/GitHub token 패턴을 검사했다. 인증정보가 포함된 파일은 발견되지 않았다.
  검사에서는 파일명과 일치 여부만 출력했으며 인증정보 값을 출력/기록하지 않았다.
- `.env`, `.env.*`, `.venv/`, 원천/processed cache, `data/operations/`는 제외한다.
  `.env.example`만 예외로 허용하며 이번 변경에 해당 파일은 없다.
- 모델 바이너리, 원천 CSV, pickle, SQLite DB, 전체 수집 receipt/cache, 빌드 산출물을
  신규 커밋에 포함하지 않는다. 1 MiB 이상 변경 후보 파일도 없다.
- 저장소가 **public**이므로 운영 JSON에서 원천 가격·금리 수치를 제거했다.
  `availability[].values`는 제외하고 추론 행의 `price`는 null로 내보낸다.
  출처·관측일·수집 시각·가용성·SHA, 파생 Risk/MSI/공식 임계값은 유지한다.
  전체 원천은 로컬 `data/operations/`에 보관하며 공개 공유하지 않는다.
- 파생 지표 공개가 원천 데이터의 모든 이용·배포 권리를 확보했다는 의미는 아니다.
  제공처별 제한과 확인하지 못한 ECOS 상세 조건은 운영 README에 명시했다.

## 보존과 결과

- 최초 기록한 기존 data/model/report/src 파일 **1,525개 SHA-256 동일**.
- Frozen V1 모델, 공식 계산 코드, 과거 OOS/검증 산출물, `src/portfolio/`,
  Portfolio snapshot, `/portfolio` 분석 구현 및 API 코드에 변경 없음.
- 사이드바에 KR `포트폴리오 분석` / EN `Portfolio Analysis` 메뉴와 기존 스타일의
  아이콘을 추가했다. `/portfolio`의 기존 공통 레이아웃·선택 상태를 사용한다.
- 한국: **2026-11-02 신규 운영 추론 성공**. Risk **40.2%**, MSI **0.753405**,
  공식 임계값 **1.115125**.
- 미국: 원천 **2026-10-30**까지 수집했으나 과거 SPY 수치 정밀도 차이와
  뒤늦게 채워진 10/05 신용 관측 때문에 reference 대조 실패. **최신 추론 보류**,
  현재 Risk/MSI는 **N/A**. 검증된 과거 캐시 재현은 **2026-10-02**까지 성공했으며
  Risk **10.0%**, MSI **-0.863097**, 임계값 **1.292548**. OOS와 구분한다.
- 미국 모델 학습 cutoff는 receipt 부재로 scaler prefix 근사 대조에 의한 추정이다.
- 공개 JSON의 파생 수치가 로컬 검증 결과와 동일함을 확인했다.

## 최종 검증

- `python -m pytest tests -q`: **95 passed**, 기존 Starlette/httpx deprecation 경고 1건.
  API 테스트 실행 시 샌드박스의 TestClient 제약을 피하는 실행 환경을 사용했다.
- `npx tsc --noEmit`, `npm run lint`, `npm run test:charts`, `npm run build`: 통과.
- production HTML에서 `/portfolio`, `/korea`, `/us`의 공통 사이드바,
  포트폴리오 링크 및 각 페이지의 선택 상태를 확인했다. 브라우저 시각 QA는 미실시.
- 기존 monitor 테스트의 CSV 출력도 임시 디렉터리에 격리되어 최종 검사 중
  기존 연구 산출물을 덮어쓰지 않는다.

이번 승인은 **feature 브랜치 커밋·push 및 PR 생성**에만 적용한다.
main 병합·배포 명령은 실행하지 않는다. 자동 병합도 설정하지 않는다.
웹은 정적 export 기반이며 원본 V1 checkout 의존성과 미국 revision 검증 제약이 남는다.
