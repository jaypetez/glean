### Build stage ###
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# uv: fast Python package installer.
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src

RUN uv venv /opt/venv \
 && uv pip install --python /opt/venv/bin/python --no-cache .

### Runtime stage ###
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    GLEAN_CONFIG=/etc/glean/feeds.yaml \
    GLEAN_DB=/data/state.db \
    HEALTH_PORT=9090 \
    LOG_LEVEL=INFO \
    TZ=UTC

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system glean \
 && useradd --system --gid glean --home /home/glean --create-home glean \
 && mkdir -p /data /etc/glean \
 && chown -R glean:glean /data /etc/glean

COPY --from=builder /opt/venv /opt/venv

USER glean
WORKDIR /home/glean

EXPOSE 9090

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:9090/healthz || exit 1

ENTRYPOINT ["glean"]
CMD ["run"]
