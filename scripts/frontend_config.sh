#!/bin/sh
# Writes the backend's address into frontend/js/config.js for a host that serves the page apart from
# the backend (Netlify):  ARIVAZHAI_API_URL=https://<hf-username>-arivazhai-api.hf.space sh scripts/frontend_config.sh
set -eu
CONFIG="$(cd "$(dirname "$0")/.." && pwd)/frontend/js/config.js"
URL="${ARIVAZHAI_API_URL:-}"
case "$URL" in
  ""|https://*|http://localhost*|http://127.0.0.1*) ;;
  *) echo "ARIVAZHAI_API_URL must start with https:// (got: $URL)" >&2; exit 1 ;;
esac
case "$URL" in *\"*|*\\*) echo "ARIVAZHAI_API_URL must not contain quotes or backslashes" >&2; exit 1 ;; esac
URL="${URL%/}"
sed -i.bak "s|^  apiBaseUrl: \".*\",|  apiBaseUrl: \"$URL\",|" "$CONFIG" && rm -f "$CONFIG.bak"
grep -q "apiBaseUrl: \"$URL\"," "$CONFIG" || { echo "could not set apiBaseUrl in $CONFIG" >&2; exit 1; }
echo "js/config.js: apiBaseUrl = \"$URL\""
