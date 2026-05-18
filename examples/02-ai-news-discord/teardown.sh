#!/usr/bin/env bash
# Tear down example 02: containers, volumes, local data/, and .env.
# The example directory itself is preserved so you can re-run setup.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "[ex02] Stopping containers + removing volumes…"
docker compose -f docker-compose.yml down -v --remove-orphans || true

echo "[ex02] Restoring feeds.yaml from feeds.yaml.bak (if present)…"
if [[ -f feeds.yaml.bak ]]; then
  mv -f feeds.yaml.bak feeds.yaml
fi

echo "[ex02] Removing local data/ and .env…"
rm -rf data .env

echo "[ex02] Done. Re-run ./setup.sh to start fresh."
