#!/usr/bin/env bash
# Tear down example 01: containers, volumes, local data/, and .env.
# The example directory itself is preserved so you can re-run setup.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "[ex01] Stopping containers + removing volumes..."
docker compose -f docker-compose.yml down -v --remove-orphans || true

echo "[ex01] Removing local data/ and .env..."
rm -rf data .env

if [ -f feeds.yaml.bak ]; then
  echo "[ex01] Restoring feeds.yaml from .bak"
  mv feeds.yaml.bak feeds.yaml
fi

echo "[ex01] Done. Re-run ./setup.sh to start fresh."