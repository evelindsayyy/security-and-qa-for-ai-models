#!/bin/bash
set -euo pipefail

# Docker CLI and compose need a writable HOME for config; compose sets HOME to
# <repo>/.docker-home (gitignored). working_dir is set by compose to HOST_REPO.
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-qa-ai-models}"
mkdir -p "${HOME:-/tmp/.docker-home}" 2>/dev/null || true

# Rebuild Vite assets when bind-mounted repo lacks a dist manifest (dev / fresh git pull).
if [ -n "${HOST_REPO:-}" ] && [ -d "${HOST_REPO}/frontend/assets" ]; then
  MANIFEST="${HOST_REPO}/frontend/static/dist/.vite/manifest.json"
  if [ ! -f "$MANIFEST" ] && command -v npm >/dev/null 2>&1; then
    (cd "${HOST_REPO}/frontend/assets" && { [ -d node_modules ] || npm ci; } && npm run build) \
      || echo "warning: frontend asset build failed — UI may lack styles" >&2
  fi
fi

exec "$@"
