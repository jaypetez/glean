#!/usr/bin/env bash
# Example 01 setup — fully self-contained glean stack:
#   glean + ollama (qwen2.5:7b) + searxng → file + dashboard sinks.
#
# Idempotent. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

MODEL="qwen2.5:7b"
COMPOSE="docker compose -f docker-compose.yml"

log() { printf '\033[1;36m[ex01]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[ex01]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[ex01]\033[0m %s\n' "$*" >&2; exit 1; }

# -- 1. Prerequisites ---------------------------------------------------------

log "Checking prerequisites…"
command -v docker  >/dev/null 2>&1 || die "docker is required."
docker compose version >/dev/null 2>&1 || die "docker compose v2 is required (try: docker compose version)."
command -v openssl >/dev/null 2>&1 || die "openssl is required (for generating SEARXNG_SECRET)."
command -v curl    >/dev/null 2>&1 || die "curl is required."
ok "Prerequisites OK."

# -- 2. .env ------------------------------------------------------------------

if [[ ! -f .env ]]; then
  log "Creating .env from .env.example…"
  cp .env.example .env
fi

if ! grep -Eq '^SEARXNG_SECRET=[0-9a-fA-F]{32,}' .env; then
  log "Generating SEARXNG_SECRET (32 bytes)…"
  SECRET="$(openssl rand -hex 32)"
  # portable in-place edit (avoids macOS sed -i quirks)
  tmp=$(mktemp)
  awk -v s="${SECRET}" '/^SEARXNG_SECRET=/ {print "SEARXNG_SECRET=" s; next} {print}' .env > "${tmp}"
  mv "${tmp}" .env
  ok "SEARXNG_SECRET set."
else
  ok "SEARXNG_SECRET already present."
fi

# -- 3. data/ directory -------------------------------------------------------

mkdir -p data/digests data/ollama
chmod -R u+rwX data

# -- 4. Bring up ollama + searxng first, wait for healthy ---------------------

log "Starting ollama + searxng…"
${COMPOSE} up -d ollama searxng

log "Waiting for ollama to be healthy (≤2 min)…"
for i in $(seq 1 24); do
  state=$(docker inspect -f '{{.State.Health.Status}}' glean-ex01-ollama 2>/dev/null || echo "starting")
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
  if curl -sf http://127.0.0.1:9091/healthz >/dev/null 2>&1; then
    ok "glean is healthy."
    break
  fi
  sleep 5
done

# -- 7. Dry-run the feed so the user sees output immediately ------------------

log "Dry-running the 'web-search' feed (no items will be sent — first tick is bootstrap)…"
${COMPOSE} exec -T glean glean test-feed web-search || true

cat <<'EOF'

──────────────────────────────────────────────────────────────────────────────
 ✅ Example 01 is up.

 Force one digest right now (writes to ./data/digests/web-search.md):
   docker compose -f docker-compose.yml exec glean glean send-now web-search

 Tail the logs:
   docker compose -f docker-compose.yml logs -f glean

 Browse digests in the browser:
   open http://127.0.0.1:9091/  # (Linux: xdg-open; Windows: Start-Process)
   # Get the API key from: docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY

 The feed will tick every hour on its own from now on.

 Tear it all down:
   ./teardown.sh
──────────────────────────────────────────────────────────────────────────────
EOF
