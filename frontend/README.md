# Frontend (`frontend/`)

Nutrition-label **UI and JSON API** (one Flask process). Browser **Start** buttons and `POST /api/*` spawn pillar jobs in Docker via [`docker_launch.py`](docker_launch.py). Reads use Postgres when configured, else on-disk JSON.

**Auth:** Public view (default) needs no login. Private view and custom runs require an allowlisted Duke netID — [`docs/auth-setup.md`](../docs/auth-setup.md) · [`../auth/README.md`](../auth/README.md).

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

While a job runs, its detail page polls status and shows a live log tail. Scan and safety start forms warn when the same model/repo is already in progress (`run.lock` under the output dir).

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
- **“Docker is required for browser-launched … runs”** — usually a transient daemon check or a stale web process after deploy. Deploys force-recreate the web container; for a one-off fix: `./docker/run.sh up -d --build`. If it keeps happening, verify socket access: `stat -c '%g' /var/run/docker.sock` should match the web container `group_add` (`DOCKER_GID` from `./docker/run.sh`).
- **Skip Docker for jobs** — `FRONTEND_LAUNCH_MODE=host` in `.env` (legacy; safety may still use nested Docker).

## See also

- [`../README.md`](../README.md) · [`docs/cli.md`](../docs/cli.md) · [`docs/auth-setup.md`](../docs/auth-setup.md) · [`docs/docker.md`](../docs/docker.md) · [`../api/README.md`](../api/README.md)
