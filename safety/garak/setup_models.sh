#!/usr/bin/env bash
# One-time download of the ML detector model required for full latentinjection + lmrc probes.
#
# The only model needed is garak-llm/roberta_toxicity_classifier (HuggingFace), used by
# garak's ToxicCommentModel detector. It is not bundled in the garak pip package and must
# be downloaded before the first scan that uses it.
#
# The model lands in safety/garak/output/.garak-cache/huggingface/ (the mounted volume),
# so it persists across all future scans without re-downloading.
#
# Run once on the server before enabling latentinjection and lmrc as full modules.
#
# Usage (from repo root):
#   ./safety/garak/setup_models.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="safety/garak/docker/compose.yml"

if command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  DC="docker compose"
fi

ENV_FLAG=""
if [ -f ".env" ]; then
  ENV_FLAG="--env-file .env"
fi

GARAK_DC="$DC $ENV_FLAG -f $COMPOSE_FILE"

echo "Building garak image (skipped if already built)..."
$GARAK_DC build garak

echo "Downloading garak-llm/roberta_toxicity_classifier..."
$GARAK_DC run --rm garak python -c "
from garak.detectors.unsafe_content import ToxicCommentModel
ToxicCommentModel()
print('Done.')
"

echo ""
echo "Done. Model cached at safety/garak/output/.garak-cache/huggingface/"
echo ""
echo "Next step: update probe_spec in safety/garak/garak_duke.yaml"
echo "  Replace the individual latentinjection.* and lmrc.* classes"
echo "  with: latentinjection,lmrc"
