#!/usr/bin/env bash
# Apply all four pillar Postgres DDL files (one-time or after schema changes).
#
#   ./scripts/apply-schemas.sh              # apply schemas only
#   ./scripts/apply-schemas.sh --bootstrap  # apply schemas + api.ingest bootstrap --apply
#
# Requires: repo root, .env with POSTGRES_DSN, prior uv sync --group dev
set -euo pipefail

cd "$(dirname "$0")/.."

BOOTSTRAP=0
for arg in "$@"; do
  case "$arg" in
    --bootstrap) BOOTSTRAP=1 ;;
    -h|--help)
      sed -n '2,8p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

if [ ! -f .env ]; then
  echo "Missing .env — cp .env.example .env first" >&2
  exit 1
fi

for schema in \
  scanner/db/scan_schema.sql \
  safety/db/safety_schema.sql \
  evaluator/db/efficacy_schema.sql \
  benchmarks/db/benchmark_schema.sql; do
  echo "Applying ${schema}..."
  uv run python -m dbutils.apply_schema "$schema"
done

if [ "$BOOTSTRAP" -eq 1 ]; then
  echo "Bootstrapping Postgres from on-disk artifacts..."
  uv run python -m api.ingest bootstrap --apply
fi

echo "Done."
