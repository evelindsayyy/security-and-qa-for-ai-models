#!/bin/bash
# Wait for the Slurm allocation and local vLLM health endpoint to become ready.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="${SCRIPT_DIR}/.vllm-session.env"
SQUEUE_FORMAT="%.18i %.10T %.20R %B"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-120}"
SLEEP_SECONDS="${SLEEP_SECONDS:-10}"

if [[ ! -f "${STATE_FILE}" ]]; then
  echo "No vLLM session state file found at ${STATE_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${STATE_FILE}"

attempt=0
while (( attempt < MAX_ATTEMPTS )); do
  line="$(squeue -h -j "${JOB_ID}" -o "${SQUEUE_FORMAT}" || true)"
  if [[ -z "${line}" ]]; then
    echo "Job ${JOB_ID} is no longer in squeue." >&2
    exit 1
  fi

  node="$(echo "${line}" | awk '{print $4}')"
  state="$(echo "${line}" | awk '{print $2}')"
  echo "Job ${JOB_ID} state=${state} node=${node}"

  if [[ "${state}" == "R" && -n "${node}" && "${node}" != "(null)" && "${node}" != "n/a" ]]; then
    if curl -sf "http://${node}:${PORT}/health" >/dev/null; then
      echo "vLLM is ready at http://${node}:${PORT}/v1"
      cat > "${STATE_FILE}" <<EOF
JOB_ID="${JOB_ID}"
MODEL="${MODEL}"
PORT="${PORT}"
LOG_DIR="${LOG_DIR}"
HOST="${node}"
EOF
      exit 0
    fi
  fi

  sleep "${SLEEP_SECONDS}"
  attempt=$((attempt + 1))
done

echo "Timed out waiting for vLLM job ${JOB_ID} to become ready." >&2
exit 1
