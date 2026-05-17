#!/usr/bin/env bash
# Example 02 setup — AI news via RSS + Ollama + Discord + dashboard.
#
# Idempotent. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

MODEL="qwen2.5:7b"
COMPOSE="docker compose -f docker-compose.yml"

log() { printf '\033[1;36m[ex02]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[ex02]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[ex02]\033[0m %s\n' "$*" >&2; exit 1; }

# -- 1. Prerequisites ---------------------------------------------------------

log "Checking prerequisites…"
command -v docker >/dev/null 2>&1 || die "docker is required."
docker compose version >/dev/null 2>&1 || die "docker compose v2 is required (try: docker compose version)."
command -v curl >/dev/null 2>&1 || die "curl is required."
ok "Prerequisites OK."

# -- 2. .env ------------------------------------------------------------------

if [[ ! -f .env ]]; then
  log "Creating .env from .env.example…"
  cp .env.example .env
fi

DISCORD_WEBHOOK_URL="$(grep -E '^DISCORD_WEBHOOK_URL=' .env | head -1 | cut -d= -f2- | tr -d '\r' || true)"

if [[ -z "${DISCORD_WEBHOOK_URL}" ]]; then
  die "Set DISCORD_WEBHOOK_URL in .env (Server Settings > Integrations > Webhooks > New Webhook)."
fi

case "${DISCORD_WEBHOOK_URL}" in
  https://discord.com/api/webhooks/*|https://discordapp.com/api/webhooks/*) ;;
  *) die "DISCORD_WEBHOOK_URL must start with https://discord.com/api/webhooks/ or https://discordapp.com/api/webhooks/." ;;
esac
ok "Discord webhook looks valid."

# -- 3. data/ directory -------------------------------------------------------

mkdir -p data/ollama
chmod -R u+rwX data

# -- 4. Bring up ollama first, wait for healthy -------------------------------

log "Starting ollama…"
${COMPOSE} up -d ollama

log "Waiting for ollama to be healthy (≤2 min)…"
for i in $(seq 1 24); do
  state=$(docker inspect -f '{{.State.Health.Status}}' glean-ex02-ollama 2>/dev/null || echo "starting")
  [[ "${state}" == "healthy" ]] && break
  sleep 5
done
[[ "${state:-}" == "healthy" ]] || die "ollama did not become healthy. Check: ${COMPOSE} logs ollama"

# -- 5. Pull the LLM model ----------------------------------------------------

if ${COMPOSE} exec -T ollama ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -q "^${MODEL}$"; then
  ok "Model ${MODEL} already present."
else
  log "Pulling ${MODEL} (~5 GB — first time only)…"
  ${COMPOSE} exec -T ollama ollama pull "${MODEL}"
  ok "Model ${MODEL} pulled."
fi

# -- 6. Start glean -----------------------------------------------------------

log "Starting glean…"
${COMPOSE} up -d glean

log "Waiting for glean healthz (≤60 s)…"
for i in $(seq 1 12); do
  if curl -sf http://127.0.0.1:9092/healthz >/dev/null 2>&1; then
    ok "glean is healthy."
    break
  fi
  sleep 5
done
curl -sf http://127.0.0.1:9092/healthz >/dev/null 2>&1 || die "glean did not become healthy. Check: ${COMPOSE} logs glean"

# -- 7. Dry-run the feed ------------------------------------------------------

log "Dry-running the 'ai-news' feed…"
${COMPOSE} exec -T glean glean test-feed ai-news

cat <<'EOF'

──────────────────────────────────────────────────────────────────────────────
 ✅ Example 02 is up.

 Browse recent digests in the browser:
   http://127.0.0.1:9092/

 Get the API key from logs:
   docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY

 Force-send a digest right now:
   docker compose -f docker-compose.yml exec glean glean send-now ai-news

 Tear it all down:
   ./teardown.sh
──────────────────────────────────────────────────────────────────────────────
EOF
