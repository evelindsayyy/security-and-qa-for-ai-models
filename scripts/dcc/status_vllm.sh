#!/bin/bash
# Show the current Slurm status for the last started vLLM job.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="${SCRIPT_DIR}/.vllm-session.env"

if [[ ! -f "${STATE_FILE}" ]]; then
  echo "No vLLM session state file found at ${STATE_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${STATE_FILE}"

squeue -j "${JOB_ID}" -o "%.18i %.10T %.20R %B"
