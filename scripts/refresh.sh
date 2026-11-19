#!/usr/bin/env bash
# Monthly refresh of Arivazhai's knowledge base (Linux / macOS): crawl the official website again, index
# what changed, and email the admin (REPORT_EMAIL_TO in .env) what was updated. Output goes to data/logs.
#
# cron, the 1st of every month at 2 AM (crontab -e):
#   0 2 1 * * /path/to/RAG-Sys/scripts/refresh.sh
# With Docker Compose instead:
#   0 2 1 * * cd /path/to/RAG-Sys && docker compose run --rm backend python -m rag.cli refresh
# If the API server runs all the time, REFRESH_EVERY_DAYS=30 in .env does the same without cron.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON=python3
mkdir -p "$ROOT/data/logs"
cd "$ROOT/backend"
"$PYTHON" -m rag.cli refresh 2>&1 | tee "$ROOT/data/logs/refresh-$(date +%F).log"
exit "${PIPESTATUS[0]}"
