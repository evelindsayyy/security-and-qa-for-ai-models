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
```

Open `http://127.0.0.1:5000`. See [`../README.md`](../README.md#quick-start) for the full step list.

### Development alternative — host Flask

UI without containerizing the app (pillar jobs still use Docker unless `FRONTEND_LAUNCH_MODE=host`):

```bash
uv sync --group dev
cp .env.example .env
uv run flask --app frontend:create_app run --debug --port 5001
```

### Optional — Postgres (one-time)

When `POSTGRES_DSN` is reachable from the application VM (or VPN). Set `EFFICACY_DB_DSN` to the same DSN.

```bash
./scripts/apply-schemas.sh --bootstrap
# Or one file: uv run python -m dbutils.apply_schema scanner/db/scan_schema.sql
```

Verify: `curl -s localhost:5000/api/health | python3 -m json.tool` → `db_available: true`.

**Data flow:** runs write JSON → auto-sync to Postgres (default) → UI/API read Postgres first. Set `AUTO_INGEST=0` to disable.

### Optional — pillar deps on the host

Only for running a pillar CLI **without** Docker. Groups **`scanner`**, **`safety`**, and **`benchmarks` are mutually exclusive** — pick **one**:

```bash
uv sync --group dev --group scanner      # artifact scanning on host
uv sync --group dev --group safety       # garak on host
uv sync --group dev --group benchmarks   # benchmark runners on host
```

For the Docker model, see [`docker.md`](docker.md).

## Web UI

```bash
# Default — containerized (auto-detects user, Docker group, repo path)
python3 main.py                   # foreground (up --build)
python3 main.py up -d --build     # background
python3 main.py down              # stop
python3 main.py logs -f web       # logs
# Equivalent: ./docker/run.sh …

# Development — host Flask only (port 5001 avoids clash with container on 5000)
python3 main.py --host
# Or: uv run flask --app frontend:create_app run --debug --port 5001
```

Set `APP_PORT` in `.env` to change the container port. One-time pillar builds: `./docker/build-pillars.sh`.

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
docker compose --env-file .env -f scanner/docker/compose.yml run --rm scanner \
  python -m scanner scan gpt2

# Safety red-team -> safety/output/<slug>/<profile>/merged_safety_result.json
uv run python -m safety.run "GPT 4.1 Mini"
# Thin wrapper (same): ./safety/run_safety.sh "GPT 4.1 Mini"

# Efficacy (LLM-as-judge) -> evaluator/results/*.jsonl
docker compose --env-file .env -f evaluator/docker/compose.yml run --rm evaluator \
  python runner.py --candidate-model "GPT 4.1 Mini" --judge-model "Llama 4 Maverick"

# Public benchmark -> benchmarks/results/
docker compose --env-file .env -f benchmarks/docker/compose.yml run --rm benchmarks \
  python run_benchmark.py --benchmark truthfulqa --model "GPT 4.1 Mini"
```

Per-pillar flags and host-only paths: [`scanner/`](../scanner/README.md) ·
[`safety/`](../safety/README.md) · [`evaluator/`](../evaluator/README.md) ·
[`benchmarks/`](../benchmarks/README.md).

## Gateway catalog

```bash
uv run python -m gateway          # grouped listing
uv run python -m gateway --json   # machine-readable
```

## Tests and lint (matches CI)

```bash
uv sync --frozen --group dev
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
```

Schema and per-pillar loaders: [`scanner/db/README.md`](../scanner/db/README.md),
[`safety/db/README.md`](../safety/db/README.md),
[`evaluator/db/README.md`](../evaluator/db/README.md),
[`benchmarks/db/README.md`](../benchmarks/db/README.md).

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

Production runs on the **application VM** (`model-advisor.colab.duke.edu`). All UI
jobs and pillar Docker containers run on this host. A DGX or laptop can be used for
optional CLI dev when Postgres is reachable from your network.

```bash
git clone <repo-url> && cd security-and-qa-for-ai-models
cp .env.example .env
# Edit .env: DUKE_GATEWAY_KEY, HF_TOKEN (if needed), POSTGRES_DSN + EFFICACY_DB_DSN

uv sync --group dev
./docker/build-pillars.sh
./scripts/apply-schemas.sh --bootstrap

python3 main.py up -d --build
curl -s http://127.0.0.1:5000/api/health | python3 -m json.tool
```

After deploy: `GET /api/health` → `db_available: true`, then POST a job and poll `status_url`. See [`api/README.md`](../api/README.md).

Ongoing: `git pull && ./docker/run.sh up -d --build`; `uv run python -m api.ingest --apply` to bulk re-ingest artifacts from VM disk.
