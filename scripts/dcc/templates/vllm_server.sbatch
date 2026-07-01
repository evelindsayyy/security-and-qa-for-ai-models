#!/bin/bash -l
#SBATCH --job-name=vllm-server
# Submitted by: python -m scripts.dcc.vllm start
# %x and %j expanded by Slurm; output path set via --output on sbatch CLI.

set -euo pipefail

cd "${REPO_ROOT}"

load_cuda() {
  if command -v module >/dev/null 2>&1; then
    module load CUDA/12.8 || echo "warning: failed to load CUDA/12.8; using system CUDA" >&2
  else
    echo "note: no module command on $(hostname); using system CUDA from /usr/local" >&2
  fi
  if [[ -d /usr/local/cuda/bin ]]; then
    export PATH="/usr/local/cuda/bin:${PATH}"
    export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
  fi
}

mkdir -p "${HF_HOME}" "${LOG_DIR}"
load_cuda

uv sync --frozen --group dcc
source "${REPO_ROOT}/.venv/bin/activate"

echo "Starting vLLM for ${MODEL} on $(hostname):${PORT}"
echo "Logs: ${LOG_DIR}/server-${SLURM_JOB_ID}.log"

vllm serve "${MODEL}" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --download-dir "${HF_HOME}" \
  --dtype "${DTYPE}" \
  > "${LOG_DIR}/server-${SLURM_JOB_ID}.log" 2>&1
