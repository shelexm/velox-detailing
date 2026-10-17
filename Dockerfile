# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/venv/bin:$PATH
WORKDIR /app

FROM base AS deps
RUN python -m venv /opt/venv
COPY requirements.lock ./
RUN pip install -r requirements.lock

FROM base AS runtime
RUN groupadd --system --gid 10001 velox \
    && useradd --system --uid 10001 --gid velox --home-dir /app --shell /usr/sbin/nologin velox
COPY --from=deps /opt/venv /opt/venv
COPY alembic.ini pyproject.toml ./
COPY migrations ./migrations
COPY app ./app
COPY static ./static
RUN mkdir -p /app/media && chown velox:velox /app/media
USER velox
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4)"]
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--timeout-graceful-shutdown", "15"]

FROM runtime AS test
USER root
COPY requirements-dev.lock ./
RUN pip install -r requirements-dev.lock
COPY tests ./tests
COPY scripts ./scripts
RUN chown -R velox:velox /app
USER velox
CMD ["pytest"]
