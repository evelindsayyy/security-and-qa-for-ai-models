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

# shellcheck source=docker/host-env.sh
source docker/host-env.sh

printf '%s' "$CI_JOB_TOKEN" | docker login -u gitlab-ci-token --password-stdin "$CI_REGISTRY"

if [ "${BUILD_PILLARS:-0}" = "1" ]; then
  ./docker/build-pillars.sh
fi

docker compose --project-name qa-ai-models --env-file .env \
  -f docker/compose.yml -f docker/compose.deploy.yml pull web

# Recreate the web container so Flask reloads bind-mounted code and refreshes
# HOST_UID / DOCKER_GID from host-env.sh (git pull alone does not restart the process).
docker compose --project-name qa-ai-models --env-file .env \
  -f docker/compose.yml -f docker/compose.deploy.yml \
  up -d --force-recreate --no-build --pull missing --no-deps web

echo "Deployed ${WEB_IMAGE} at ${DEPLOY_PATH} ($(git rev-parse --short HEAD))"
