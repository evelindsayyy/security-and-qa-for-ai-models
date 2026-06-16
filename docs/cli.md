# CLI reference

All commands run from the **repo root**. First-time setup:

```bash
uv sync
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
docker compose --project-name qa-ai-models -f docker/compose.yml build
docker compose --project-name qa-ai-models -f scanner/docker/compose.yml build
```

## Postgres ingest

Set `POSTGRES_DSN` / `EFFICACY_DB_DSN` in `.env`, then (`uv sync --group db`):

```bash
uv run python scanner/db/load_scans.py --apply
uv run python evaluator/db/load_results.py --apply
```

Schema and dry-run details: [`scanner/db/README.md`](../scanner/db/README.md),
[`evaluator/db/README.md`](../evaluator/db/README.md).
