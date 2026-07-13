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

# Frontend assets are resolved by frontend/vite_assets.py, which prefers the
# working-tree build (frontend/static/dist, rebuilt by run.sh in dev) and falls
# back to the image bake (/opt/frontend-dist, always present in this image).
# The entrypoint deliberately does NOT copy between the two: an earlier
# "seed the bind mount from the image" step went stale (a bind mount seeded by
# an old image was never refreshed) and could shadow a fresh host build. On the
# VM, deploy-remote.sh removes the working-tree dist so the fresh image bake is
# always served; in dev, run.sh builds the working-tree dist before start.

exec "$@"
