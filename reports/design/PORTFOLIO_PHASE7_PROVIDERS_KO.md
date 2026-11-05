# Phase 7 공급자 검토 — 2026-11-05

공식 문서의 제공 범위와 권리 조건을 조사했다. 가격 다운로드·정확성 실측·API 키 발급·유료 가입은 수행하지 않았다. 아래 품질 평가는 공급자 설명과 검증해야 할 항목이며 정확성 인증이 아니다. 기존 source_rights_review.json과 registry.json의 승인 상태는 변경하지 않는다. 신규 가격/팩터 승인 모두 0개.

| 공급자 | 시장·이력·갱신 | 품질 검증 항목 | 제한·비용 | 공개 서비스 권리와 결정 |
|---|---|---|---|---|
| KRX OPEN API | KOSPI/KOSDAQ/ETF 일별, 서비스 목록상 2010-01-04부터 | 거래소 원천이나 수정주가·배당·권리락 별도 검증 | 인증키 필요. 호출 한도·무료 범위는 현행 약관 재확인 필요 | 약관 원문 경로 조회 실패. 공개 파생 분석·저장·재배포 권리 미확인으로 차단 |
| 금융위/공공데이터포털 | 한국 주식·ETF, 주식 안내는 일1회 다음 영업일 13시 이후. 전체 역사 시작일 미확인 | 포털 메타데이터의 실시간 표기와 설명 불일치. 설명상 지연값을 기준으로 설계. 기업행동 별도 필요 | 무료 접근, 키/트래픽·과거 범위 실측 미실시 | 공공누리4유형, 상업적 이용·변경 제한 및 제3자 무단 재배포 금지. 무료 API를 공개 서비스 허가로 해석하지 않음 |
| Alpha Vantage | global daily adjusted 25년 이상 안내, 일별/장중 상품별 | 조정종가·배당·분할 제공 설명, 실제 표본 대조 필요 | 무료 일반 한도 25회/일. daily adjusted는 premium. 상업 계약 견적 별도 | 기본 개인 비상업. 조직·외부 사용자 공개는 별도 서면 합의 필요. 차단 |
| Twelve Data | 다시장, 과거 범위·지연·실시간은 거래소/상품/플랜별 | 심볼 목록 노출은 가격 접근 보증 아님. 한국 데이터·수정주가 범위 확인 필요 | REST/WS 크레딧·플랜별 과금. 사업용+거래소 추가비용은 견적 필요 | 사업 플랜도 비미국 상업 사용 추가 승인, 재배포 별도 계약. 비복원 파생값·출처표시 조건 검토 필요. 차단 |
| Massive | 미국 주식/ETF, 이력은 플랜 rolling window, business 전체 이력 안내 | 통합 거래/호가·기업행동, 조정·수정 이력 별도 검증 | 개인/사업용 별도. 사업·거래소 entitlement 및 운영 호출량 견적 필요 | 개인 구독은 재배포 불가. 파생값 권리도 사용 형태별 확인. 차단 |
| Yahoo/yfinance, Stooq | 기존 Phase 3 검토 참조. 가격/이력 가용성이 권리 증거가 아님 | 기업행동·조정·정정 검증 미완료 | 비공식 경로 SLA/호출 제한 미확정 | 공개 사용 권리 미확인. 추가 수집 없음 |
| FRED / Fed H.15 / Cboe VIX | 기존 팩터 검토 유지 | 금리 단위·빈티지, VIX 지수 권리·캘린더·정정 검증 | 공급자·시리즈별 조건, 운영 비용 미산정 | H.15의 공공 정보 가능성이 가격·VIX 권리를 대체하지 않음. 신규 팩터 승인 없음 |

고정 가격표를 서비스 예산으로 간주하지 않는다. 전체 종목수 × 일별 요청량, 초기 757세션 backfill, 재시도·정정·기업행동, 저장/백업 비용과 외부 사용자·파생결과·배포 산출물 권리를 명시한 견적이 필요하다. 현재 공급자별 정확도 수치·가용성 SLA·실측 지연은 없음.

공식 근거:
- https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd
- https://openapi.krx.co.kr/contents/OPP/MAIN/main/index.cmd
- https://www.data.go.kr/catalog/15094808/openapi.json
- https://www.data.go.kr/catalog/15094806/openapi.json
- https://www.alphavantage.co/documentation/
- https://www.alphavantage.co/support/
- https://www.alphavantage.co/terms_of_service/
- https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage
- https://twelvedata.com/pricing-business
- https://massive.com/knowledge-base/article/how-much-historical-stock-data-does-massive-have
- https://massive.com/knowledge-base/article/how-can-i-redistribute-massives-market-data

위 조건은 프로젝트용 권리 검토 기록이며 신규 라이선스 승인 문서가 아니다. KRX 약관 조회 실패 내용은 제3자 설명으로 대체 확정하지 않았다.
