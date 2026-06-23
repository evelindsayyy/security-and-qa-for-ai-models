#!/bin/bash -l
# Submit a Slurm job that starts a local vLLM server for a chosen model.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
STATE_FILE="${SCRIPT_DIR}/.vllm-session.env"

MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
PORT="${PORT:-8000}"
HF_HOME="${HF_HOME:-/work/${USER}/hf_cache}"
PARTITION="${PARTITION:-codeplussu2026-gpu}"
GPU_TYPE="${GPU_TYPE:-}"
GPU_COUNT="${GPU_COUNT:-1}"
CPUS_PER_TASK="${CPUS_PER_TASK:-8}"
MEMORY="${MEMORY:-64G}"
WALL_TIME="${WALL_TIME:-02:00:00}"
DTYPE="${DTYPE:-bfloat16}"
ACCOUNT="${ACCOUNT:-codeplussu2026}"
LOG_DIR="${LOG_DIR:-${REPO_ROOT}/logs}"

mkdir -p "${LOG_DIR}"

SBATCH_ARGS=(
  --job-name=vllm-server
  --output="${LOG_DIR}/%x-%j.out"
  --partition="${PARTITION}"
  --cpus-per-task="${CPUS_PER_TASK}"
  --mem="${MEMORY}"
  --time="${WALL_TIME}"
  --export=ALL,MODEL="${MODEL}",PORT="${PORT}",HF_HOME="${HF_HOME}",LOG_DIR="${LOG_DIR}",DTYPE="${DTYPE}",REPO_ROOT="${REPO_ROOT}"
)

if [[ -n "${GPU_TYPE}" ]]; then
  SBATCH_ARGS+=(--gres="gpu:${GPU_TYPE}:${GPU_COUNT}")
else
  SBATCH_ARGS+=(--gres="gpu:${GPU_COUNT}")
fi

if [[ -n "${ACCOUNT}" ]]; then
  SBATCH_ARGS+=(--account="${ACCOUNT}")
fi

JOB_ID="$(
  sbatch --parsable "${SBATCH_ARGS[@]}" <<'EOF'
#!/bin/bash -l
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

# vLLM is in the optional 'dcc' dependency group, so request it explicitly —
# a plain `uv sync` installs core + dev only and the job dies with exit 127
# ("vllm: command not found"). Linux/CUDA-only; the .venv on /work persists,
# so this is a one-time install then a fast no-op on later runs.
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

# Power or Thanos metrics can be added back here later.
EOF
)"

cat > "${STATE_FILE}" <<EOF
JOB_ID="${JOB_ID}"
MODEL="${MODEL}"
PORT="${PORT}"
LOG_DIR="${LOG_DIR}"
EOF

echo "Submitted vLLM job ${JOB_ID}"
echo "State file: ${STATE_FILE}"
