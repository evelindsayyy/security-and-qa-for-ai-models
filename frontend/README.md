# Frontend (`frontend/`)

Nutrition-label UI. Reads JSON from pillar output dirs; supports **browser-launched runs** (Docker + polling).

Planned: read from Postgres via `api/`. Today: `scanner/output/`, `safety/output/`, `evaluator/results/`, `benchmarks/results/`.

## Run

**Local (fastest):**

```bash
uv sync
uv run flask --app frontend:create_app run --debug
```

Launch pages: `/scans/new` · `/safety/new` · `/eval-run/new` · `/benchmarks/new`

Set `FRONTEND_LAUNCH_MODE=host` to skip Docker for launches (debugging, unit tests).

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
| `*_data.py` / `*_launch.py` | Read results + spawn Docker/host subprocess |
| `docker_launch.py` | Shared Docker helper (`.env`, UID/GID, compose build) |
| `routes.py`, `templates/`, `static/` | UI |

## Related docs

- [`docs/architecture.md`](../docs/architecture.md)
- [`docs/docker.md`](../docs/docker.md)
- Pillar READMEs: [`scanner/`](../scanner/README.md) · [`safety/`](../safety/README.md) · [`evaluator/`](../evaluator/README.md) · [`benchmarks/`](../benchmarks/README.md)
