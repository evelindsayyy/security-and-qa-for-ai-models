#!/usr/bin/env bash
# Launch the containerized UI on any host with Docker.
#
# Auto-detects the values that differ per machine so they never live in .env:
#   HOST_UID / HOST_GID  - run as you, so output files are not root-owned
#   DOCKER_GID           - group of /var/run/docker.sock, for browser launches
#   HOST_REPO            - the repo is mounted at the SAME absolute path inside
#                          the container as outside, so pillar jobs spawned via
#                          the Docker socket resolve their bind mounts correctly
#
#   ./docker/run.sh up --build         # start (foreground; Ctrl+C stops)
#   ./docker/run.sh up -d --build      # start (background / detached)
#   ./docker/run.sh restart            # stop + rebuild + recreate (pick up code)
#   ./docker/run.sh restart-deploy     # production: pull CI web image + recreate (WEB_IMAGE set)
#   ./docker/run.sh down               # stop
#   ./docker/run.sh logs -f web        # follow logs (works for detached too)
#
# Production HTTPS: set CADDY_DOMAIN in .env — run.sh auto-includes compose.caddy.yml
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=docker/host-env.sh
source docker/host-env.sh

if [ -d frontend/assets ] && command -v npm >/dev/null 2>&1; then
  bash scripts/build-frontend.sh || echo "warning: frontend asset build failed" >&2
fi

ENV_ARGS=()
[ -f .env ] && ENV_ARGS=(--env-file .env)

COMPOSE_FILES=(-f docker/compose.yml)
if [ -f .env ] && grep -qE '^CADDY_DOMAIN=.+' .env 2>/dev/null; then
  COMPOSE_FILES+=(-f docker/compose.caddy.yml)
fi

compose() {
  docker compose --project-name qa-ai-models "${ENV_ARGS[@]}" \
    "${COMPOSE_FILES[@]}" "$@"
}

_deploy_compose_files() {
  COMPOSE_FILES=(-f docker/compose.yml -f docker/compose.deploy.yml)
  if [ -f .env ] && grep -qE '^CADDY_DOMAIN=.+' .env 2>/dev/null; then
    COMPOSE_FILES+=(-f docker/compose.caddy.yml)
  fi
}

_deploy_services() {
  SERVICES=(web)
  if [ -f .env ] && grep -qE '^CADDY_DOMAIN=.+' .env 2>/dev/null; then
    SERVICES+=(caddy)
  fi
  printf '%s\n' "${SERVICES[@]}"
}

# GitLab deploy on the VM — same as `uv run python main.py restart-deploy` when WEB_IMAGE is set.
if [ "${1:-}" = "restart-deploy" ]; then
  shift || true
  WEB_IMAGE="${WEB_IMAGE:?WEB_IMAGE required for restart-deploy}"
  _deploy_compose_files
  mapfile -t SERVICES < <(_deploy_services)

  APP_PORT="$(grep -E '^APP_PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2- || true)"
  APP_PORT="${APP_PORT:-5000}"
  if ss -ltn 2>/dev/null | grep -q ":${APP_PORT} "; then
    if ! docker compose --project-name qa-ai-models --env-file .env \
      "${COMPOSE_FILES[@]}" ps --status running --format '{{.Name}}' 2>/dev/null \
      | grep -q 'qa-ai-models-web'; then
      echo "Port ${APP_PORT} is in use by a non-qa-ai-models process — free it before deploy" >&2
      ss -ltnp 2>/dev/null | grep ":${APP_PORT} " || true
      exit 1
    fi
  fi

  echo "Pulling ${WEB_IMAGE}…"
  compose pull web

  echo "Recreating qa-ai-models (production image)…"
  compose stop "${SERVICES[@]}" 2>/dev/null || true
  compose rm -f "${SERVICES[@]}" 2>/dev/null || true

  _compose_up() {
    compose up -d --force-recreate --no-build --pull always --no-deps --remove-orphans \
      --wait --wait-timeout 90 "${SERVICES[@]}"
  }

  if ! _compose_up; then
    echo "compose up failed — clearing stale qa-ai-models containers and retrying" >&2
    docker ps -aq --filter "name=qa-ai-models-" | xargs -r docker rm -f
    _compose_up
  fi

  echo "Production stack restarted (${WEB_IMAGE})."
  exit 0
fi

# Full recreate so bind-mounted Python/templates are reloaded and the image
# is rebuilt. Prefer this after git pull instead of hunting for a VS Code port.
if [ "${1:-}" = "restart" ]; then
  shift || true
  echo "Stopping qa-ai-models…"
  compose down --remove-orphans || true
  echo "Rebuilding and starting (detached)…"
  compose up -d --build --force-recreate --remove-orphans "$@"
  echo "UI recreating. Follow logs with: ./docker/run.sh logs -f web"
  echo "Stop with: ./docker/run.sh down"
  exit 0
fi

exec docker compose --project-name qa-ai-models "${ENV_ARGS[@]}" \
  "${COMPOSE_FILES[@]}" "$@"
