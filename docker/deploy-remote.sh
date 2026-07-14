#!/usr/bin/env bash
# Run on the application VM (invoked by GitLab deploy-manual over SSH).
#
# Expects env: DEPLOY_PATH, WEB_IMAGE, CI_REGISTRY, CI_JOB_TOKEN
# Expects env: DEPLOY_PATH, WEB_IMAGE, CI_REGISTRY, CI_JOB_TOKEN
# Optional: GIT_REF (default main), BUILD_PILLARS=1 to rebuild pillar images after pull
# Optional: CI_SERVER_HOST, CI_PROJECT_PATH, CI_SERVER_PROTOCOL — HTTPS git sync via CI_JOB_TOKEN
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:?DEPLOY_PATH required}"
WEB_IMAGE="${WEB_IMAGE:?WEB_IMAGE required}"
CI_REGISTRY="${CI_REGISTRY:?CI_REGISTRY required}"
CI_JOB_TOKEN="${CI_JOB_TOKEN:?CI_JOB_TOKEN required}"
GIT_REF="${GIT_REF:-main}"

cd "$DEPLOY_PATH"
test -f .env || { echo "Missing .env in ${DEPLOY_PATH}" >&2; exit 1; }

# Repo is shared with the vcm account; group-writable objects avoid blocking vcm git pull.
umask 002

_git_origin_url() {
  if [[ -n "${CI_SERVER_HOST:-}" && -n "${CI_PROJECT_PATH:-}" ]]; then
    local proto="${CI_SERVER_PROTOCOL:-https}"
    printf '%s://gitlab-ci-token:%s@%s/%s.git' \
      "$proto" "$CI_JOB_TOKEN" "$CI_SERVER_HOST" "$CI_PROJECT_PATH"
    return 0
  fi
  git remote get-url origin
}

_sync_repo() {
  local ref="$1"
  local origin_url
  origin_url="$(_git_origin_url)"
  local attempt
  for attempt in 1 2 3; do
    if git fetch "$origin_url" "$ref" \
      && git checkout "$ref" \
      && git merge --ff-only "FETCH_HEAD"; then
      return 0
    fi
    echo "git sync attempt ${attempt}/3 failed; retrying..." >&2
    sleep $((attempt * 2))
  done
  echo "git sync failed after 3 attempts (origin: ${origin_url%%gitlab-ci-token:*}…)" >&2
  return 1
}

_sync_repo "$GIT_REF"

# The VM never builds frontend assets on the host; production serves the Vite
# bundle baked into the CI-built image (/opt/frontend-dist). frontend/static/dist
# is gitignored and must not exist here, or a stale leftover (e.g. from an older
# deploy) would shadow the fresh image bake and the UI would render with outdated
# styles. Remove it so vite_assets.py falls through to the image bake.
rm -rf "${DEPLOY_PATH}/frontend/static/dist"

# shellcheck source=docker/host-env.sh
source docker/host-env.sh

# Per-UID Docker CLI homes under .docker-home; group-writable so deploy user and
# interactive VM users (different UIDs) can each mkdir their own subdir.
mkdir -p "${DEPLOY_PATH}/.docker-home"
chmod 2775 "${DEPLOY_PATH}/.docker-home" 2>/dev/null || chmod 775 "${DEPLOY_PATH}/.docker-home" 2>/dev/null || true

printf '%s' "$CI_JOB_TOKEN" | docker login -u gitlab-ci-token --password-stdin "$CI_REGISTRY"

if [ "${BUILD_PILLARS:-0}" = "1" ]; then
  ./docker/build-pillars.sh
fi

COMPOSE_FILES=(-f docker/compose.yml -f docker/compose.deploy.yml)
if grep -qE '^CADDY_DOMAIN=.+' .env 2>/dev/null; then
  COMPOSE_FILES+=(-f docker/compose.caddy.yml)
fi

SERVICES=(web)
if grep -qE '^CADDY_DOMAIN=.+' .env 2>/dev/null; then
  SERVICES+=(caddy)
fi

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

docker compose --project-name qa-ai-models --env-file .env \
  "${COMPOSE_FILES[@]}" pull web

# Always tear down this project's web/caddy first so a half-finished prior
# deploy or a host-side `main.py` / run.sh session cannot leave a stale
# container serving old bind-mounted code on APP_PORT.
echo "Recreating qa-ai-models services for ${WEB_IMAGE}…"
docker compose --project-name qa-ai-models --env-file .env \
  "${COMPOSE_FILES[@]}" stop "${SERVICES[@]}" 2>/dev/null || true
docker compose --project-name qa-ai-models --env-file .env \
  "${COMPOSE_FILES[@]}" rm -f "${SERVICES[@]}" 2>/dev/null || true

# Recreate containers so Flask reloads bind-mounted code and refreshes
# HOST_UID / DOCKER_GID from host-env.sh (git pull alone does not restart the process).
#
# Self-heal a wedged deploy: a previous half-finished recreate can leave a
# renamed container squatting a compose name (observed: caddy), which fails the
# next `up` with a "container name already in use" conflict that --force-recreate
# cannot clear. On failure, drop this project's containers and retry once so the
# deploy recovers on its own instead of needing a manual `docker rm` on the VM.
_compose_up() {
  docker compose --project-name qa-ai-models --env-file .env \
    "${COMPOSE_FILES[@]}" \
    up -d --force-recreate --no-build --pull always --no-deps --remove-orphans \
    --wait --wait-timeout 90 "${SERVICES[@]}"
}

if ! _compose_up; then
  echo "compose up failed — clearing stale qa-ai-models containers and retrying" >&2
  docker ps -aq --filter "name=qa-ai-models-" | xargs -r docker rm -f
  _compose_up
fi

echo "Deployed ${WEB_IMAGE} at ${DEPLOY_PATH} ($(git rev-parse --short HEAD))"
