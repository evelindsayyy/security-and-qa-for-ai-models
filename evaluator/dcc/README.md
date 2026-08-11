# Running on the Duke Compute Cluster (DCC)

Notes + scripts for running evaluator jobs on the DCC. Start with the
"hello GPU" test (`hello_gpu.sh`) to learn the SLURM workflow before you
run a real model.

**Why the DCC at all?** The Gateway-based eval (candidate calls
`litellm.oit.duke.edu`) does NOT need a GPU. The DCC is only for
**self-hosting open-source models** too big for a laptop (roughly 13B+).
For small open models (≤8B), Ollama on your laptop is enough.

NetID on the cluster: `lz302`. Everything must live under `/work/lz302/`
(20 TiB), never your home dir (25 GiB).

---

## One-time setup (you do this; it needs your Duke login)

```bash
# 1. Log in (needs your NetID password + 2FA — only you can do this)
ssh dcc

# 2. Make an SSH key so the cluster can reach GitHub (accept defaults, no passphrase)
ssh-keygen -t ed25519
cat ~/.ssh/id_ed25519.pub          # copy this whole line

# 3. Paste that key into GitHub → Settings → SSH and GPG keys (in your browser)

# 4. Clone the repo onto /work (NOT home)
cd /work/lz302
git clone git@github.com:evelindsayyy/security-and-qa-for-ai-models.git
cd security-and-qa-for-ai-models

# 5. Install deps (uv is already on the cluster, cache already points at /work)
uv sync
```

Alternative to steps 1–4 if GitHub auth is a hassle — push from your laptop,
then `rsync` to the cluster (re-run after every change):

```bash
# from your laptop, in the repo dir:
rsync -a --exclude .venv --exclude .git ./ dcc:/work/lz302/security-and-qa-for-ai-models/
```

---

## Test 1 — "hello GPU" (run this FIRST)

Proves the workflow end-to-end without running a model.

```bash
cd /work/lz302/security-and-qa-for-ai-models
mkdir -p logs                                   # output dir must exist before submitting
sbatch evaluator/dcc/hello_gpu.sh               # submit; prints "Submitted batch job <id>"
squeue -u lz302                                 # watch it: PD=pending, R=running, gone=done
tail -f logs/hello-gpu-<id>.out                 # read the output (Ctrl-C to stop tailing)
scancel <id>                                    # only if you need to kill it
```

**Success =** the log's section 2 shows an `A5000` in the `nvidia-smi` table.
That means: code reached `/work`, SLURM queued the job, a GPU node ran it,
and the log came back. You now know how to use the cluster.

**If it sits in `PD` (pending) a long time:** the GPU partition is busy —
normal. Lower the wait by not needing a GPU for a pure-mechanics test:
edit `hello_gpu.sh`, change `--partition=gpu-common` to `--partition=common`
and delete the `--gres=gpu...` line. (You lose the GPU check but prove the
rest of the workflow instantly.)

---

## Test 2 — serve a small open model + evaluate it (LATER)

Once Test 1 works, the real job is: start a vLLM server on the GPU node,
point the runner at it, run the eval. That script isn't written yet — it's
the next step, and needs:
  - the `--candidate-endpoint` override added to `candidate.py`/`runner.py`
    (so the runner can target `http://localhost:8000/v1` instead of the Gateway)
  - a chosen model (start small: `meta-llama/Llama-3.1-8B-Instruct` fits one A5000)
  - the judge stays on the Gateway — only the candidate is self-hosted

Plan this with Claude when you're ready; don't hand-roll the vLLM + SLURM
glue blind.

---

## SLURM cheat-sheet

| Command | What it does |
|---|---|
| `sbatch script.sh` | submit a job |
| `squeue -u lz302` | your jobs (`PD`=pending, `R`=running) |
| `tail -f logs/<name>-<id>.out` | watch a job's output live |
| `scancel <id>` | kill a job |
| `sinfo` | what partitions/nodes exist |
| `scontrol show job <id>` | full detail on one job |

The knobs in a `#SBATCH` header: `--partition` (which node pool),
`--gres=gpu:a5000:N` (how many GPUs), `--mem`, `--cpus-per-task`,
`--time` (hard wall-clock limit — job is killed when it's hit).
