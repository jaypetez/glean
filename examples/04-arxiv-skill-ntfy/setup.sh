#!/usr/bin/env bash
# Example 04 setup — arXiv cs.AI + cs.LG → skill extraction → ntfy + JSONL + dashboard.
#
# Idempotent. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

MODEL="qwen2.5:7b"
COMPOSE=(docker compose -f docker-compose.yml)

log() { printf '\033[1;36m[ex04]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[ex04]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[ex04]\033[0m %s\n' "$*" >&2; exit 1; }

log "Checking prerequisites…"
command -v docker >/dev/null 2>&1 || die "docker is required."
docker compose version >/dev/null 2>&1 || die "docker compose v2 is required (try: docker compose version)."
command -v curl >/dev/null 2>&1 || die "curl is required."
ok "Prerequisites OK."

if [[ ! -f .env ]]; then
  log "Creating .env from .env.example…"
  cp .env.example .env
fi

NTFY_TOPIC="$(grep -E '^NTFY_TOPIC=' .env | head -1 | cut -d= -f2- | tr -d '\r')"
if [[ -z "${NTFY_TOPIC}" || "${NTFY_TOPIC}" == "glean-arxiv-CHANGE-ME" ]]; then
  die $'Set a private ntfy topic in .env before starting.\n# In .env, set: NTFY_TOPIC=glean-arxiv-$(openssl rand -hex 6)'
fi
if [[ ! "${NTFY_TOPIC}" =~ ^[A-Za-z0-9_-]{1,64}$ ]]; then
  die "NTFY_TOPIC must be 1-64 characters using only letters, digits, '_' or '-'."
fi

mkdir -p data/digests data/ollama
chmod -R u+rwX data

log "Starting ollama…"
"${COMPOSE[@]}" up -d ollama

log "Waiting for ollama to be healthy (≤2 min)…"
state=""
for _ in $(seq 1 24); do
  state=$(docker inspect -f '{{.State.Health.Status}}' glean-ex04-ollama 2>/dev/null || echo "starting")
  [[ "${state}" == "healthy" ]] && break
  sleep 5
done
[[ "${state}" == "healthy" ]] || die "ollama did not become healthy. Check: docker compose -f docker-compose.yml logs ollama"

if "${COMPOSE[@]}" exec -T ollama ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -q "^${MODEL}$"; then
  ok "Model ${MODEL} already present."
else
  log "Pulling ${MODEL} (~5 GB — first time only)…"
  "${COMPOSE[@]}" exec -T ollama ollama pull "${MODEL}"
  ok "Model ${MODEL} pulled."
fi

log "Starting glean…"
"${COMPOSE[@]}" up -d glean

log "Waiting for glean healthz (≤60 s)…"
healthy="false"
for _ in $(seq 1 12); do
  if curl -sf http://127.0.0.1:9094/healthz >/dev/null 2>&1; then
    healthy="true"
    ok "glean is healthy."
    break
  fi
  sleep 5
done
[[ "${healthy}" == "true" ]] || die "glean did not become healthy. Check: docker compose -f docker-compose.yml logs glean"

log "Dry-running the 'arxiv-papers' feed…"
"${COMPOSE[@]}" exec -T glean glean test-feed arxiv-papers

cat <<EOF

──────────────────────────────────────────────────────────────────────────────
 ✅ Example 04 is up.

 Browser viewer URL:
   http://127.0.0.1:9094/
   # Get the API key from: docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY

 JSONL archive:
   ${SCRIPT_DIR}/data/digests/arxiv-papers.jsonl

 Subscribe on your phone:
   https://ntfy.sh/${NTFY_TOPIC}
   # Or install the ntfy mobile app and subscribe to topic: ${NTFY_TOPIC}

 Tear it all down:
   ./teardown.sh
──────────────────────────────────────────────────────────────────────────────
EOF
