### UI build stage ###
FROM node:22-alpine@sha256:968df39aedcea65eeb078fb336ed7191baf48f972b4479711397108be0966920 AS ui-builder

WORKDIR /ui

# Copy package files first for better caching
COPY ui/package.json ui/package-lock.json* ./
RUN npm install --no-audit --no-fund --prefer-offline

# Copy the rest of the UI source and build
COPY ui/ ./
RUN npm run build


### Build stage (existing Python build) ###
FROM python:3.13-slim-trixie@sha256:dc1546eefcbe8caaa1f004f16ab76b204b5e1dbd58ff81b899f21cd40541232f AS builder

RUN apt-get update \
 && apt-get -y --no-install-recommends upgrade \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY --from=ghcr.io/astral-sh/uv:0.5.13@sha256:ea61e006cfec0e8d81fae901ad703e09d2c6cf1aa58abcb6507d124b50286f9f /uv /usr/local/bin/uv

WORKDIR /app

# Layer 1: dependencies (changes rarely)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv \
 && uv sync --frozen --no-dev --no-install-project

# Layer 2: application code (changes often)
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


### Runtime stage ###
FROM python:3.13-slim-trixie@sha256:dc1546eefcbe8caaa1f004f16ab76b204b5e1dbd58ff81b899f21cd40541232f AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PATH="/opt/venv/bin:$PATH" \
    GLEAN_CONFIG=/etc/glean/feeds.yaml \
    GLEAN_DB=/data/state.db \
    GLEAN_UI_DIST=/home/glean/ui/dist \
    HEALTH_PORT=9090 \
    LOG_LEVEL=INFO \
    TZ=UTC

RUN apt-get update \
 && apt-get -y --no-install-recommends upgrade \
 && apt-get install -y --no-install-recommends tzdata ca-certificates \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system glean \
 && useradd --system --no-log-init --gid glean --home /home/glean --create-home glean \
 && mkdir -p /data /etc/glean /home/glean/ui \
 && chown -R glean:glean /data /etc/glean /home/glean

COPY --from=builder /opt/venv /opt/venv
COPY docker/curl /usr/local/bin/curl
RUN chmod 0755 /usr/local/bin/curl
COPY --from=ui-builder --chown=glean:glean /ui/dist /home/glean/ui/dist

USER glean
WORKDIR /home/glean

EXPOSE 9090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9090/healthz', timeout=4)" || exit 1

ENTRYPOINT ["glean"]
CMD ["run"]
