#!/bin/bash
set -euo pipefail

# Docker CLI and compose need a writable HOME for config; compose sets HOME to
# <repo>/.docker-home (gitignored). working_dir is set by compose to HOST_REPO.
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-qa-ai-models}"
mkdir -p "${HOME:-/tmp/.docker-home}" 2>/dev/null || true

exec "$@"
