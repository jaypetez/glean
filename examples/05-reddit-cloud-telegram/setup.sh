#!/usr/bin/env bash
# Example 05 setup — Reddit -> cloud LLM -> Telegram + dashboard.
#
# Idempotent. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

COMPOSE="docker compose -f docker-compose.yml"

log() { printf '\033[1;36m[ex05]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[ex05]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[ex05]\033[0m %s\n' "$*" >&2; exit 1; }

log "Checking prerequisites…"
command -v docker >/dev/null 2>&1 || die "docker is required."
docker compose version >/dev/null 2>&1 || die "docker compose v2 is required (try: docker compose version)."
command -v curl >/dev/null 2>&1 || die "curl is required."
ok "Prerequisites OK."

if [[ ! -f .env ]]; then
  log "Creating .env from .env.example…"
  cp .env.example .env
  die "Created .env from .env.example. Fill in your cloud LLM key and Telegram values, then re-run ./setup.sh."
fi

set -a
# shellcheck disable=SC1091
source ./.env
set +a

selected_provider="$(awk '/^[[:space:]]*provider:[[:space:]]*/ { print $2; exit }' feeds.yaml)"
selected_provider="${selected_provider:-openai}"

if [[ -z "${OPENAI_API_KEY:-}" && -z "${ANTHROPIC_API_KEY:-}" ]]; then
  die "Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env before starting."
fi

if [[ "${selected_provider}" == "openai" && -z "${OPENAI_API_KEY:-}" ]]; then
  die "feeds.yaml is configured for provider=openai. Set OPENAI_API_KEY or switch feeds.yaml to the Anthropic block in README.md."
fi

if [[ "${selected_provider}" == "anthropic" && -z "${ANTHROPIC_API_KEY:-}" ]]; then
  die "feeds.yaml is configured for provider=anthropic. Set ANTHROPIC_API_KEY or switch feeds.yaml back to OpenAI."
fi

[[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] || die "TELEGRAM_BOT_TOKEN is required."
[[ -n "${TELEGRAM_CHAT_ID:-}" ]] || die "TELEGRAM_CHAT_ID is required."
[[ -n "${TELEGRAM_OPS_CHAT_ID:-}" ]] || die "TELEGRAM_OPS_CHAT_ID is required."

printf '%s' "${TELEGRAM_BOT_TOKEN}" | grep -Eq '^[0-9]+:[A-Za-z0-9_-]+$' || \
  die "TELEGRAM_BOT_TOKEN must match ^[0-9]+:[A-Za-z0-9_-]+$."
printf '%s' "${TELEGRAM_CHAT_ID}" | grep -Eq '^-?[0-9]+$' || \
  die "TELEGRAM_CHAT_ID must be an integer (negative for groups)."
printf '%s' "${TELEGRAM_OPS_CHAT_ID}" | grep -Eq '^-?[0-9]+$' || \
  die "TELEGRAM_OPS_CHAT_ID must be an integer (negative for groups)."

mkdir -p data
chmod -R u+rwX data

log "Using cloud LLM provider: ${selected_provider}"
log "Starting glean…"
${COMPOSE} up -d glean

log "Waiting for glean healthz (≤60 s)…"
healthy=0
for i in $(seq 1 12); do
  if curl -sf http://127.0.0.1:9095/healthz >/dev/null 2>&1; then
    healthy=1
    ok "glean is healthy."
    break
  fi
  sleep 5
done
[[ "${healthy}" -eq 1 ]] || die "glean did not become healthy. Check: ${COMPOSE} logs glean"

log "Dry-running the 'reddit-ml' feed…"
${COMPOSE} exec -T glean glean test-feed reddit-ml

cat <<EOF

──────────────────────────────────────────────────────────────────────────────
 ✅ Example 05 is up.

 Browser UI:
   http://127.0.0.1:9095/
   # API key: docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY

 Telegram chat to watch:
   ${TELEGRAM_CHAT_ID}

 Tail the logs:
   docker compose -f docker-compose.yml logs -f glean

 Force one digest right now:
   docker compose -f docker-compose.yml exec glean glean send-now reddit-ml

 Cost note:
   This example uses a cloud LLM, so expect a small per-tick spend.
   No Ollama container, GPU, or 5 GB model pull is required.

 Tear it all down:
   ./teardown.sh
──────────────────────────────────────────────────────────────────────────────
EOF
