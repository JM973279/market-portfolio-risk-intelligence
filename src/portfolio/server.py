import os
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.portfolio.analytics import load_snapshot_meta
from src.portfolio.api import router
from src.portfolio.v2_api import router as v2_router
from src.portfolio.readiness import require_snapshot
from src.portfolio.execution import bounded_endpoint, portfolio_lifespan

# 포트폴리오 API를 단독으로 띄우는 앱입니다.
#   uvicorn src.portfolio.server:app --port 8000
# 메인 앱이 생기면 이 파일의 V1 및 V2 router를 각각 연결합니다.
DEFAULT_ORIGINS = "" if os.getenv("RENDER") == "true" else "http://localhost:3000,http://127.0.0.1:3000"
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("PORTFOLIO_API_CORS_ORIGINS", DEFAULT_ORIGINS).split(",")
    if o.strip()
]

if os.getenv("RENDER") == "true":
    for origin in CORS_ORIGINS:
        parsed = urlsplit(origin)
        if "*" in origin or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Render CORS origins must be exact public HTTPS origins without paths or wildcards")

# Disable interactive docs/OpenAPI on Render; keep /health and business endpoints.
DOCS_ENABLED = os.getenv("PORTFOLIO_API_DOCS_ENABLED", "false" if os.getenv("RENDER") == "true" else "true").lower() == "true"
app = FastAPI(
    title="Portfolio Risk API",
    lifespan=portfolio_lifespan,
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url="/redoc" if DOCS_ENABLED else None,
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(router)
app.include_router(v2_router)


@app.get("/health")
@bounded_endpoint
def health():
    require_snapshot()
    return {"status": "ok", "as_of": load_snapshot_meta()["as_of"]}
