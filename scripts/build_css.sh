#!/bin/sh
# Builds frontend/css/tailwind.css (the page's only stylesheet) from frontend/css/tailwind.input.css and the
# Tailwind classes in frontend/index.html and frontend/js/*.js, with Tailwind's standalone program (no npm).
# The program is downloaded once into .tools/ (git-ignored).   sh scripts/build_css.sh [--watch]
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=4.1.14
TOOL="$ROOT/.tools/tailwindcss-$VERSION"
if [ ! -x "$TOOL" ]; then
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) NAME=tailwindcss-linux-x64 ;;
    Linux-aarch64) NAME=tailwindcss-linux-arm64 ;;
    Darwin-arm64) NAME=tailwindcss-macos-arm64 ;;
    Darwin-x86_64) NAME=tailwindcss-macos-x64 ;;
    *) echo "No Tailwind program for $(uname -s)-$(uname -m); on Windows run scripts\\build_css.cmd" >&2; exit 1 ;;
  esac
  mkdir -p "$ROOT/.tools"
  echo "Downloading Tailwind CSS v$VERSION ($NAME) ..."
  curl -fsSL -o "$TOOL" "https://github.com/tailwindlabs/tailwindcss/releases/download/v$VERSION/$NAME"
  chmod +x "$TOOL"
fi
cd "$ROOT/frontend"
exec "$TOOL" -i css/tailwind.input.css -o css/tailwind.css --minify "$@"
