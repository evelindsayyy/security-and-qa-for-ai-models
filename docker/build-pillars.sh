#!/usr/bin/env bash
# One-time: build all four pillar job images (scanner, safety, evaluator, benchmarks).
set -euo pipefail

cd "$(dirname "$0")/.."

export HOST_REPO="$(pwd)"
export UID="$(id -u)"
export GID="$(id -g)"

if [ ! -f .env ]; then
  echo "Missing .env — cp .env.example .env first" >&2
  exit 1
fi

for compose in \
  scanner/docker/compose.yml \
  safety/docker/compose.yml \
  evaluator/docker/compose.yml \
  benchmarks/docker/compose.yml; do
  echo "Building ${compose}..."
  docker compose --env-file .env -f "$compose" build
done

echo "Done. Pillar images ready for browser/API Start buttons."
