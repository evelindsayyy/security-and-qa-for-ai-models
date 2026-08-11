# CLI reference

All commands run from the **repo root**.

On the host shell (application VM or dev workstation), use **`python3`** — many Ubuntu images do not provide a `python` shim. Inside pillar containers, `python` is fine.

## First-time setup

### Containerized UI (default)

Recommended for local dev and the application VM. Pillar jobs run in Docker; host only needs `uv` for setup commands.

```bash
uv sync --group dev
cp .env.example .env   # DUKE_GATEWAY_KEY required; POSTGRES_DSN when DB is configured
./docker/build-pillars.sh
python3 main.py         # same as ./docker/run.sh up --build
# Or: uv run python main.py
```

Open `http://127.0.0.1:5000`. See [`../README.md`](../README.md#quick-start) for the full step list.

### Development alternative — host Flask

UI without containerizing the app (pillar jobs still use Docker unless `FRONTEND_LAUNCH_MODE=host`):

```bash
uv sync --group dev
cp .env.example .env
uv run flask --app frontend:create_app run --debug --port 5001
```

For live CSS/TS during host Flask dev, run the Vite watcher in a second terminal:

```bash
cd frontend/assets && npm ci && npm run dev
```

### Frontend assets

Vite + Preact + Tailwind under `frontend/assets/`. Output: `frontend/static/dist/` (gitignored).

```bash
cd frontend/assets
npm ci
npm run build       # production → ../static/dist/
npm run dev         # watch (pair with host Flask)
npm run test        # Vitest
# Or: ./scripts/build-frontend.sh
```

**Resolution:** `docker/run.sh` builds on the host before start (dev). The web
image bakes assets at `/opt/frontend-dist` (CI `frontend-build` + `build-web-image`).
`frontend/vite_assets.py` serves working-tree first, image bake as fallback. The
Dockerfile copies `frontend/templates/` so Tailwind scans template classes.

### Optional — Postgres (one-time)

When `POSTGRES_DSN` is reachable from the application VM (or VPN). Set `EFFICACY_DB_DSN` to the same DSN.

```bash
./scripts/apply-schemas.sh --bootstrap
# Auth backfill (one-time, after apply-schemas):
uv run python db/migrate_auth_columns.py --apply
# Or one file: uv run python -m dbutils.apply_schema scanner/db/scan_schema.sql
```

Verify: `curl -s localhost:5000/api/health | python3 -m json.tool` → `db_available: true`.

**Data flow:** runs write JSON → auto-sync to Postgres (default) → UI/API read Postgres first. Set `AUTO_INGEST=0` to disable.

### Optional — authentication (OIDC)

Deploy code first with `AUTH_ENABLED=0`. Auth details: [`../auth/README.md`](../auth/README.md).

```bash
# After OAuth client is registered on the VM .env:
AUTH_ENABLED=1
SECRET_KEY=<random hex>
DUKE_OIDC_CLIENT_ID=...
DUKE_OIDC_CLIENT_SECRET=...
# Leave DUKE_OIDC_REDIRECT_URI blank — inferred from CADDY_DOMAIN or request host
AUTH_ALLOWED_NETIDS=netid1,netid2

# Local dev without Duke login:
AUTH_ENABLED=0
AUTH_DEV_NETID=yournetid
AUTH_ALLOWED_NETIDS=yournetid
```

```bash
curl -s localhost:5000/auth/me | python3 -m json.tool
```

### Optional — pillar deps on the host

Only for running a pillar CLI **without** Docker. Groups **`scanner`**, **`safety`**, and **`benchmarks` are mutually exclusive** — pick **one**:

```bash
uv sync --group dev --group scanner      # artifact scanning on host
uv sync --group dev --group safety       # garak on host
uv sync --group dev --group benchmarks   # benchmark runners on host
```

For the Docker model, see [`docker.md`](docker.md) and [Web UI](#web-ui-containerized) below.

## Web UI (containerized)

Entry points (equivalent): **`./docker/run.sh`**, **`python3 main.py`**, **`uv run python main.py`**.

All use Compose project **`qa-ai-models`**, load `.env`, auto-detect host UID/GID and repo path, and build frontend assets before start. See [`docker/README.md`](../docker/README.md).

| Action | Command |
|--------|---------|
| Start (foreground) | `… up --build` — bare `main.py` defaults to this |
| Start (background) | `… up -d --build` |
| After code changes | `… restart` |
| Stop | `… down` |
| Logs | `… logs -f web` |

`restart` runs `down`, then `up -d --build --force-recreate --remove-orphans`.

**One-time:** `./docker/build-pillars.sh`. **`APP_PORT`** in `.env` (default `5000`). With **`CADDY_DOMAIN`** set, `run.sh` adds `compose.caddy.yml` for HTTPS.

### Host Flask (UI only)

```bash
uv run python main.py --host
APP_PORT=5001 uv run python main.py --host   # alternate port
cd frontend/assets && npm run dev            # live assets (second terminal)
```

Pillar jobs still use Docker unless `FRONTEND_LAUNCH_MODE=host`.

## Remote access

| Host | SSH |
|------|-----|
| Application VM | `ssh <netid>@model-advisor.colab.duke.edu` |
| DGX (optional dev) | `ssh <netid>@<dgx-host>` |
| DCC (vLLM) | [`scripts/dcc/README.md`](../scripts/dcc/README.md) |

After login:

```bash
cd security-and-qa-for-ai-models
git pull && ./docker/run.sh restart
curl -s http://127.0.0.1:5000/api/health | python3 -m json.tool
```

**Port forward** when the UI is on localhost only:

```bash
ssh -L 5000:localhost:5000 <netid>@<host>
```

Open `http://localhost:5000`. OIDC redirect URIs: [`auth/README.md`](../auth/README.md).

## JSON API

Same Flask app as the UI. See [`api/README.md`](../api/README.md).

```bash
# Health — expect db_available: true when DSN + schemas are configured
curl -s localhost:5000/api/health | python3 -m json.tool

# List + start a scan (202 + status_url)
curl -s localhost:5000/api/scans | python3 -m json.tool
curl -s -X POST localhost:5000/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"hf_repo":"distilbert-base-uncased"}' | python3 -m json.tool
curl -s localhost:5000/api/scans/distilbert-base-uncased/status | python3 -m json.tool

# Safety, eval, benchmark — POST bodies in api/README.md
curl -s localhost:5000/api/safety | python3 -m json.tool
curl -s localhost:5000/api/evals | python3 -m json.tool
curl -s localhost:5000/api/benchmarks | python3 -m json.tool
```

If `POST /api/scans` returns **503** with “cannot write”, output is often root-owned from an old Docker run. On the application VM (or any host without sudo):

```bash
docker run --rm -v "$PWD/scanner/output:/out" -u root busybox \
  chown -R "$(id -u):$(id -g)" /out
```

Scanner model weights use the named volume `qa-ai-models_scanner_models`. If a scan fails with **Permission denied** under `/app/scanner/models`, fix ownership once (replace `1002` with the repo owner's uid/gid — usually `stat -c '%u' .`):

```bash
docker run --rm -v qa-ai-models_scanner_models:/models -u root busybox \
  sh -c 'mkdir -p /models && chown -R 1002:1002 /models'
```

Then rebuild the scanner image (`./docker/build-pillars.sh` or restart the stack) so the entrypoint keeps the volume owned correctly.

## Pillar jobs

Browser "Start" buttons run these for you. To run them directly, set the file
owner once so outputs are not root-owned:

```bash
export HOST_UID=$(id -u) HOST_GID=$(id -g)   # web stack (docker/run.sh sets these automatically)
# Pillar stacks use UID/GID — do not `export UID` in bash (readonly); use ./docker/build-pillars.sh
# or: env UID=$(id -u) GID=$(id -g) docker compose …
```

```bash
# Scan an HF repo -> scanner/output/<slug>/scan_result.json (+ auto-ingest)
env UID=$(id -u) GID=$(id -g) \
  docker compose --env-file .env -f scanner/docker/compose.yml run --rm scanner \
  python -m scanner scan gpt2

# Safety -> safety/output/<slug>/<profile>/merged_safety_result.json
uv run python -m safety.run "GPT 4.1 Mini"
# Thin wrapper (same): ./safety/run_safety.sh "GPT 4.1 Mini"

# Safety via Docker orchestrator (matches browser / UI path)
env UID=$(id -u) GID=$(id -g) DOCKER_GID=$(stat -c '%g' /var/run/docker.sock) \
  docker compose --env-file .env -f safety/docker/compose.yml run --rm safety \
  python -m safety.run "GPT 4.1 Mini"

# Efficacy (LLM-as-judge) -> evaluator/results/*.jsonl
env UID=$(id -u) GID=$(id -g) \
  docker compose --env-file .env -f evaluator/docker/compose.yml run --rm evaluator \
  python runner.py --candidate-model "GPT 4.1 Mini" --judge-model "Llama 4 Maverick"

# Public benchmark -> benchmarks/results/
env UID=$(id -u) GID=$(id -g) \
  docker compose --env-file .env -f benchmarks/docker/compose.yml run --rm benchmarks \
  python run_benchmark.py --benchmark truthfulqa --model "GPT 4.1 Mini"

# Personality (Big Five Inventory) -> personality/results/
env UID=$(id -u) GID=$(id -g) \
  docker compose --env-file .env -f personality/docker/compose.yml run --rm personality \
  python run_personality.py --model "GPT 4.1 Mini"
```

Per-pillar flags and host-only paths: [`scanner/`](../scanner/README.md) ·
[`safety/`](../safety/README.md) · [`evaluator/`](../evaluator/README.md) ·
[`benchmarks/`](../benchmarks/README.md) · [`personality/`](../personality/README.md).

### Concurrent runs and locks

| Pillar | Lock location | CLI if already running |
|--------|---------------|------------------------|
| Scan | `scanner/output/<slug>/run.lock` | exit **2** |
| Safety | `safety/output/<slug>/<profile>/run.lock` | exit **2** |
| Benchmark | `benchmarks/results/<stem>.run.lock` | UI only (no CLI lock yet) |
| Personality | `personality/results/<stem>.lock` | UI only |
Scan and safety start forms show a warning when that model/repo is already in progress.

**Stale locks:** removed when the holder PID is dead. Safety UI also treats orphaned locks as `failed` when the log shows `Complete:` or errors without a live process. Delete `run.lock` manually after `kill -9` if needed.

**Garak (safety):** Duke 14 `probe_spec` queues 14 yaml entries → ~13 exported module findings (`dan.*` rolls up). Incomplete reports (no `completion` entry or fewer modules) fail export/merge — `garak_subset_v1` appears in `missing_suites`.

Historical scan rows may show pre-change `overall_risk_score` values (clean scans now score **0**; benign gpt2-style pickles stay **18**).

## Gateway catalog

```bash
uv run python -m gateway          # grouped listing
uv run python -m gateway --json   # machine-readable
```

## Tests and lint (matches CI)

```bash
uv sync --frozen --group dev
cd frontend/assets && npm ci && npm run build && npm run test
uv run ruff check .
uv run python -m unittest discover -s unit_tests -v
```

## Build images

```bash
docker compose --project-name qa-ai-models -f docker/compose.yml build
docker compose --project-name qa-ai-models -f scanner/docker/compose.yml build
```

The web image can also be smoke-tested locally with Buildah:

```bash
STORAGE_DRIVER=vfs buildah bud --isolation=chroot -f docker/Dockerfile -t localhost/qa-ai-web:buildah-smoke .
```

## Postgres ingest

Set real credentials in ``.env`` (not the ``YOUR_USER`` placeholders). Use ``?sslmode=require``.

**Auto-sync:** each successful pillar run syncs into Postgres (best-effort; never fails the job). Disable with ``AUTO_INGEST=0``.

```bash
# Verify connectivity and per-pillar DB read paths (container default port 5000)
curl -s localhost:5000/api/health | python3 -m json.tool

# Bulk backfill / dry-run
uv run python -m api.ingest
uv run python -m api.ingest --apply
uv run python -m api.ingest bootstrap --apply   # all pillars + summary line
uv run python -m api.ingest --personality --apply
```

Schema and per-pillar loaders: [`scanner/db/README.md`](../scanner/db/README.md),
[`safety/db/README.md`](../safety/db/README.md),
[`evaluator/db/README.md`](../evaluator/db/README.md),
[`benchmarks/db/README.md`](../benchmarks/db/README.md),
[`personality/db/`](../personality/db/) (`personality_schema.sql`, `load_personality.py`).

## DCC vLLM (open-weight inference)

For **open-source models** served on the Duke Compute Cluster instead of the gateway.
**Today:** evaluator CLI only (`--candidate-endpoint`, `--inference-backend dcc`).
**Planned:** safety and benchmarks via the same endpoint override pattern.

```bash
uv run python -m scripts.dcc.vllm start --model Qwen/Qwen2.5-7B-Instruct
uv run python -m scripts.dcc.vllm wait
uv run python -m scripts.dcc.vllm status
uv run python -m scripts.dcc.vllm stop
```

Thin wrappers: `./scripts/dcc/start_vllm.sh`, etc. See [`scripts/dcc/README.md`](../scripts/dcc/README.md).

## Application VM setup

Production runs on **model-advisor.colab.duke.edu**. UI, pillar jobs, and ingest
run on this host.

```bash
git clone <repo-url> && cd security-and-qa-for-ai-models
cp .env.example .env
# Edit .env: gateway key, Postgres DSNs, and production HTTPS:
#   CADDY_DOMAIN=model-advisor.colab.duke.edu
#   TRUST_PROXY=1

uv sync --group dev
./docker/build-pillars.sh
./scripts/apply-schemas.sh --bootstrap
uv run python db/migrate_auth_columns.py --apply   # one-time

uv run python main.py up -d --build
curl -s http://127.0.0.1:5000/api/health | python3 -m json.tool
curl -s https://model-advisor.colab.duke.edu/api/health | python3 -m json.tool
```

**Ongoing updates:** GitHub Actions deploy (preferred) or `git pull && ./docker/run.sh restart`.
Enable OIDC when ready: [`auth/README.md`](../auth/README.md).
