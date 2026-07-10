#!/bin/bash
set -euo pipefail

# Docker CLI and compose need a writable HOME for config; compose sets HOME to
# <repo>/.docker-home (gitignored). working_dir is set by compose to HOST_REPO.
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-qa-ai-models}"

_setup_home() {
  local repo="${HOST_REPO:-}"
  local uid="${HOST_UID:-1000}"
  if [ -n "$repo" ]; then
    local repo_home="${repo}/.docker-home/${uid}"
    if mkdir -p "$repo_home" 2>/dev/null; then
      export HOME="$repo_home"
      return 0
    fi
    echo "warning: cannot write ${repo_home} — using /tmp for Docker CLI HOME" >&2
  fi
  export HOME="/tmp/.docker-home-${uid}"
  mkdir -p "$HOME"
}
_setup_home

# Bind-mounted repos never include frontend/static/dist (gitignored). After a git
# pull or fresh clone the UI needs the Vite bundle; seed from the image bake
# (/opt/frontend-dist) before attempting an npm rebuild on the host mount.
if [ -n "${HOST_REPO:-}" ]; then
  DIST="${HOST_REPO}/frontend/static/dist"
  MANIFEST="${DIST}/.vite/manifest.json"
  if [ ! -f "$MANIFEST" ]; then
    if [ -f /opt/frontend-dist/.vite/manifest.json ]; then
      echo "Seeding frontend static dist from image (bind mount has no Vite build)..."
      mkdir -p "$DIST"
      cp -a /opt/frontend-dist/. "$DIST/"
    elif [ -d "${HOST_REPO}/frontend/assets" ] && command -v npm >/dev/null 2>&1; then
      echo "Building frontend assets (no image seed, running npm run build)..."
      (cd "${HOST_REPO}/frontend/assets" && { [ -d node_modules ] || npm ci; } && npm run build) \
        || echo "warning: frontend asset build failed — UI may lack styles" >&2
    else
      echo "warning: no frontend dist and cannot build — UI will lack styles" >&2
    fi
  fi
fi

exec "$@"
