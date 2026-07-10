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
# pull or fresh clone the UI needs the Vite bundle. frontend/vite_assets.py
# already prefers /opt/frontend-dist (fresh for the running image) over the
# bind mount, so the app is correctly styled regardless of this step. But we
# still resync the bind mount unconditionally (not just "if missing") so that
# on-disk state — direct file inspection, `docker cp`, host tooling — matches
# what's actually served; a one-time seed would otherwise go stale the moment
# a later image build ships newer assets.
if [ -n "${HOST_REPO:-}" ]; then
  DIST="${HOST_REPO}/frontend/static/dist"
  if [ -f /opt/frontend-dist/.vite/manifest.json ]; then
    # Clean replace (not merge) so hashed assets from older builds don't pile
    # up on disk across deploys. Safe even if this fails partway: the app
    # reads /opt/frontend-dist directly and doesn't depend on this bind-mount
    # copy for correct serving.
    if rm -rf "$DIST" 2>/dev/null && mkdir -p "$DIST" 2>/dev/null && cp -a /opt/frontend-dist/. "$DIST/" 2>/dev/null; then
      echo "Synced frontend static dist from image bake ($DIST)."
    else
      echo "warning: cannot write ${DIST} — serving styles from image bake only" >&2
    fi
  elif [ ! -f "${DIST}/.vite/manifest.json" ]; then
    if [ -d "${HOST_REPO}/frontend/assets" ] && command -v npm >/dev/null 2>&1; then
      echo "Building frontend assets (no image seed, running npm run build)..."
      (cd "${HOST_REPO}/frontend/assets" && { [ -d node_modules ] || npm ci; } && npm run build) \
        || echo "warning: frontend asset build failed — UI may lack styles" >&2
    else
      echo "warning: no frontend dist and cannot build — UI will lack styles" >&2
    fi
  fi
fi

exec "$@"
