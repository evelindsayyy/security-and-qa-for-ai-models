# CLI reference

All commands run from the **repo root**. First-time setup (core + optional groups for local pillar work):

```bash
uv sync --group dev --group scanner --group benchmarks
cp .env.example .env   # paste DUKE_GATEWAY_KEY (and HF_TOKEN / Postgres DSNs if needed)
```

For the Docker model behind these commands, see [`docker.md`](docker.md).

## Web UI

```bash
# Local dev (no Docker)
uv run flask --app frontend:create_app run --debug          # add --port 5001 if 5000 is busy

# Containerized (application VM); auto-detects user, Docker group, and repo path
./docker/run.sh up --build       # foreground
./docker/run.sh up -d --build    # background
./docker/run.sh down             # stop
./docker/run.sh logs -f web      # logs
```

Set `APP_PORT` in `.env` to change the port. Open `http://127.0.0.1:5000`.

## JSON API

Same Flask app as the UI. See [`api/README.md`](../api/README.md).

```bash
# Health (db_available false on DGX without Postgres is normal)
curl -s localhost:5001/api/health | python3 -m json.tool

# List + start a scan (202 + status_url)
curl -s localhost:5001/api/scans | python3 -m json.tool
curl -s -X POST localhost:5001/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"hf_repo":"distilbert-base-uncased"}' | python3 -m json.tool
curl -s localhost:5001/api/scans/distilbert-base-uncased/status | python3 -m json.tool

# Safety, eval, benchmark — POST bodies in api/README.md
curl -s localhost:5001/api/safety | python3 -m json.tool
curl -s localhost:5001/api/evals | python3 -m json.tool
curl -s localhost:5001/api/benchmarks | python3 -m json.tool
```

If `POST /api/scans` returns **503** with “cannot write”, output is often root-owned. On DGX (no sudo):

```bash
docker run --rm -v "$PWD/scanner/output:/out" -u root busybox \
  chown -R "$(id -u):$(id -g)" /out
```

## Pillar jobs

Browser "Start" buttons run these for you. To run them directly, set the file
owner once so outputs are not root-owned:

```bash
export UID=$(id -u) GID=$(id -g)
```

```bash
# Scan an HF repo -> scanner/output/<slug>/scan_result.json
docker compose --env-file .env -f scanner/docker/compose.yml run --rm scanner \
  python -m scanner scan gpt2

# Safety red-team -> safety/output/<slug>/merged_safety_result.json
./safety/run_safety.sh "GPT 4.1 Mini"

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

Local Docker Compose builds remain useful for verifying the full runtime stack
before deploy.

## Postgres ingest

Set real credentials in ``.env`` (not the ``YOUR_USER`` placeholders). Use ``?sslmode=require``. Run schema apply and bootstrap from the **application VM** (or VPN); gx10 may fail ``pg_hba`` / auth checks.

**Auto-sync:** when a DSN is set, each successful pillar run syncs its artifact into Postgres (best-effort; never fails the job). Disable with ``AUTO_INGEST=0``. Bulk backfill:

```bash
uv sync --group db
# Once per environment (all four pillar tables):
uv run python -m dbutils.apply_schema scanner/db/scan_schema.sql
uv run python -m dbutils.apply_schema safety/db/safety_schema.sql
uv run python -m dbutils.apply_schema evaluator/db/efficacy_schema.sql
uv run python -m dbutils.apply_schema benchmarks/db/benchmark_schema.sql
```

```bash
# All pillars (dry-run by default)
uv run python -m api.ingest
uv run python -m api.ingest --apply

# Single pillar (--scan, --safety, --eval, --benchmark)
uv run python -m api.ingest --scan --apply
uv run python -m api.ingest bootstrap --apply   # all pillars + summary line

# Per-pillar loaders
uv run python scanner/db/load_scans.py --apply
uv run python safety/db/load_safety.py --apply
uv run python evaluator/db/load_results.py --apply
uv run python benchmarks/db/load_benchmarks.py --apply
```

Schema and dry-run details: [`scanner/db/README.md`](../scanner/db/README.md),
[`safety/db/README.md`](../safety/db/README.md),
[`evaluator/db/README.md`](../evaluator/db/README.md),
[`benchmarks/db/README.md`](../benchmarks/db/README.md).

## Application VM setup

Production runs on the **application VM** (`model-advisor.colab.duke.edu`). DGX
(gx10) is fine for local dev and scans; Postgres ingest usually requires the VM
or VPN.

```bash
git clone <repo-url> && cd security-and-qa-for-ai-models
cp .env.example .env
# Edit .env: DUKE_GATEWAY_KEY, HF_TOKEN (if needed), POSTGRES_DSN with ?sslmode=require

uv sync --group db
uv run python -m dbutils.apply_schema scanner/db/scan_schema.sql
uv run python -m dbutils.apply_schema safety/db/safety_schema.sql
uv run python -m dbutils.apply_schema evaluator/db/efficacy_schema.sql
uv run python -m dbutils.apply_schema benchmarks/db/benchmark_schema.sql
uv run python -m api.ingest bootstrap --apply   # backfill artifacts already on disk

./docker/run.sh up -d --build
curl -s http://127.0.0.1:5000/api/health | python -m json.tool
```

After deploy, verify the JSON API: `GET /api/health` (`db_available: true` when
Postgres is reachable), then `POST /api/scans` or `POST /api/benchmarks` with a
JSON body, poll the returned `status_url`, and `GET` the detail route. See
[`api/README.md`](../api/README.md).

Ongoing: `git pull && ./docker/run.sh up -d --build` to deploy; `uv run python -m
api.ingest --apply` to bulk re-ingest artifacts copied from DGX.
