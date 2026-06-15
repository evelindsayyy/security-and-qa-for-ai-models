#!/usr/bin/env bash
# End-to-end safety: Promptfoo policy + red-team + Garak + merge.
#
# Usage (from repo root):
#   ./safety/run_safety.sh
#   ./safety/run_safety.sh "gpt-5-chat"
#   ./safety/run_safety.sh --skip-redteam
#   ./safety/run_safety.sh --garak-probes "encoding,promptinject,dan.Dan_11_0"
#   ./safety/run_safety.sh --skip-garak
#   ./safety/run_safety.sh --skip-promptfoo

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./safety/run_safety.sh [MODEL] [OPTIONS]

End-to-end safety for one gateway model: Promptfoo policy, red-team, Garak, merge.

MODEL defaults to the GATEWAY_MODEL environment variable (or "GPT 4.1 Mini").

Options:
  --skip-redteam         Skip Promptfoo red-team eval + export
  --skip-promptfoo       Skip Promptfoo (Garak + merge only)
  --skip-garak           Skip Garak (Promptfoo + merge only)
  --garak-probes LIST    Comma-separated Garak modules (overrides garak_duke.yaml)
  --help                 Show this help

Examples:
  ./safety/run_safety.sh
  ./safety/run_safety.sh "gpt-5-chat"
  ./safety/run_safety.sh --skip-redteam
  ./safety/run_safety.sh --garak-probes "encoding,promptinject"

Individual suite commands: safety/README.md and safety/{promptfoo,garak}/README.md
EOF
}

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

run_py() {
  # Host dev may use uv; Docker orchestrator images use plain python + pip deps.
  if PYTHONPATH=. python -c "import safety.merge" >/dev/null 2>&1; then
    PYTHONPATH=. python "$@"
  else
    PYTHONPATH=. uv run python "$@"
  fi
}

DEFAULT_MODEL="${GATEWAY_MODEL:-GPT 4.1 Mini}"

MODEL="$DEFAULT_MODEL"
REDTEAM=true
SKIP_PROMPTFOO=false
SKIP_GARAK=false
GARAK_PROBES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --skip-redteam)
      REDTEAM=false
      shift
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
export REDTEAM_GRADER_MODEL="${REDTEAM_GRADER_MODEL:-GPT 4.1 Mini}"
SLUG="$(GATEWAY_MODEL="$MODEL" PYTHONPATH=. python -c "
from safety.gateway_ids import normalize_gateway_model_id
import os
print(normalize_gateway_model_id(os.environ['GATEWAY_MODEL']))
")"

mkdir -p "safety/promptfoo/output/${SLUG}" "safety/garak/output/${SLUG}" "safety/output/${SLUG}"

# Sub-stacks read the single repo-root .env (mounted at /app/.env in the orchestrator).
# The safety container uses `docker-compose` when available so nested runs work even
# when the image does not expose the Docker v2 plugin.
if command -v docker-compose >/dev/null 2>&1; then
  PF_DC="docker-compose --env-file .env -f safety/promptfoo/docker/compose.yml"
  GARAK_DC="docker-compose --env-file .env -f safety/garak/docker/compose.yml"
else
  PF_DC="docker compose --env-file .env -f safety/promptfoo/docker/compose.yml"
  GARAK_DC="docker compose --env-file .env -f safety/garak/docker/compose.yml"
fi

echo "Safety run: model=${MODEL} slug=${SLUG} redteam=${REDTEAM}"

MERGE_ARGS=()

if ! $SKIP_PROMPTFOO; then
  echo "--- Promptfoo policy ---"
  set +e
  $PF_DC run --rm -e GATEWAY_MODEL="$MODEL" -e REDTEAM_GRADER_MODEL="$REDTEAM_GRADER_MODEL" promptfoo \
    promptfoo eval -c promptfooconfig.yaml -o "output/${SLUG}/eval.json"
  PF_RC=$?
  set -e
  if [[ $PF_RC -ne 0 && ! -f "safety/promptfoo/output/${SLUG}/eval.json" ]]; then
    echo "ERROR: policy eval failed (exit ${PF_RC}); no eval.json written" >&2
    exit $PF_RC
  fi

  run_py safety/promptfoo/export_safety_result.py \
    "safety/promptfoo/output/${SLUG}/eval.json"
  MERGE_ARGS+=(--promptfoo "safety/promptfoo/output/${SLUG}/safety_result.json")

  if $REDTEAM; then
    echo "--- Promptfoo red-team ---"
    set +e
    $PF_DC run --rm -e GATEWAY_MODEL="$MODEL" -e REDTEAM_GRADER_MODEL="$REDTEAM_GRADER_MODEL" promptfoo \
      promptfoo redteam run -c promptfooconfig.redteam.yaml \
      -o "output/${SLUG}/redteam_eval.json" --delay 500 --max-concurrency 1 --force
    RT_RC=$?
    set -e
    if [[ $RT_RC -ne 0 && ! -f "safety/promptfoo/output/${SLUG}/redteam_eval.json" ]]; then
      echo "ERROR: red-team failed (exit ${RT_RC})" >&2
      exit $RT_RC
    fi

    run_py safety/promptfoo/export_safety_result.py \
      "safety/promptfoo/output/${SLUG}/redteam_eval.json"
    MERGE_ARGS+=(--promptfoo "safety/promptfoo/output/${SLUG}/redteam_safety_result.json")
  else
    echo "--- Promptfoo red-team skipped (--skip-redteam) ---"
  fi
else
  echo "--- Promptfoo skipped (--skip-promptfoo) ---"
fi

if ! $SKIP_GARAK; then
  echo "--- Garak scan ---"
  GARAK_RUN_CFG="/app/safety/garak/output/${SLUG}/garak_run.yaml"
  sed "s|report_dir: .*|report_dir: /app/safety/garak/output/${SLUG}|" \
    safety/garak/garak_duke.yaml > "${GARAK_RUN_CFG}"
  GARAK_CMD=(python -m garak --config "${GARAK_RUN_CFG}" -n "${MODEL}")
  if [[ -n "$GARAK_PROBES" ]]; then
    GARAK_CMD+=(-p "$GARAK_PROBES")
  fi

  set +e
  "${GARAK_CMD[@]}"
  GARAK_RC=$?
  set -e

  shopt -s nullglob
  REPORT_CANDIDATES=("safety/garak/output/${SLUG}/garak-duke"*.report.jsonl)
  shopt -u nullglob

  REPORT=""
  if (( ${#REPORT_CANDIDATES[@]} > 0 )); then
    REPORT="$(ls -t "${REPORT_CANDIDATES[@]}" | head -1)"
  fi

  if [[ -z "$REPORT" ]]; then
    echo "ERROR: Garak finished (exit ${GARAK_RC}) but no report in safety/garak/output/${SLUG}/" >&2
    exit "${GARAK_RC:-1}"
  fi

  echo "--- Garak export ---"
  run_py safety/garak/export_safety_result.py \
    "$REPORT" \
    -o "safety/garak/output/${SLUG}/safety_result.json" \
    --gateway-model-id "$MODEL"
  MERGE_ARGS+=(--garak "safety/garak/output/${SLUG}/safety_result.json")
else
  echo "--- Garak skipped (--skip-garak) ---"
fi

if [ ${#MERGE_ARGS[@]} -eq 0 ]; then
  echo "ERROR: nothing to merge — run at least one suite" >&2
  exit 1
fi

echo "--- Merge ---"
run_py -m safety.merge \
  "${MERGE_ARGS[@]}" \
  -o "safety/output/${SLUG}/merged_safety_result.json"

echo "Complete: safety/output/${SLUG}/merged_safety_result.json"
echo "Frontend: /safety/${SLUG}"
