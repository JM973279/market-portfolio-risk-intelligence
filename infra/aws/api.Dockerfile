# Portfolio API image for the AWS Lightsail container service.
# Build from the repository root: docker build -f infra/aws/api.Dockerfile .
FROM python:3.14.4-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    PORTFOLIO_API_DOCS_ENABLED=false \
    PORT=8000

WORKDIR /app
COPY requirements.portfolio.txt .
RUN pip install --no-cache-dir --root-user-action=ignore -r requirements.portfolio.txt

COPY config/portfolio-snapshot.sha256.json config/
COPY data/portfolio/ data/portfolio/
COPY src/ src/
# Same gate as render.yaml: refuse an image whose snapshot differs from the manifest.
RUN python -c 'from src.portfolio.readiness import require_snapshot; require_snapshot()'

USER nobody
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=3)"
CMD ["sh", "-c", "exec python -m uvicorn src.portfolio.server:app --host 0.0.0.0 --port \"$PORT\" --workers 1"]
