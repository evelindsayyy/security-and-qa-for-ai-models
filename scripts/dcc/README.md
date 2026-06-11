# DCC vLLM Examples

These scripts split the original one-shot Slurm workflow into a small lifecycle:

1. Start a Slurm job that boots a local vLLM server for a chosen model
2. Wait for the allocation and health endpoint to become ready
3. Send prompts to the running vLLM server from a separate client script
4. Check status or stop the job when you are done

This separation makes the workflow easier to explain, debug, and reuse.

## Scripts

- `start_vllm.sh`: submit a Slurm job that starts vLLM for a selected model
- `status_vllm.sh`: show the current Slurm status for the active job
- `wait_vllm.sh`: wait until the allocation is running and the vLLM `/health` endpoint is ready
- `stop_vllm.sh`: cancel the current job and remove the local session state
- `chat_vllm.py`: send a prompt to a running vLLM server

## Typical Flow

Start a vLLM job:

```bash
MODEL="Qwen/Qwen2.5-7B-Instruct" scripts/dcc/start_vllm.sh
```

Wait until it is ready:

```bash
scripts/dcc/wait_vllm.sh
```

Submit a prompt to the running server:

```bash
uv run python scripts/dcc/chat_vllm.py \
  --prompt "Explain why batching improves GPU throughput."
```


Check job state:

```bash
scripts/dcc/status_vllm.sh
```

Stop the job:

```bash
scripts/dcc/stop_vllm.sh
```

## Notes

- `start_vllm.sh` is based on the structure of the original `submit.sh` example but only handles server startup.
- `start_vllm.sh` submits the Slurm job itself, so do not wrap it in another `sbatch` command.
- `chat_vllm.py` is intentionally small and only demonstrates inference against an existing server.
- The shell helpers keep a tiny local state file at `scripts/dcc/.vllm-session.env` so the later commands do not need the job id retyped each time.
- Thanos or Prometheus power-metric collection is intentionally left out for now. There is a comment in the generated Slurm script showing where that logic could be reintroduced later.

## Slurm Cheat Sheet

Useful commands on the DCC login node:

```bash
# Show likely GPU partitions and current availability
sinfo -p codeplussu2026-gpu,scavenger-gpu -o "%P %a %l %D %t %C"

# Show your jobs
squeue -u "$USER" -o "%i %P %T %R"

# Show details for one job
scontrol show job <jobid>

# Cancel a job
scancel <jobid>
```

Minimal GPU smoke test:

```bash
sbatch --parsable \
  -A codeplussu2026 \
  -p codeplussu2026-gpu \
  --gres=gpu:1 \
  --time=00:02:00 \
  --job-name=codeplus-gpu-smoke \
  --output="$HOME/projects/smoke/codeplus-gpu-smoke-%j.out" \
  --wrap 'hostname; nvidia-smi -L'
```

In that `sbatch` example, GPU selection happens in two places:

- `-p codeplussu2026-gpu` chooses the GPU partition
- `--gres=gpu:1` asks Slurm for one GPU within that partition
