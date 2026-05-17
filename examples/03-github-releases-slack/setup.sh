#!/usr/bin/env bash
# Example 03 setup — GitHub releases -> Slack + dashboard.
#
# Idempotent. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

COMPOSE="docker compose -f docker-compose.yml"

log() { printf '\033[1;36m[ex03]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[ex03]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[ex03]\033[0m %s\n' "$*" >&2; exit 1; }

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

SLACK_WEBHOOK_URL="$(grep -E '^SLACK_WEBHOOK_URL=' .env | head -1 | cut -d= -f2- | tr -d '\r')"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL#\"}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL%\"}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL#\'}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL%\'}"
if [[ -z "${SLACK_WEBHOOK_URL}" ]]; then
  die "SLACK_WEBHOOK_URL is blank in .env. Add your Slack webhook URL, then re-run setup.sh."
fi

if [[ "${SLACK_WEBHOOK_URL}" != https://hooks.slack.com/services/* ]]; then
  die "SLACK_WEBHOOK_URL must start with https://hooks.slack.com/services/"
fi

ok "Slack webhook URL looks valid."

# -- 3. data/ directory -------------------------------------------------------

mkdir -p data
chmod -R u+rwX data

# -- 4. Start glean -----------------------------------------------------------

log "Starting glean (no Ollama container needed for this example)…"
${COMPOSE} up -d glean

log "Waiting for glean healthz (≤60 s)…"
healthy=0
for i in $(seq 1 12); do
  if curl -sf http://127.0.0.1:9093/healthz >/dev/null 2>&1; then
    healthy=1
    ok "glean is healthy."
    break
  fi
  sleep 5
done

if [[ "${healthy}" -ne 1 ]]; then
  die "glean did not become healthy. Check: ${COMPOSE} logs glean"
fi

# -- 5. Dry-run the feed ------------------------------------------------------

log "Dry-running the 'github-releases' feed…"
if ! ${COMPOSE} exec -T glean glean test-feed github-releases; then
  log "Dry-run hit a transient fetch error. The stack is still up; re-run setup.sh or try again later."
fi

cat <<'EOF'

──────────────────────────────────────────────────────────────────────────────
 ✅ Example 03 is up.

 Browse recent digests in the dashboard:
   open http://127.0.0.1:9093/   # (Linux: xdg-open; Windows: Start-Process)
   # Get the API key from: docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY

 Tail the logs:
   docker compose -f docker-compose.yml logs -f glean

 Customize the repo list:
   edit feeds.yaml to add/remove GitHub repos ending in /releases.atom

 Note: bootstrap is skip-and-mark, so the dashboard stays empty until one of
 the tracked repos publishes a new release after setup.

 The feed will check for new releases every 6 hours and post them to Slack.

 Tear it all down:
   ./teardown.sh
──────────────────────────────────────────────────────────────────────────────
EOF
