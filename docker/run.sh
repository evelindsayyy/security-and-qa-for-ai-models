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
#   ./docker/run.sh up --build      # start (foreground)
#   ./docker/run.sh up -d --build   # start (background)
#   ./docker/run.sh down            # stop
#   ./docker/run.sh logs -f web     # logs
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=docker/host-env.sh
source docker/host-env.sh

ENV_ARGS=()
[ -f .env ] && ENV_ARGS=(--env-file .env)

exec docker compose --project-name qa-ai-models "${ENV_ARGS[@]}" \
  -f docker/compose.yml "$@"
