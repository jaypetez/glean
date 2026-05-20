#!/usr/bin/env bash
# Example 02 setup — AI news via RSS + Ollama + Discord + dashboard.
#
# Idempotent. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

MODEL="qwen2.5:7b"
EMBED_MODEL="nomic-embed-text"

log()  { printf '\033[1;36m[ex02]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ex02]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[ex02]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[ex02]\033[0m %s\n' "$*" >&2; exit 1; }

detect_gpu_mode() {
  if [[ -n "${GLEAN_OLLAMA_GPU:-}" ]]; then
    case "${GLEAN_OLLAMA_GPU}" in
      none|nvidia|rocm|external) echo "${GLEAN_OLLAMA_GPU}"; return ;;
      *) die "Invalid GLEAN_OLLAMA_GPU=${GLEAN_OLLAMA_GPU} (must be none|nvidia|rocm|external)" ;;
    esac
  fi
  if curl -sf -m 2 http://host.docker.internal:11434/api/tags >/dev/null 2>&1 \
     || curl -sf -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "external"; return
  fi
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    echo "nvidia"; return
  fi
  if command -v rocm-smi >/dev/null 2>&1 && [[ -e /dev/kfd ]]; then
    echo "rocm"; return
  fi
  echo "none"
}

patch_feeds_yaml_for_external_ollama() {
  if grep -q "base_url: http://host.docker.internal:11434" feeds.yaml; then
    if [[ ! -f feeds.yaml.bak ]]; then
      warn "feeds.yaml already points to host.docker.internal and no feeds.yaml.bak exists; teardown will leave it as-is."
    fi
    return
  fi
  log "Patching feeds.yaml: ollama base_url -> host.docker.internal (external mode)"
  if [[ ! -f feeds.yaml.bak ]]; then
    cp feeds.yaml feeds.yaml.bak
  fi
  sed -i.tmp 's|base_url: http://ollama:11434|base_url: http://host.docker.internal:11434|g' feeds.yaml
  rm -f feeds.yaml.tmp
}

restore_feeds_yaml_if_needed() {
  if [[ -f feeds.yaml.bak ]]; then
    log "Restoring feeds.yaml: ollama base_url -> ollama container"
    mv -f feeds.yaml.bak feeds.yaml
  fi
}

check_external_ollama_from_glean() {
  local probe='import json, sys, urllib.request
with urllib.request.urlopen("http://host.docker.internal:11434/api/tags", timeout=5) as response:
    payload = json.load(response)
models = {entry.get("name") for entry in payload.get("models", [])}
missing = [model for model in sys.argv[1:] if model not in models]
sys.exit(0 if not missing else 1)
'
  if "${COMPOSE[@]}" exec -T glean python -c "${probe}" "${MODEL}" "${EMBED_MODEL}" >/dev/null 2>&1; then
    ok "glean container can reach host Ollama and found ${MODEL} + ${EMBED_MODEL}"
  else
    warn "glean container could NOT confirm host Ollama at host.docker.internal:11434 with ${MODEL} + ${EMBED_MODEL}. Ensure host Ollama is reachable from Docker and run: ollama pull ${MODEL} && ollama pull ${EMBED_MODEL}"
  fi
}

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
if [[ -z "${GLEAN_OLLAMA_GPU:-}" ]]; then
  GLEAN_OLLAMA_GPU="$(grep -E '^GLEAN_OLLAMA_GPU=' .env | head -1 | cut -d= -f2- | tr -d '\r' || true)"
fi

MODE="$(detect_gpu_mode)"
if [[ "${MODE}" != "external" ]]; then
  restore_feeds_yaml_if_needed
fi
log "GPU mode: ${MODE} (override with GLEAN_OLLAMA_GPU=none|nvidia|rocm|external in .env)"
COMPOSE_FILE_ARGS=("-f" "docker-compose.yml")
case "${MODE}" in
  nvidia)
    COMPOSE_FILE_ARGS+=("-f" "docker-compose.nvidia.yml")
    ;;
  rocm)
    COMPOSE_FILE_ARGS+=("-f" "docker-compose.rocm.yml")
    ;;
  external)
    COMPOSE_FILE_ARGS+=("-f" "docker-compose.external-ollama.yml")
    patch_feeds_yaml_for_external_ollama
    ;;
esac
COMPOSE=(docker compose "${COMPOSE_FILE_ARGS[@]}")
COMPOSE_TEXT="${COMPOSE[*]}"

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
"${COMPOSE[@]}" up -d ollama

log "Waiting for ollama to be healthy (≤2 min)…"
for i in $(seq 1 24); do
  state=$(docker inspect -f '{{.State.Health.Status}}' glean-ex02-ollama 2>/dev/null || echo "starting")
  [[ "${state}" == "healthy" ]] && break
  sleep 5
done
[[ "${state:-}" == "healthy" ]] || die "ollama did not become healthy. Check: ${COMPOSE_TEXT} logs ollama"

if [[ "${MODE}" == "nvidia" ]]; then
  if "${COMPOSE[@]}" exec -T ollama nvidia-smi >/dev/null 2>&1; then
    ok "ollama container can see the GPU"
  else
    warn "ollama container could NOT see the GPU. Install nvidia-container-toolkit + restart Docker, or set GLEAN_OLLAMA_GPU=none."
  fi
elif [[ "${MODE}" == "rocm" ]]; then
  if "${COMPOSE[@]}" exec -T ollama rocm-smi >/dev/null 2>&1; then
    ok "ollama container can see the AMD GPU"
  else
    warn "ollama container could NOT see the AMD GPU. See https://github.com/ollama/ollama/blob/main/docs/gpu.md#amd-radeon."
  fi
fi

# -- 5. Pull the LLM model ----------------------------------------------------

if [[ "${MODE}" == "external" ]]; then
  log "External Ollama mode - skipping model pull (host Ollama expected to have ${MODEL} + ${EMBED_MODEL})"
  log "If missing, pull on your host: ollama pull ${MODEL} && ollama pull ${EMBED_MODEL}"
elif "${COMPOSE[@]}" exec -T ollama ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -q "^${MODEL}$"; then
  ok "Model ${MODEL} already present."
else
  log "Pulling ${MODEL} (~5 GB — first time only)…"
  "${COMPOSE[@]}" exec -T ollama ollama pull "${MODEL}"
  ok "Model ${MODEL} pulled."
fi

if [[ "${MODE}" != "external" ]] && "${COMPOSE[@]}" exec -T ollama ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -q "^${EMBED_MODEL}$"; then
  ok "Model ${EMBED_MODEL} already present."
elif [[ "${MODE}" != "external" ]]; then
  log "Pulling ${EMBED_MODEL} (~270 MB — first time only)…"
  "${COMPOSE[@]}" exec -T ollama ollama pull "${EMBED_MODEL}"
  ok "Model ${EMBED_MODEL} pulled."
fi

# -- 6. Start glean -----------------------------------------------------------

log "Starting glean…"
"${COMPOSE[@]}" up -d glean

log "Waiting for glean healthz (≤60 s)…"
for i in $(seq 1 12); do
  if curl -sf http://127.0.0.1:9092/healthz >/dev/null 2>&1; then
    ok "glean is healthy."
    break
  fi
  sleep 5
done
curl -sf http://127.0.0.1:9092/healthz >/dev/null 2>&1 || die "glean did not become healthy. Check: ${COMPOSE_TEXT} logs glean"

if [[ "${MODE}" == "external" ]]; then
  check_external_ollama_from_glean
fi

# -- 7. Dry-run the feed ------------------------------------------------------

log "Dry-running the 'ai-news' feed…"
"${COMPOSE[@]}" exec -T glean glean test-feed ai-news

cat <<EOF

──────────────────────────────────────────────────────────────────────────────
 ✅ Example 02 is up.

 Browse recent digests in the browser:
   http://127.0.0.1:9092/

 Get the API key from logs:
   ${COMPOSE_TEXT} logs glean | grep GLEAN_INITIAL_API_KEY

 Force-send a digest right now:
   ${COMPOSE_TEXT} exec glean glean send-now ai-news

 Tear it all down:
   ./teardown.sh
──────────────────────────────────────────────────────────────────────────────
EOF
