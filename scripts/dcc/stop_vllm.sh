#!/bin/bash
# Cancel the current vLLM Slurm job and remove the local session state.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="${SCRIPT_DIR}/.vllm-session.env"

if [[ ! -f "${STATE_FILE}" ]]; then
  echo "No vLLM session state file found at ${STATE_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${STATE_FILE}"

scancel "${JOB_ID}"
rm -f "${STATE_FILE}"

echo "Cancelled vLLM job ${JOB_ID}"
