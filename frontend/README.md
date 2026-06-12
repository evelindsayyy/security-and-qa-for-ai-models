# Frontend (`frontend/`)

Progress viewer for the Duke model nutrition label. Loads JSON from local pipeline output; scan, safety, eval, and benchmark pillars support **browser-launched runs** (Docker + live polling).

Production UI will read from Postgres via `api/`. This draft reads disk under `scanner/output/`, `evaluator/results/`, `benchmarks/results/`, and `safety/output/`.

## Run locally

```bash
uv sync
uv run flask --app frontend:create_app run --debug
```

## Routes

| Route | Purpose |
|-------|---------|
| `/` | Hub — pillar counts + gateway link |
| `/models` | Live gateway catalog |
| `/scans`, `/scans/new`, `/scans/start`, `/scans/<slug>` | HF scanning |
| `/eval-run`, `/eval-run/new`, … | Duke efficacy (LLM-as-judge) |
| `/benchmarks`, `/benchmarks/new`, … | Public benchmarks (TruthfulQA, IFEval, …) |
| `/safety`, `/safety/new`, … | Inference safety |

Each pillar has `/<slug>/status` JSON for in-progress polling.

## Populate data

| Pillar | Browser | CLI |
|--------|---------|-----|
| Scan | `/scans/new` | `scanner scan <hf_id>` |
| Efficacy | `/eval-run/new` | `evaluator/runner.py` |
| Benchmarks | `/benchmarks/new` | `benchmarks/run_benchmark.py` |
| Safety | `/safety/new` | `./safety/run_safety.sh` |

## Layout

| Module | Role |
|--------|------|
| [`gateway/`](../gateway/) | Live catalog for `/models` and dropdowns |
| `*_data.py` / `*_launch.py` | Read results + spawn Docker/host subprocess |
| `docker_launch.py` | Shared Docker helper (root `.env`, UID/GID, `docker compose build`) |
| `routes.py`, `templates/`, `static/` | UI |

## Browser-launched runs

Docker Compose by default. Every stack reads the repo-root `.env` (one gateway token); `docker_launch.py` exports the host UID/GID and builds the image once per stack.

| Pillar | Compose | Service |
|--------|---------|---------|
| Scan | `scanner/docker/compose.yml` | `scanner` |
| Safety | `safety/docker/compose.yml` | `safety` |
| Eval | `evaluator/docker/compose.yml` | `evaluator` |
| Benchmarks | `benchmarks/docker/compose.yml` | `benchmarks` |

Set `FRONTEND_LAUNCH_MODE=host` for host Python (unit tests, debugging).

## Related docs

- [`docs/architecture.md`](../docs/architecture.md)
- [`benchmarks/README.md`](../benchmarks/README.md)
- [`scanner/README.md`](../scanner/README.md)
- [`safety/README.md`](../safety/README.md)
- [`evaluator/README.md`](../evaluator/README.md)
