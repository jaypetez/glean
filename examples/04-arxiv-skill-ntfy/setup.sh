#!/usr/bin/env bash
# Example 04 setup — arXiv cs.AI + cs.LG → skill extraction → ntfy + JSONL + dashboard.
#
# Idempotent. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

MODEL="qwen2.5:7b"

log() { printf '\033[1;36m[ex04]\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m[ex04]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[ex04]\033[0m %s\n' "$*" >&2; exit 1; }

detect_gpu_mode() {
  if [ -n "${GLEAN_OLLAMA_GPU:-}" ]; then
    case "${GLEAN_OLLAMA_GPU}" in
      none|nvidia|rocm|external) echo "${GLEAN_OLLAMA_GPU}"; return ;;
      *) die "Invalid GLEAN_OLLAMA_GPU=${GLEAN_OLLAMA_GPU}" ;;
    esac
  fi
  if curl -sf -m 2 http://host.docker.internal:11434/api/tags >/dev/null 2>&1 \
     || curl -sf -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "external"; return
  fi
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    echo "nvidia"; return
  fi
  if command -v rocm-smi >/dev/null 2>&1 && [ -e /dev/kfd ]; then
    echo "rocm"; return
  fi
  echo "none"
}

patch_feeds_yaml_for_external_ollama() {
  if grep -q "base_url: http://host.docker.internal:11434" feeds.yaml; then
    return
  fi
  log "Patching feeds.yaml: ollama base_url -> host.docker.internal (external mode)"
  cp feeds.yaml feeds.yaml.bak
  sed -i.tmp 's|base_url: http://ollama:11434|base_url: http://host.docker.internal:11434|g' feeds.yaml
  rm -f feeds.yaml.tmp
}

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

ENV_GPU_MODE="$(grep -E '^GLEAN_OLLAMA_GPU=' .env | head -1 | cut -d= -f2- | tr -d '\r')"
if [[ -n "${ENV_GPU_MODE}" && -z "${GLEAN_OLLAMA_GPU:-}" ]]; then
  GLEAN_OLLAMA_GPU="${ENV_GPU_MODE}"
fi

MODE="$(detect_gpu_mode)"
log "GPU mode: ${MODE} (override via GLEAN_OLLAMA_GPU in .env)"
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
[[ "${state}" == "healthy" ]] || die "ollama did not become healthy. Check the compose logs for ollama."

case "${MODE}" in
  nvidia)
    log "Verifying NVIDIA GPU access inside ollama…"
    "${COMPOSE[@]}" exec -T ollama nvidia-smi >/dev/null 2>&1 || die "NVIDIA GPU not visible inside the ollama container."
    ok "NVIDIA GPU detected inside ollama."
    ;;
  rocm)
    log "Verifying ROCm GPU access inside ollama…"
    "${COMPOSE[@]}" exec -T ollama rocm-smi >/dev/null 2>&1 || die "ROCm GPU not visible inside the ollama container."
    ok "ROCm GPU detected inside ollama."
    ;;
esac

if [[ "${MODE}" == "external" ]]; then
  ok "Using external Ollama; skipping model pull."
else
  if "${COMPOSE[@]}" exec -T ollama ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -q "^${MODEL}$"; then
    ok "Model ${MODEL} already present."
  else
    log "Pulling ${MODEL} (~5 GB — first time only)…"
    "${COMPOSE[@]}" exec -T ollama ollama pull "${MODEL}"
    ok "Model ${MODEL} pulled."
  fi
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
[[ "${healthy}" == "true" ]] || die "glean did not become healthy. Check the compose logs for glean."

log "Dry-running the 'arxiv-papers' feed…"
"${COMPOSE[@]}" exec -T glean glean test-feed arxiv-papers

cat <<EOF

──────────────────────────────────────────────────────────────────────────────
 ✅ Example 04 is up.

 GPU mode:
   ${MODE}

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
