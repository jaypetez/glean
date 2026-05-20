#!/usr/bin/env bash
# Tear down example 06: containers, volumes, local data/, and .env.
# The example directory itself is preserved so you can re-run setup.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "[ex06] Stopping containers + removing volumes..."
docker compose -f docker-compose.yml down -v --remove-orphans || true

echo "[ex06] Removing local data/ and .env..."
rm -rf data .env

echo "[ex06] Done. Re-run ./setup.sh to start fresh."
