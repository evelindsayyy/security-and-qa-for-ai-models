# Frontend (`frontend/`)

AI Model Advisor **UI and JSON API** (one Flask process). Browser **Start** buttons
and `POST /api/*` spawn pillar jobs via [`docker_launch.py`](docker_launch.py).
Reads use Postgres when configured, else on-disk JSON.

## Quick start

```bash
uv sync --group dev
cp .env.example .env
./docker/build-pillars.sh
python3 main.py up -d --build    # default; builds assets via run.sh
```

Open http://127.0.0.1:5000. Launch pages: `/scans/new` · `/safety/new` ·
`/eval-run/new` · `/benchmarks/new`.

While a job runs, detail pages poll status and show a live log tail. Scan and
safety start forms warn when the same model/repo is already in progress.

## UI stack

Server-rendered **Jinja** templates + **Preact** islands (Vite, TypeScript, Tailwind 3).

| Layer | Path |
|-------|------|
| Templates | `frontend/templates/` |
| Styles | `frontend/assets/src/styles/app.css` + Tailwind |
| Islands | `frontend/assets/src/islands/` |
| Built bundle | `frontend/static/dist/` (gitignored) |

[`vite_assets.py`](vite_assets.py) resolves hashed bundle URLs and serves
`/static/dist/*` from the working-tree build when present, else `/opt/frontend-dist`
from the image.

```bash
cd frontend/assets
npm ci && npm run build    # → ../static/dist/
npm run dev                # watch (pair with python3 main.py --host)
npm run test               # Vitest
```

`docker/run.sh` runs `scripts/build-frontend.sh` before container start. CI
`frontend-build` job produces the image bake.

### Islands

| Island | Role |
|--------|------|
| `FindingsPanel` | Filterable findings on detail pages |
| `ComparisonHeatmap` | Pillar list/compare matrices |
| `LiveRunProgress` | Run progress + log tail |
| `CompareCharts` | Charts on `/compare` |

### Key routes

| Area | Routes |
|------|--------|
| Overview | `/` |
| Catalog / compare | `/models`, `/compare`, `/models/<slug>` |
| Pipeline | `/pipeline` |
| Pillars | `/scans`, `/safety`, `/eval-run`, `/benchmarks` + detail/new pages |
| Extras | `/personality` + detail/new (Big Five Inventory; not in rollup) |

Header: **Public | Private** toggle · **Sign in with Duke NetID** when `AUTH_ENABLED=1`.

## Modules

| Module | Role |
|--------|------|
| `routes.py` | Flask routes |
| `model_rollup.py` | Cross-pillar catalog/compare data |
| `model_findings.py` | Top findings for model detail |
| `overview.py` | Overview KPIs + activity |
| `pipeline.py` | Cross-pillar gating view |
| `vite_assets.py` | Vite manifest + static dist serving |
| `docker_launch.py` | Browser-launched pillar Docker stacks |
| `db_fallback.py` | Postgres-first reads; disk when offline |
| `staleness.py` | Per-pillar needs-rerun rules |
| `run_paths.py` | Public/private path scoping |

## Benchmark model sources (`/benchmarks/new`)

| Source | Example input |
|--------|---------------|
| Gateway | `GPT 4.1 Mini` (dropdown) |
| Hosted (HF Inference) | `meta-llama/Llama-3.1-8B-Instruct` + token |
| Custom API | `my-model` + `http://host:8080/v1` |

See [`benchmarks/README.md`](../benchmarks/README.md).

## Auth (local dev)

```bash
# .env — no Duke OAuth required
AUTH_ENABLED=0
AUTH_DEV_NETID=yournetid
AUTH_ALLOWED_NETIDS=yournetid

curl -s localhost:5000/auth/me | python3 -m json.tool
```

Production OIDC: [`auth/README.md`](../auth/README.md).

## JSON API

Same data as the UI. Routes: [`api/README.md`](../api/README.md).

```bash
curl -s localhost:5000/api/health | python3 -m json.tool
curl -s localhost:5000/api/scans | python3 -m json.tool
curl -s -X POST localhost:5000/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"hf_repo":"distilbert-base-uncased"}' | python3 -m json.tool
```

POST returns **202** with `job_id` and `status_url`.

## Host Flask (development)

UI without containerizing the app; pillar jobs still use Docker by default.

```bash
cd frontend/assets && npm run dev    # terminal 1
python3 main.py --host               # terminal 2
```

## Troubleshooting

- **Unstyled UI** — run `npm run build` or restart via `python3 main.py up -d --build`; on VM use CI deploy. See [`docker/README.md`](../docker/README.md).
- **Docker required for Start** — `.docker-home` UID mismatch or stale web process; `./docker/run.sh up -d --force-recreate`.
- **`db_available: false`** — check `POSTGRES_DSN`, schema apply, network ([`cli.md`](../docs/cli.md)).
- **503 on POST /api/scans** — root-owned `scanner/output`; see [`cli.md`](../docs/cli.md).

## See also

[`README.md`](../README.md) · [`docs/cli.md`](../docs/cli.md) · [`docs/docker.md`](../docs/docker.md) · [`api/README.md`](../api/README.md)
