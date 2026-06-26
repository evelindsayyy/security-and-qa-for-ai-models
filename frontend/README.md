# Frontend (`frontend/`)

Nutrition-label **UI and JSON API** (one Flask process). Browser **Start** buttons and `POST /api/*` spawn pillar jobs in Docker via [`docker_launch.py`](docker_launch.py). Reads use Postgres when configured, else on-disk JSON.

## Quick start

### One-time setup

```bash
uv sync --group dev
cp .env.example .env             # DUKE_GATEWAY_KEY required
./docker/build-pillars.sh        # pillar images for Start buttons
```

Postgres schema and backfill (optional): see [root README — Optional Postgres](../README.md#optional--postgres).

### Run (containerized — default)

**Containerized (application VM):** [`docs/docker.md`](../docs/docker.md).
=======
```bash
python3 main.py                   # or: ./docker/run.sh up --build
python3 main.py up -d --build     # background
```

Open http://127.0.0.1:5000 · launch pages: `/scans/new` · `/safety/new` · `/eval-run/new` · `/benchmarks/new`

### Benchmark model sources (`/benchmarks/new`)

Three ways to pick a model — the form shows a setup guide that changes with your
selection. Full reference: [`benchmarks/README.md`](../benchmarks/README.md#model-input-cheat-sheet).

| Source | Model input example |
|--------|---------------------|
| Gateway | `GPT 4.1 Mini` (dropdown) |
| Hosted (HF Inference) | `meta-llama/Llama-3.1-8B-Instruct` + `hf_…` token |
| Custom (self-hosted API) | `my-finetune-v2` + `http://localhost:8080/v1` |

### JSON API

Same data as the UI. Full routes: [`../api/README.md`](../api/README.md).

```bash
curl -s localhost:5000/api/health | python3 -m json.tool
curl -s localhost:5000/api/scans | python3 -m json.tool
curl -s -X POST localhost:5000/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"hf_repo":"distilbert-base-uncased"}' | python3 -m json.tool
curl -s localhost:5000/api/scans/distilbert-base-uncased/status | python3 -m json.tool
```

POST returns **202** with `job_id` and `status_url`; poll status, then GET detail.

### Host Flask (development)

UI without containerizing the app; pillar jobs still use Docker unless `FRONTEND_LAUNCH_MODE=host`:

```bash
python3 main.py --host
# Or: uv run flask --app frontend:create_app run --debug --port 5001
```

## Troubleshooting

- **Host has no `python` command** — use `python3 main.py` or `./docker/run.sh` (see [`docs/cli.md`](../docs/cli.md)).
- **Promptfoo “config not found” / empty eval.json** — missing `HOST_REPO`. `./docker/run.sh` sets it; browser launches pass it via `docker_launch.py`.
- **Garak `run config not found: tmp*.yaml`** — redeploy after fix in `run_garak.py` (absolute config path).
- **`POST /api/scans` → 503** (cannot write) — root-owned output from an old run. On the application VM (no sudo needed):

  ```bash
  docker run --rm -v "$PWD/scanner/output:/out" -u root busybox \
    chown -R "$(id -u):$(id -g)" /out
  ```

- **`db_available: false`** — check `POSTGRES_DSN`, schema apply, and network ([`docs/cli.md`](../docs/cli.md)).
- **Skip Docker for jobs** — `FRONTEND_LAUNCH_MODE=host` in `.env` (legacy; safety may still use nested Docker).

## See also

- [`../README.md`](../README.md) · [`docs/cli.md`](../docs/cli.md) · [`docs/docker.md`](../docs/docker.md) · [`../api/README.md`](../api/README.md)
