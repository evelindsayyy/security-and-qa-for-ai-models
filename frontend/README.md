# Frontend (`frontend/`)

Nutrition-label UI and JSON API (same Flask process). Each pillar reads via `*_data.py` (Postgres when configured, artifact fallback). **Start** buttons and `POST /api/*` spawn jobs through `*_launch.py` and [`docker_launch.py`](docker_launch.py).

## Quick start

```bash
uv sync
cp .env.example .env          # DUKE_GATEWAY_KEY / OPENAI_API_KEY
uv run flask --app frontend:create_app run --debug --port 5001
```

Open http://127.0.0.1:5001 · launch pages: `/scans/new` · `/safety/new` · `/eval-run/new` · `/benchmarks/new`

## JSON API

Mounted at `/api` — same data as the UI. Full route list: [`../api/README.md`](../api/README.md).

```bash
curl -s localhost:5001/api/health | python3 -m json.tool
curl -s localhost:5001/api/scans | python3 -m json.tool
curl -s -X POST localhost:5001/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"hf_repo":"distilbert-base-uncased"}' | python3 -m json.tool
curl -s localhost:5001/api/scans/distilbert-base-uncased/status | python3 -m json.tool
```

POST returns **202** with `job_id` and `status_url`; poll status, then GET detail.

## Launch modes

| UI runs on | `FRONTEND_LAUNCH_MODE` | Job execution |
|------------|------------------------|---------------|
| Host (`uv run flask`) | `docker` (default) | Docker on host daemon |
| Host | `host` | Host scripts (`./safety/run_safety.sh`, etc.) |
| `./docker/run.sh` (VM) | `docker` (default) | Docker via mounted socket |

Browser/API launches set `HOST_REPO`, `UID`, `GID`, and `DOCKER_GID` automatically ([`docker_launch.py`](docker_launch.py)).

## One-time Docker setup

Required for default browser/API launches (host Flask + Docker jobs):

```bash
docker compose version
export HOST_REPO="$(pwd)" UID=$(id -u) GID=$(id -g)
export DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)

docker compose --env-file .env -f scanner/docker/compose.yml build
docker compose --env-file .env -f safety/docker/compose.yml build
docker compose --env-file .env -f evaluator/docker/compose.yml build
docker compose --env-file .env -f benchmarks/docker/compose.yml build
```

Containerized UI (application VM): [`../docker/run.sh`](../docker/run.sh) sets `HOST_REPO` for you.

## Routes

| Route | Purpose |
|-------|---------|
| `/` | Hub |
| `/models` | Gateway catalog |
| `/scans`, `/scans/new`, `/scans/<slug>` | HF scanning |
| `/safety`, `/safety/new`, `/safety/<slug>/<profile>` | Safety (`/safety/<slug>` → `/base`) |
| `/eval-run`, `/eval-run/new`, … | Efficacy |
| `/benchmarks`, `/benchmarks/new`, … | Benchmarks |

Each pillar: UI status routes and matching `/api/.../status` for polling.

## Layout

| Module | Role |
|--------|------|
| [`gateway/`](../gateway/) | Live catalog |
| `*_data.py` / `*_db_data.py` | Pillar list + detail |
| `*_launch.py` | Browser/API subprocess spawn |
| [`output_dirs.py`](output_dirs.py) | Wipe + writability checks before runs |
| `docker_launch.py` | Shared compose helper |
| [`../api/`](../api/) | JSON REST blueprints |
| `routes.py`, `templates/`, `static/` | HTML UI |

## Troubleshooting

- **Promptfoo “config not found” from UI safety run** — orchestrator missing `HOST_REPO`. Browser launches set it; manual `docker compose … safety` needs `export HOST_REPO="$(pwd)"`.
- **Permission errors on output dirs (`POST /api/scans` → 503)** — old Docker runs may leave root-owned files under `scanner/output/<slug>/`. On DGX you often **cannot use sudo**; fix ownership via Docker from the repo root:

  ```bash
  docker run --rm -v "$PWD/scanner/output:/out" -u root busybox \
    chown -R "$(id -u):$(id -g)" /out/gpt2
  # whole scanner tree:
  docker run --rm -v "$PWD/scanner/output:/out" -u root busybox \
    chown -R "$(id -u):$(id -g)" /out
  ```

  Same pattern works for `safety/output`, etc. **Prevent recurrence:** `export UID=$(id -u) GID=$(id -g)` before compose runs (browser/API launches set this automatically).
- **Skip Docker for jobs** — `FRONTEND_LAUNCH_MODE=host` (safety still uses Promptfoo/Garak Docker unless you run suites manually).
- **`db_available: false` on DGX** — expected without VPN/Postgres; API reads still work from disk JSON.

## See also

- [`docs/docker.md`](../docs/docker.md) · [`docs/cli.md`](../docs/cli.md) · [`api/README.md`](../api/README.md)
- Pillar READMEs: [`scanner/`](../scanner/README.md) · [`safety/`](../safety/README.md) · [`evaluator/`](../evaluator/README.md) · [`benchmarks/`](../benchmarks/README.md)
