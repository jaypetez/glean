#!/usr/bin/env bash
# Example 06 setup — Weekly AI news -> email via Mailpit.
#
# Idempotent. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

COMPOSE=(docker compose -f docker-compose.yml)
MODEL="qwen2.5:7b"

log() { printf '\033[1;36m[ex06]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[ex06]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[ex06]\033[0m %s\n' "$*" >&2; exit 1; }

log "Checking prerequisites..."
command -v docker >/dev/null 2>&1 || die "docker is required."
docker compose version >/dev/null 2>&1 || die "docker compose v2 is required (try: docker compose version)."
command -v curl >/dev/null 2>&1 || die "curl is required."
ok "Prerequisites OK."

if [[ ! -f .env ]]; then
  log "Creating .env from .env.example..."
  cp .env.example .env
fi

mkdir -p data/ollama
chmod -R u+rwX data

log "Starting ollama + mailpit..."
"${COMPOSE[@]}" up -d ollama mailpit

log "Waiting for ollama to be healthy (<=2 min)..."
state=""
for i in $(seq 1 24); do
  state=$(docker inspect -f '{{.State.Health.Status}}' glean-ex06-ollama 2>/dev/null || echo "starting")
  [[ "${state}" == "healthy" ]] && break
  sleep 5
done
[[ "${state}" == "healthy" ]] || die "ollama did not become healthy. Check: ${COMPOSE[*]} logs ollama"

if "${COMPOSE[@]}" exec -T ollama ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -q "^${MODEL}$"; then
  ok "Model ${MODEL} already present."
else
  log "Pulling ${MODEL} (~5 GB - first time only)..."
  "${COMPOSE[@]}" exec -T ollama ollama pull "${MODEL}"
  ok "Model ${MODEL} pulled."
fi

log "Starting glean..."
"${COMPOSE[@]}" up -d glean

log "Waiting for glean healthz (<=60 s)..."
healthy=0
for i in $(seq 1 12); do
  if curl -sf http://127.0.0.1:9096/healthz >/dev/null 2>&1; then
    healthy=1
    ok "glean is healthy."
    break
  fi
  sleep 5
done
[[ "${healthy}" -eq 1 ]] || die "glean did not become healthy. Check: ${COMPOSE[*]} logs glean"

log "Dry-running the 'weekly-digest' feed..."
if ! "${COMPOSE[@]}" exec -T glean glean test-feed weekly-digest; then
  printf '\033[1;33m[ex06]\033[0m %s\n' "Dry-run failed. The stack is still up; inspect logs with: ${COMPOSE[*]} logs glean"
fi

cat <<'EOF'

✅ Example 06 is up.

View caught emails in Mailpit:
  open http://127.0.0.1:8025

Force send a digest now:
  docker compose -f docker-compose.yml exec glean glean send-now weekly-digest

Browse digests in the dashboard:
  open http://127.0.0.1:9096/

The feed ticks every Monday at 09:00 UTC.
EOF
