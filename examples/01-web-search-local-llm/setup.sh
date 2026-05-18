#!/usr/bin/env bash
# Example 01 setup - fully self-contained glean stack:
#   glean + ollama (qwen2.5:7b) + searxng -> file + dashboard sinks.
#
# Idempotent. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

MODEL="qwen2.5:7b"

log()  { printf '\033[1;36m[ex01]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ex01]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[ex01]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[ex01]\033[0m %s\n' "$*" >&2; exit 1; }

external_ollama_available() {
  local url
  for url in http://host.docker.internal:11434/api/tags http://127.0.0.1:11434/api/tags; do
    if curl -sf -m 2 "$url" 2>/dev/null | grep -q '"models"'; then
      return 0
    fi
  done
  return 1
}

docker_has_nvidia_runtime() {
  docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'
}

detect_gpu_mode() {
  if [ -n "${GLEAN_OLLAMA_GPU:-}" ]; then
    case "$GLEAN_OLLAMA_GPU" in
      none|nvidia|rocm|external) echo "$GLEAN_OLLAMA_GPU"; return ;;
      *) die "Invalid GLEAN_OLLAMA_GPU=$GLEAN_OLLAMA_GPU (must be none|nvidia|rocm|external)" ;;
    esac
  fi
  if external_ollama_available; then
    echo "external"; return
  fi
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1 && docker_has_nvidia_runtime; then
    echo "nvidia"; return
  fi
  if command -v rocm-smi >/dev/null 2>&1 && [ -e /dev/kfd ]; then
    echo "rocm"; return
  fi
  echo "none"
}

patch_feeds_yaml_for_external_ollama() {
  if grep -q "base_url: http://host.docker.internal:11434" feeds.yaml; then
    return  # already patched
  fi
  log "Patching feeds.yaml: ollama base_url -> host.docker.internal (external mode)"
  cp feeds.yaml feeds.yaml.bak
  sed -i.tmp 's|base_url: http://ollama:11434|base_url: http://host.docker.internal:11434|g' feeds.yaml
  rm -f feeds.yaml.tmp
}

restore_feeds_yaml_from_backup() {
  if [ -f feeds.yaml.bak ]; then
    log "Restoring feeds.yaml from .bak"
    mv feeds.yaml.bak feeds.yaml
  fi
}

# -- 1. Prerequisites ---------------------------------------------------------

log "Checking prerequisites..."
command -v docker  >/dev/null 2>&1 || die "docker is required."
docker compose version >/dev/null 2>&1 || die "docker compose v2 is required (try: docker compose version)."
command -v openssl >/dev/null 2>&1 || die "openssl is required (for generating SEARXNG_SECRET)."
command -v curl    >/dev/null 2>&1 || die "curl is required."
ok "Prerequisites OK."

# -- 2. .env ------------------------------------------------------------------

if [[ ! -f .env ]]; then
  log "Creating .env from .env.example..."
  cp .env.example .env
fi

if ! grep -Eq '^SEARXNG_SECRET=[0-9a-fA-F]{32,}' .env; then
  log "Generating SEARXNG_SECRET (32 bytes)..."
  SECRET="$(openssl rand -hex 32)"
  tmp=".env.tmp"
  awk -v s="${SECRET}" '/^SEARXNG_SECRET=/ {print "SEARXNG_SECRET=" s; next} {print}' .env > "${tmp}"
  mv "${tmp}" .env
  ok "SEARXNG_SECRET set."
else
  ok "SEARXNG_SECRET already present."
fi

if [[ -z "${GLEAN_OLLAMA_GPU:-}" ]] && [[ -f .env ]]; then
  GLEAN_OLLAMA_GPU="$(awk -F= '/^GLEAN_OLLAMA_GPU=/{print $2}' .env | tail -n 1 | tr -d '\r')"
  export GLEAN_OLLAMA_GPU
fi

MODE=$(detect_gpu_mode)
log "GPU mode: ${MODE} (override with GLEAN_OLLAMA_GPU=none|nvidia|rocm|external in .env)"
if [ "${MODE}" != "external" ] && [ -f feeds.yaml.bak ]; then
  restore_feeds_yaml_from_backup
fi

COMPOSE_FILE_ARGS=("-f" "docker-compose.yml")
case "$MODE" in
  nvidia)   COMPOSE_FILE_ARGS+=("-f" "docker-compose.nvidia.yml") ;;
  rocm)     COMPOSE_FILE_ARGS+=("-f" "docker-compose.rocm.yml") ;;
  external) COMPOSE_FILE_ARGS+=("-f" "docker-compose.external-ollama.yml")
            patch_feeds_yaml_for_external_ollama ;;
esac
COMPOSE=(docker compose "${COMPOSE_FILE_ARGS[@]}")
COMPOSE_DISPLAY="${COMPOSE[*]}"

# -- 3. data/ directory -------------------------------------------------------

mkdir -p data/digests data/ollama
chmod -R u+rwX data

# -- 4. Bring up ollama + searxng first, wait for healthy ---------------------

log "Starting ollama + searxng..."
if ! "${COMPOSE[@]}" up -d ollama searxng; then
  if [ "$MODE" = "nvidia" ]; then
    warn "NVIDIA mode could not start the ollama container."
    warn "Install nvidia-container-toolkit, then: sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker"
    warn "Or set GLEAN_OLLAMA_GPU=none in .env to force CPU mode."
  elif [ "$MODE" = "rocm" ]; then
    warn "ROCm mode could not start the ollama container."
    warn "See https://github.com/ollama/ollama/blob/main/docs/gpu.md#amd-radeon for ROCm setup."
    warn "Or set GLEAN_OLLAMA_GPU=none in .env to force CPU mode."
  fi
  die "compose up failed for ollama/searxng."
fi

log "Waiting for ollama to be healthy (<=2 min)..."
for i in $(seq 1 24); do
  state=$(docker inspect -f '{{.State.Health.Status}}' glean-ex01-ollama 2>/dev/null || echo "starting")
  [[ "${state}" == "healthy" ]] && break
  sleep 5
done
[[ "${state:-}" == "healthy" ]] || die "ollama did not become healthy. Check: ${COMPOSE_DISPLAY} logs ollama"

if [ "$MODE" = "nvidia" ]; then
  if "${COMPOSE[@]}" exec -T ollama nvidia-smi >/dev/null 2>&1; then
    ok "ollama container can see the GPU"
  else
    warn "ollama container could NOT see the GPU."
    warn "Install nvidia-container-toolkit, then: sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker"
    warn "Or set GLEAN_OLLAMA_GPU=none in .env to force CPU mode."
  fi
elif [ "$MODE" = "rocm" ]; then
  if "${COMPOSE[@]}" exec -T ollama rocm-smi >/dev/null 2>&1; then
    ok "ollama container can see the AMD GPU"
  else
    warn "ollama container could NOT see the AMD GPU."
    warn "See https://github.com/ollama/ollama/blob/main/docs/gpu.md#amd-radeon for ROCm setup."
  fi
fi

# -- 5. Pull the LLM model ----------------------------------------------------

if [ "$MODE" = "external" ]; then
  log "External Ollama mode - skipping model pull (host Ollama is expected to have qwen2.5:7b)"
  log "If missing, pull on your host: ollama pull qwen2.5:7b"
elif "${COMPOSE[@]}" exec -T ollama ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -q "^${MODEL}$"; then
  ok "Model ${MODEL} already present."
else
  log "Pulling ${MODEL} (~5 GB - first time only)..."
  "${COMPOSE[@]}" exec -T ollama ollama pull "${MODEL}"
  ok "Model ${MODEL} pulled."
fi

# -- 6. Start glean -----------------------------------------------------------

log "Starting glean..."
"${COMPOSE[@]}" up -d glean

log "Waiting for glean healthz (<=60 s)..."
healthy=0
for i in $(seq 1 12); do
  if curl -sf http://127.0.0.1:9091/healthz >/dev/null 2>&1; then
    ok "glean is healthy."
    healthy=1
    break
  fi
  sleep 5
done
if [ "${healthy}" -ne 1 ]; then
  warn "glean healthz did not respond within 60 s. Continuing so you can inspect logs with: ${COMPOSE_DISPLAY} logs glean"
fi

# -- 7. Dry-run the feed so the user sees output immediately ------------------

log "Dry-running the 'web-search' feed (no items will be sent - first tick is bootstrap)..."
"${COMPOSE[@]}" exec -T glean glean test-feed web-search || true

cat <<EOF

------------------------------------------------------------------------------
 OK: Example 01 is up (Ollama mode: ${MODE}).

 Compose command for this run:
   ${COMPOSE_DISPLAY}

 Force one digest right now (writes to ./data/digests/web-search.md):
   ${COMPOSE_DISPLAY} exec glean glean send-now web-search

 Tail the logs:
   ${COMPOSE_DISPLAY} logs -f glean

 Browse digests in the browser:
   open http://127.0.0.1:9091/  # (Linux: xdg-open; Windows: Start-Process)
   # Get the API key from: ${COMPOSE_DISPLAY} logs glean | grep GLEAN_INITIAL_API_KEY

 The feed will tick every hour on its own from now on.

 Tear it all down:
   ./teardown.sh
------------------------------------------------------------------------------
EOF