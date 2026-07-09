# Frontend (`frontend/`)

Nutrition-label **UI and JSON API** (one Flask process). Browser **Start** buttons and `POST /api/*` spawn pillar jobs in Docker via [`docker_launch.py`](docker_launch.py). When a DSN is reachable, reads come **only from Postgres**; disk JSON is the offline fallback when no DSN is set. Permanent deletes remove both the DB row and VM artifacts.

**Auth:** Public view (default) needs no login. Private view and custom runs require an allowlisted Duke netID — [`../auth/README.md`](../auth/README.md).

## Quick start

### One-time setup

```bash
uv sync --group dev
cp .env.example .env             # DUKE_GATEWAY_KEY required
./docker/build-pillars.sh        # pillar images for Start buttons
```

Postgres schema and backfill (optional): see [root README — Optional Postgres](../README.md#optional--postgres).

### Run (containerized — default)

See [`docs/docker.md`](../docs/docker.md).

```bash
python3 main.py                   # or: ./docker/run.sh up --build
python3 main.py up -d --build     # background
```

Open http://127.0.0.1:5000.

Launch pages: `/scans/new`, `/safety/new`, `/eval-run/new`, `/benchmarks/new` — gateway dropdowns on each form. Benchmark model-input options (Gateway / Hosted / Custom): [`benchmarks/README.md`](../benchmarks/README.md).

Cross-pillar pages: `/models` (catalog + aggregate ranking), `/models/<slug>` (detail + AI/rules recommendations), `/compare?models=slug1,slug2` (head-to-head charts). API: `GET /api/models`, `GET /api/models/<slug>` — see [`../api/README.md`](../api/README.md).

Pillar list pages use **List / Compare** tabs (suite×model or tool×model matrices). Stale rows show an orange **!** (hover for why); up-to-date rows show nothing. **Rerun** (filled when stale) and **Delete** sit on each row. Rules live in [`staleness.py`](staleness.py) — see [Staleness indicators](#staleness-indicators) below. Reference guides: `/safety/reference`, `/eval-run/reference`, `/scans/reference`, `/benchmarks/reference`.

## Modules

| Module | Role |
|--------|------|
| `model_rollup.py` | Cross-pillar union for catalog, API, compare (batch lookup + TTL cache) |
| `model_identity.py` | Gateway slug / HF repo id normalization |
| `model_summary.py` | Gateway-backed AI summaries (cached); rules-v1 fallback |
| `recommendation_rules.py` | Rules-v1 analyst summaries (fallback) |
| `reference_constants.py` | Preferred reference model ordering |
| `staleness.py` | Per-pillar “needs rerun” rules; constants `CURRENT_SPEC_CUTOFF`, `SAFETY_EXPECTED_GARAK_PROBES` |
| `oss_gateway_hf.py` | HF mirror repos for open-weight gateway models → catalog scan rollup |
| `delete_db.py` | DB-delete error surfacing for permanent deletes |
| `db_fallback.py` | Postgres-only when DSN reachable; disk fallback offline only |
| `launch_registry.py` | Shared in-flight job liveness |
| `docker_launch.py` | Browser-launched pillar Docker stacks |
| `static/pillar-view-tabs.js` | List/Compare tab toggle on pillar pages |
| `static/compare-panel.js` | Catalog model checkbox compare |
| `static/findings-table.js` | Filterable findings tables |
| `static/log-scroll.js` | Auto-scroll run logs |
| `static/table-sort.js` | Client-side table sort |
| `static/vendor/chart.umd.min.js` | Chart.js for `/compare` |

While a job runs, its detail page polls status and shows a live log tail.

Header: **Public | Private** view toggle · **Sign in with Duke NetID** (when `AUTH_ENABLED=1`).

### Auth (local dev)

```bash
# .env — no Duke OAuth required
AUTH_ENABLED=0
AUTH_DEV_NETID=yournetid
AUTH_ALLOWED_NETIDS=yournetid

curl -s localhost:5000/auth/me | python3 -m json.tool
```

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
- **Stale safety `run.lock`** — if a container died mid-run, the UI marks the job `failed` and releases the lock when the log shows completion or errors without a live holder.
- **Partial Garak** — incomplete Garak scans are omitted from merge; detail may show `garak_subset_v1` in `missing_suites` or a partial-Garak warning.
- **`POST /api/scans` → 503** (cannot write) — root-owned output from an old run. On the application VM (no sudo needed):

  ```bash
  docker run --rm -v "$PWD/scanner/output:/out" -u root busybox \
    chown -R "$(id -u):$(id -g)" /out
  ```

- **`db_available: false`** — check `POSTGRES_DSN`, schema apply, and network ([`docs/cli.md`](../docs/cli.md)).
- **“Docker is required for browser-launched … runs”** — often a UID mismatch on `.docker-home` after CI deploy, or a stale web process. See [`docker/README.md`](../docker/README.md#troubleshooting). Quick fix: `./docker/run.sh up -d --force-recreate`.
- **Skip Docker for jobs** — `FRONTEND_LAUNCH_MODE=host` in `.env` (legacy; safety may still use nested Docker).

## See also

- [`../README.md`](../README.md) · [`docs/cli.md`](../docs/cli.md) · [`docs/docker.md`](../docs/docker.md) · [`../api/README.md`](../api/README.md)
