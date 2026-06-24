# Frontend (`frontend/`)

Nutrition-label UI. Each pillar reads via ``*_data.py`` (Postgres when a DSN
is configured, with artifact fallback). Browser-launched runs via Docker + polling.

## Run

**Local (fastest):**

```bash
uv sync
uv run flask --app frontend:create_app run --debug
```

Launch pages: `/scans/new` · `/safety/new` · `/eval-run/new` · `/benchmarks/new`

Set `FRONTEND_LAUNCH_MODE=host` to skip Docker for launches (debugging, unit tests).

### Benchmark model sources (`/benchmarks/new`)

Three ways to pick a model — the form shows a setup guide that changes with your
selection. Full reference: [`benchmarks/README.md`](../benchmarks/README.md#model-input-cheat-sheet).

| Source | Model input example |
|--------|---------------------|
| Gateway | `GPT 4.1 Mini` (dropdown) |
| Hosted (HF Inference) | `meta-llama/Llama-3.1-8B-Instruct` + `hf_…` token |
| Custom (vLLM) | `Qwen/Qwen3-0.6B` + `http://localhost:8000/v1` |

**Containerized (application VM):** [`docs/docker.md`](../docs/docker.md).

## Routes

| Route | Purpose |
|-------|---------|
| `/` | Hub — pillar counts + gateway link |
| `/models` | Live gateway catalog |
| `/scans`, `/scans/new`, `/scans/start`, `/scans/<slug>` | HF scanning |
| `/eval-run`, `/eval-run/new`, … | Duke efficacy (LLM-as-judge) |
| `/benchmarks`, `/benchmarks/new`, … | Public benchmarks |
| `/safety`, `/safety/new`, … | Inference safety |

Each pillar has `/<slug>/status` JSON for in-progress polling.

## Layout

| Module | Role |
|--------|------|
| [`gateway/`](../gateway/) | Live catalog for `/models` and dropdowns |
| `scan_data.py` / `scan_db_data.py` | `/scans` — DB when `POSTGRES_DSN` set |
| `safety_data.py` / `safety_db_data.py` | `/safety` — DB when `POSTGRES_DSN` set |
| `eval_run_data.py` / `eval_db_data.py` | `/eval-run` — DB when `EFFICACY_DB_DSN` set |
| `benchmark_data.py` / `benchmark_db_data.py` | `/benchmarks` — DB when `POSTGRES_DSN` set |
| `*_launch.py` | Spawn Docker/host subprocess for browser runs |
| `docker_launch.py` | Shared Docker helper (`.env`, UID/GID, compose build) |
| `routes.py`, `templates/`, `static/` | UI |

## Related docs

- [`docs/architecture.md`](../docs/architecture.md)
- [`docs/docker.md`](../docs/docker.md)
- Pillar READMEs: [`scanner/`](../scanner/README.md) · [`safety/`](../safety/README.md) · [`evaluator/`](../evaluator/README.md) · [`benchmarks/`](../benchmarks/README.md)
