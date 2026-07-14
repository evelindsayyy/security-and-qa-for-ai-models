#!/usr/bin/env bash
# Build frontend Vite assets into frontend/static/dist/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS="${ROOT}/frontend/assets"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found — skipping frontend asset build" >&2
  exit 0
fi

cd "$ASSETS"
if [ ! -d node_modules ]; then
  npm ci
fi
npm run build
echo "Frontend assets built → frontend/static/dist/"
