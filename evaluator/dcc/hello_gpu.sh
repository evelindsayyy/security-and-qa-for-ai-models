#!/bin/bash -l
# =============================================================================
# hello_gpu.sh — minimal DCC test job
# =============================================================================
# Purpose: prove you can use the cluster, with as few moving parts as possible.
# It requests one GPU for 5 minutes and just prints what it got. If you can
# read its log afterwards and see an A5000 in the nvidia-smi output, the whole
# workflow works (code on /work -> sbatch -> GPU node -> logs back).
#
# This does NOT run a model. It's the "hello world" you run first, before
# any vLLM / model-serving job, so you learn the SLURM mechanics in isolation.
#
# Run it (from the repo dir on the DCC):
#   mkdir -p logs
#   sbatch evaluator/dcc/hello_gpu.sh
#   squeue -u $USER                 # watch it queue/run
#   tail -f logs/hello-gpu-<jobid>.out
# =============================================================================

#SBATCH --job-name=hello-gpu
#SBATCH --output=logs/%x-%j.out        # %x=job-name, %j=job-id. Needs logs/ to exist.
#SBATCH --partition=gpu-common         # GPU partition (from your team's instructions)
#SBATCH --gres=gpu:a5000:1             # ask for ONE A5000 GPU
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:05:00                # 5 min cap — short jobs queue faster

set -euo pipefail                      # fail loudly on any error or unset var

# sbatch starts the job in the directory you submitted from; be explicit.
cd "${SLURM_SUBMIT_DIR:-$PWD}"

echo "=== 1. Where is this running? ==="
hostname                               # the GPU node's name
date
echo "USER=$USER"
echo "SUBMIT_DIR=${SLURM_SUBMIT_DIR:-$PWD}"
echo

echo "=== 2. What GPU did SLURM give this job? ==="
# If this prints an A5000, your GPU request succeeded. This is the key line.
nvidia-smi
echo

echo "=== 3. Is the environment sane? ==="
python3 --version || echo "(no system python3 — fine, uv manages its own)"
uv --version || echo "(uv not on PATH)"
echo

echo "=== Done. If you can read this in the log file, the cluster works. ==="
