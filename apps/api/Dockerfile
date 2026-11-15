# syntax=docker/dockerfile:1.7
FROM python:3.15-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app
# Tesseract (English) for OCR of pages without a text layer (spec 004 AC10).
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 app

# --- production image: runtime deps only ---
FROM base AS prod
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/healthz',timeout=2).status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

# --- dev image: includes dev deps; source is bind-mounted by compose ---
FROM base AS dev
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project
COPY . .
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- enrichment worker (spec 009, D85): Docling with CPU-only PyTorch, models baked in ---
# Only the background worker runs this image; the API and the fast worker stay small. Models are
# downloaded at build time because workers run with a read-only root and no model downloads.
FROM base AS enrich-base
ENV DOCLING_ARTIFACTS_PATH=/opt/docling-models \
    UV_CACHE_DIR=/root/.cache/uv \
    OMP_NUM_THREADS=2

FROM enrich-base AS enrich
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project --group enrichment
RUN docling-tools models download --output-dir /opt/docling-models layout tableformer \
 && chmod -R a+rX /opt/docling-models
# Runtime: read-only root, so model caches point at /tmp and nothing is downloaded.
ENV HF_HUB_OFFLINE=1 HF_HOME=/tmp/hf TORCH_HOME=/tmp/torch XDG_CACHE_HOME=/tmp/cache
COPY app ./app
USER app
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=INFO", "-Q", "enrichment,scan,deletion", "--concurrency=1"]

FROM enrich-base AS enrich-dev
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project --group enrichment
RUN docling-tools models download --output-dir /opt/docling-models layout tableformer \
 && chmod -R a+rX /opt/docling-models
ENV HF_HUB_OFFLINE=1 HF_HOME=/tmp/hf TORCH_HOME=/tmp/torch XDG_CACHE_HOME=/tmp/cache
COPY . .
USER app
