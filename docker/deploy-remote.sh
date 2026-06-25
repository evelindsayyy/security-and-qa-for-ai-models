#!/usr/bin/env bash
# Run on the application VM (invoked by GitLab deploy-manual over SSH).
#
# Expects env: DEPLOY_PATH, WEB_IMAGE, CI_REGISTRY, CI_JOB_TOKEN
# Optional: GIT_REF (default main), BUILD_PILLARS=1 to rebuild pillar images after pull
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:?DEPLOY_PATH required}"
WEB_IMAGE="${WEB_IMAGE:?WEB_IMAGE required}"
CI_REGISTRY="${CI_REGISTRY:?CI_REGISTRY required}"
CI_JOB_TOKEN="${CI_JOB_TOKEN:?CI_JOB_TOKEN required}"
GIT_REF="${GIT_REF:-main}"

cd "$DEPLOY_PATH"
test -f .env || { echo "Missing .env in ${DEPLOY_PATH}" >&2; exit 1; }

git fetch origin "$GIT_REF"
git checkout "$GIT_REF"
git pull --ff-only origin "$GIT_REF"

# shellcheck source=docker/host-env.sh
source docker/host-env.sh

printf '%s' "$CI_JOB_TOKEN" | docker login -u gitlab-ci-token --password-stdin "$CI_REGISTRY"

if [ "${BUILD_PILLARS:-0}" = "1" ]; then
  ./docker/build-pillars.sh
fi

docker compose --project-name qa-ai-models --env-file .env \
  -f docker/compose.yml -f docker/compose.deploy.yml pull web

docker compose --project-name qa-ai-models --env-file .env \
  -f docker/compose.yml -f docker/compose.deploy.yml up -d --no-build --pull missing web

echo "Verifying Docker access inside web container..."
docker compose --project-name qa-ai-models --env-file .env \
  -f docker/compose.yml -f docker/compose.deploy.yml exec -T web docker info >/dev/null

if [ "${BUILD_PILLARS:-0}" != "1" ]; then
  echo "Tip: run deploy with BUILD_PILLARS=1 once after pillar Dockerfiles change."
fi

echo "Deployed ${WEB_IMAGE} at ${DEPLOY_PATH} ($(git rev-parse --short HEAD))"
