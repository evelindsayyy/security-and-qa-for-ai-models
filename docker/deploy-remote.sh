#!/usr/bin/env bash
# Run on the application VM (invoked by GitLab deploy job over SSH).
#
# Expects env: DEPLOY_PATH, CI_REGISTRY, CI_JOB_TOKEN
# Optional: GIT_REF (default main), BUILD_PILLARS=1 to rebuild pillar images after pull
# Optional: CI_SERVER_HOST, CI_PROJECT_PATH, CI_SERVER_PROTOCOL — HTTPS git sync via CI_JOB_TOKEN
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:?DEPLOY_PATH required}"
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

# Stale host dist must not shadow the image bake (vite_assets.py fallback).
rm -rf "${DEPLOY_PATH}/frontend/static/dist"

# shellcheck source=docker/host-env.sh
source docker/host-env.sh

mkdir -p "${DEPLOY_PATH}/.docker-home"
chmod 2775 "${DEPLOY_PATH}/.docker-home" 2>/dev/null || chmod 775 "${DEPLOY_PATH}/.docker-home" 2>/dev/null || true

printf '%s' "$CI_JOB_TOKEN" | docker login -u gitlab-ci-token --password-stdin "$CI_REGISTRY"

if [ "${BUILD_PILLARS:-0}" = "1" ]; then
  ./docker/build-pillars.sh
fi

./docker/run.sh restart

APP_PORT="${APP_PORT:-5000}"
echo "Waiting for web health on 127.0.0.1:${APP_PORT}…"
for attempt in $(seq 1 45); do
  if curl -sf "http://127.0.0.1:${APP_PORT}/api/health" >/dev/null; then
    echo "Web healthy after ${attempt} attempt(s)."
    break
  fi
  if [ "$attempt" -eq 45 ]; then
    echo "Web did not become healthy within 90s — check: ./docker/run.sh logs web" >&2
    exit 1
  fi
  sleep 2
done

echo "Deployed at ${DEPLOY_PATH} ($(git rev-parse --short HEAD))"
