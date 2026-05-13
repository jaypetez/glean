### Build stage ###
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /usr/local/bin/uv

WORKDIR /app

# Layer 1: dependencies (changes rarely)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv \
 && uv sync --frozen --no-dev --no-install-project

# Layer 2: application code (changes often)
# --no-editable so the venv contains a real copy of the package, not a
# .pth file pointing back at /app/src (which would break when only /opt/venv
# is copied to the runtime stage).
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

### Runtime stage ###
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PATH="/opt/venv/bin:$PATH" \
    GLEAN_CONFIG=/etc/glean/feeds.yaml \
    GLEAN_DB=/data/state.db \
    HEALTH_PORT=9090 \
    LOG_LEVEL=INFO \
    TZ=UTC

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system glean \
 && useradd --system --no-log-init --gid glean --home /home/glean --create-home glean \
 && mkdir -p /data /etc/glean \
 && chown -R glean:glean /data /etc/glean

COPY --from=builder /opt/venv /opt/venv

USER glean
WORKDIR /home/glean

EXPOSE 9090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9090/healthz', timeout=4)" || exit 1

ENTRYPOINT ["glean"]
CMD ["run"]
