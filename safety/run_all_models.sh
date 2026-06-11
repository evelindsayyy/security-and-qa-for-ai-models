#!/usr/bin/env bash
# Run full safety pipeline sequentially for all gateway models.
# Use YOUR IDE terminal so output stays visible (agent background tabs may vanish).
#
# Usage (from repo root):
#   ./safety/run_all_models.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODELS=(
  "GPT 4.1 Mini"
  "gpt-5-chat"
  "gpt-5.5"
  "gpt-5-mini"
  "Llama 4 Maverick"
)

MASTER="safety/output/sequential_run.log"
echo "=== Sequential safety started $(date -Iseconds) ===" | tee -a "$MASTER"

for MODEL in "${MODELS[@]}"; do
  SLUG="$(GATEWAY_MODEL="$MODEL" PYTHONPATH=. uv run python -c "
from safety.gateway_ids import normalize_gateway_model_id
import os
print(normalize_gateway_model_id(os.environ['GATEWAY_MODEL']))
")"
  LOG="safety/output/${SLUG}/run.log"
  mkdir -p "safety/output/${SLUG}"

  echo ""
  echo "========================================"
  echo " START: $MODEL (slug=$SLUG) $(date -Iseconds)"
  echo "========================================"
  echo "=== START $MODEL (slug=$SLUG) $(date -Iseconds) ===" >> "$MASTER"

  ./safety/run_safety.sh "$MODEL" 2>&1 | tee "$LOG"

  echo "=== DONE $MODEL $(date -Iseconds) ===" | tee -a "$MASTER"
done

echo "=== All models complete $(date -Iseconds) ===" | tee -a "$MASTER"
