# AWS 배포: Lightsail 컨테이너 서비스

웹과 Portfolio API를 Lightsail 컨테이너 서비스 하나에 함께 올립니다. 웹만 공개 주소(HTTPS)를 갖고, API는 같은 서비스 안에서만 접근합니다.
App Runner는 2026-04-30부터 신규 고객을 받지 않아 쓰지 않습니다. [AWS 안내](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html)

## 구성

| 컨테이너 | 이미지 | 포트 | 공개 |
| --- | --- | --- | --- |
| `web` | `infra/aws/web.Dockerfile` (Next.js) | 3000 | 공개 주소, 상태 확인 `/` |
| `api` | `infra/aws/api.Dockerfile` (FastAPI) | 8000 | 내부 |

- 같은 서비스의 컨테이너는 `localhost`로 통신합니다. [Lightsail 배포 문서](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-container-services-deployments.html)
- 웹은 빌드할 때 `/api/portfolio/*` 전달 대상을 `http://127.0.0.1:8000`으로 고정합니다. 브라우저는 웹 주소만 호출하므로 CORS 설정이 필요 없습니다.
- API 이미지는 빌드할 때 `require_snapshot()`으로 스냅샷 해시를 확인합니다. Render 설정과 같은 검사입니다.
- 시장 화면의 운영 데이터(`frontend/public/data/*.json`)는 웹 이미지에 들어갑니다. 데이터를 갱신하면 웹 이미지를 다시 빌드해 배포해야 합니다.

## 비용

Micro(메모리 1GB, 0.25 vCPU) 1개 노드 기준 월 약 US$10입니다. 서비스를 만든 순간부터 과금되고, 삭제해야 멈춥니다. [Lightsail 컨테이너 FAQ](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-faq-containers.html)
로컬 측정 메모리는 웹 166MiB, API 96MiB로 합계 약 260MiB입니다(시연 분석 실행 후).

## 로컬 검증

저장소 루트에서 실행합니다. 웹이 API 컨테이너의 네트워크를 함께 써서 Lightsail과 같은 `localhost` 구조를 재현합니다.

```bash
docker compose -f infra/aws/compose.yaml up --build -d
# http://localhost:3000/portfolio
docker compose -f infra/aws/compose.yaml down
```

2026-11-10 확인 결과: `/`, `/portfolio`, `/us`, `/korea` 모두 200. 웹을 거친 API 호출에서 시연 수치가 기획과 같았습니다(변동성 23.38% → 16.94%, 주식 급락 손실 30.16% → 21.95%, 금리 충격 손실 2.33% 유의, NVDA 위험 기여도 30.43%).

## 배포

준비(한 번):

1. 리전 설정: `aws configure set region ap-northeast-2 --profile market-stress-scheduler`
2. 로그인: `aws login --profile market-stress-scheduler`
3. Lightsail 이미지 업로드 도구 `lightsailctl` 설치. [설치 안내](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-install-software.html)

배포:

```bash
docker compose -f infra/aws/compose.yaml build
export AWS_PROFILE=market-stress-scheduler
CREATE_SERVICE=yes infra/aws/deploy_lightsail.sh   # 처음 한 번만 CREATE_SERVICE=yes
infra/aws/deploy_lightsail.sh                      # 이후 갱신
```

스크립트는 두 이미지를 올리고 새 배포를 만든 뒤, 새 버전이 활성화될 때까지 기다렸다가 공개 주소를 출력합니다. 인증은 AWS CLI 기본 규칙(`AWS_PROFILE` 또는 내보낸 `AWS_*` 자격 증명)을 따르고, `AWS_REGION`(기본 `ap-northeast-2`), `LIGHTSAIL_SERVICE`(기본 `mpri`), `LIGHTSAIL_POWER`(기본 `micro`)로 바꿀 수 있습니다.

Windows PowerShell에서 `aws login`을 했다면 WSL에서는 그 로그인을 직접 쓰지 못합니다. 실행하는 셸에서만 임시 자격 증명을 가져옵니다(파일에 저장하지 않음).

```bash
eval "$("/mnt/c/Program Files/Amazon/AWSCLIV2/aws.exe" configure export-credentials \
  --profile market-stress-scheduler --format env-no-export | tr -d '\r' | sed 's/^/export /')"
```

## 실패와 되돌리기

- 새 배포가 실패하면 Lightsail은 이전 배포를 그대로 유지합니다. 원인은 콘솔의 컨테이너 로그에서 확인합니다.
- 최근 50개 배포 버전이 보관되므로 콘솔에서 이전 버전으로 다시 배포할 수 있습니다.
- AWS 주소를 검증하기 전까지 Render 서비스는 백업으로 유지합니다.

## 아직 확인하지 않은 것

- 실제 AWS 실행: 2026-11-10 기준 로그인 세션이 만료돼 스크립트를 AWS에서 돌려 보지 않았습니다.
- 첫 응답 시간. 서울 리전(`ap-northeast-2`)에서 컨테이너 서비스 용량(Nano·Micro·Small)이 조회되는 것까지는 2026-11-10에 확인했습니다.
