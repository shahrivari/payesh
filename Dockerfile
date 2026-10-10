FROM python:3.14-slim-trixie AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim-trixie
RUN groupadd --gid 10001 payesh && useradd --uid 10001 --gid payesh --create-home payesh \
    && mkdir -p /data && chown payesh:payesh /data
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PAYESH_DATA_DIR=/data PAYESH_UPDATE_INTERVAL=60 PAYESH_HOST=0.0.0.0
USER payesh
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/stats', timeout=3)" || exit 1
ENTRYPOINT ["payesh-web"]
