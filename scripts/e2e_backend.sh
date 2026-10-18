#!/usr/bin/env bash
# Start the API on the fictional demo dataset for end-to-end UI tests (no network, no API keys).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
export DATA_DIR="${DATA_DIR:-$ROOT/data/e2e}"
export EMBEDDING_PROVIDER=hashing LLM_PROVIDER=extractive RATE_LIMIT_PER_MINUTE=0 LOG_LEVEL=WARNING
export CORS_ORIGINS="${CORS_ORIGINS:-http://127.0.0.1:4173,http://localhost:4173}"
cd "$ROOT/backend"
if [ ! -f "$DATA_DIR/index/manifest.json" ]; then
  "$PYTHON" -m rag.cli demo
fi
exec "$PYTHON" -m uvicorn rag.api.app:app --host 127.0.0.1 --port "${API_PORT:-8765}"
