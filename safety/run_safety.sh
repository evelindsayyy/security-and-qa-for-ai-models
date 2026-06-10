#!/usr/bin/env bash
# End-to-end safety: Promptfoo policy (+ optional red-team) + Garak + merge.
#
# Usage (from repo root):
#   ./safety/run_safety.sh
#   ./safety/run_safety.sh "gpt-5-chat" --redteam
#   ./safety/run_safety.sh --garak-probes "encoding,promptinject,dan.Dan_11_0"
#   ./safety/run_safety.sh --skip-garak          # promptfoo + merge only
#   ./safety/run_safety.sh --skip-promptfoo      # garak + merge only

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./safety/run_safety.sh [MODEL] [OPTIONS]

End-to-end safety for one gateway model: Promptfoo policy, Garak scan, merge.
Pass --redteam to add the Promptfoo red-team suite.

MODEL defaults to "GPT 4.1 Mini" (or GATEWAY_MODEL env).

Options:
  --redteam              Include Promptfoo red-team eval + export
  --skip-promptfoo       Skip Promptfoo (Garak + merge only)
  --skip-garak           Skip Garak (Promptfoo + merge only)
  --garak-probes LIST    Comma-separated Garak modules (overrides garak_duke.yaml)
  --help                 Show this help

Examples:
  ./safety/run_safety.sh
  ./safety/run_safety.sh "gpt-5-chat"
  ./safety/run_safety.sh "GPT 4.1 Mini" --redteam
  ./safety/run_safety.sh --garak-probes "encoding,promptinject"

Individual suite commands: safety/README.md and safety/{promptfoo,garak}/README.md
EOF
}

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODEL="${GATEWAY_MODEL:-GPT 4.1 Mini}"
REDTEAM=false
SKIP_PROMPTFOO=false
SKIP_GARAK=false
GARAK_PROBES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --redteam)
      REDTEAM=true
      shift
      ;;
    --skip-promptfoo)
      SKIP_PROMPTFOO=true
      shift
      ;;
    --skip-garak)
      SKIP_GARAK=true
      shift
      ;;
    --garak-probes)
      if [[ -z "${2:-}" ]]; then
        echo "ERROR: --garak-probes requires a comma-separated module list" >&2
        exit 1
      fi
      GARAK_PROBES="$2"
      shift 2
      ;;
    -*)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      MODEL="$1"
      shift
      ;;
  esac
done

if $SKIP_PROMPTFOO && $SKIP_GARAK; then
  echo "ERROR: cannot use --skip-promptfoo and --skip-garak together" >&2
  exit 1
fi

export GATEWAY_MODEL="$MODEL"
SLUG="$(GATEWAY_MODEL="$MODEL" PYTHONPATH=. uv run python -c "
from safety.gateway_ids import normalize_gateway_model_id
import os
print(normalize_gateway_model_id(os.environ['GATEWAY_MODEL']))
")"

mkdir -p "safety/promptfoo/output/${SLUG}" "safety/garak/output/${SLUG}" "safety/output/${SLUG}"

PF_DC="docker compose --env-file safety/promptfoo/docker/.env -f safety/promptfoo/docker/compose.yml"
GARAK_DC="docker compose --env-file safety/garak/docker/.env -f safety/garak/docker/compose.yml"

echo "Safety run: model=${MODEL} slug=${SLUG}"

MERGE_ARGS=()

if ! $SKIP_PROMPTFOO; then
  echo "--- Promptfoo policy ---"
  set +e
  $PF_DC run --rm -e GATEWAY_MODEL="$MODEL" promptfoo \
    promptfoo eval -c promptfooconfig.yaml -o "output/${SLUG}/eval.json"
  PF_RC=$?
  set -e
  if [[ $PF_RC -ne 0 && ! -f "safety/promptfoo/output/${SLUG}/eval.json" ]]; then
    echo "ERROR: policy eval failed (exit ${PF_RC}); no eval.json written" >&2
    exit $PF_RC
  fi

  PYTHONPATH=. uv run python safety/promptfoo/export_safety_result.py \
    "safety/promptfoo/output/${SLUG}/eval.json"
  MERGE_ARGS+=(--promptfoo "safety/promptfoo/output/${SLUG}/safety_result.json")

  if $REDTEAM; then
    echo "--- Promptfoo red-team ---"
    set +e
    $PF_DC run --rm -e GATEWAY_MODEL="$MODEL" promptfoo \
      promptfoo redteam run -c promptfooconfig.redteam.yaml \
      -o "output/${SLUG}/redteam_eval.json" --delay 500 --max-concurrency 1 --force
    RT_RC=$?
    set -e
    if [[ $RT_RC -ne 0 && ! -f "safety/promptfoo/output/${SLUG}/redteam_eval.json" ]]; then
      echo "ERROR: red-team failed (exit ${RT_RC})" >&2
      exit $RT_RC
    fi

    PYTHONPATH=. uv run python safety/promptfoo/export_safety_result.py \
      "safety/promptfoo/output/${SLUG}/redteam_eval.json"
    MERGE_ARGS+=(--promptfoo "safety/promptfoo/output/${SLUG}/redteam_safety_result.json")
  fi
else
  echo "--- Promptfoo skipped (--skip-promptfoo) ---"
fi

if ! $SKIP_GARAK; then
  echo "--- Garak scan ---"
  GARAK_CMD=(python -m garak --config garak_duke.yaml -n "${MODEL}")
  if [[ -n "$GARAK_PROBES" ]]; then
    GARAK_CMD+=(-p "$GARAK_PROBES")
  fi

  set +e
  $GARAK_DC run --rm garak "${GARAK_CMD[@]}"
  GARAK_RC=$?
  set -e

  shopt -s nullglob
  REPORT_CANDIDATES=(
    safety/garak/output/garak-duke-*.report.jsonl
    "safety/garak/output/${SLUG}/garak-duke-"*.report.jsonl
  )
  shopt -u nullglob

  REPORT=""
  if (( ${#REPORT_CANDIDATES[@]} > 0 )); then
    REPORT="$(ls -t "${REPORT_CANDIDATES[@]}" | head -1)"
  fi

  if [[ -z "$REPORT" ]]; then
    echo "ERROR: Garak finished (exit ${GARAK_RC}) but no garak-duke-*.report.jsonl found" >&2
    exit "${GARAK_RC:-1}"
  fi

  REPORT_DEST="safety/garak/output/${SLUG}/$(basename "$REPORT")"
  if [[ "$REPORT" != "$REPORT_DEST" ]]; then
    cp "$REPORT" "$REPORT_DEST"
    REPORT="$REPORT_DEST"
  fi

  echo "--- Garak export ---"
  PYTHONPATH=. uv run python safety/garak/export_safety_result.py \
    "$REPORT" \
    -o "safety/garak/output/${SLUG}/safety_result.json" \
    --gateway-model-id "$MODEL"
  MERGE_ARGS+=(--garak "safety/garak/output/${SLUG}/safety_result.json")
else
  echo "--- Garak skipped (--skip-garak) ---"
fi

if (( ${#MERGE_ARGS[@]} == 0 )); then
  echo "ERROR: nothing to merge — run at least one suite" >&2
  exit 1
fi

echo "--- Merge ---"
PYTHONPATH=. uv run python -m safety.merge \
  "${MERGE_ARGS[@]}" \
  -o "safety/output/${SLUG}/merged_safety_result.json"

echo "Complete: safety/output/${SLUG}/merged_safety_result.json"
echo "Frontend: /safety/${SLUG}"
