# Benchmarks Postgres ingest (`benchmarks/db/`)

Load `benchmarks/results/<slug>.{json,jsonl}` into `public.benchmark_runs` on the
shared Duke Postgres (`qa_ai_models`). Built on **`dbutils/`** — dry-run by default,
idempotent upserts.

Disk JSON remains the source of truth until you run `--apply`. The frontend reads
`benchmarks/results/` on disk today.

## One-time setup

```bash
uv sync --group db
cp .env.example .env    # paste real POSTGRES_DSN from team lead (not YOUR_USER placeholders)
```

Connection errors usually mean: placeholder credentials still in ``.env``, missing ``?sslmode=require``, or your host is not on the network Postgres allows (try VPN / application VM).

## Apply schema (one-time)

Requires ``uv sync --group db`` and a real ``POSTGRES_DSN`` in ``.env`` (see ``.env.example`` — include ``?sslmode=require``).

```bash
uv run python -m dbutils.apply_schema benchmarks/db/benchmark_schema.sql
```

## Load benchmark runs

```bash
uv run python benchmarks/db/load_benchmarks.py              # dry run (no DB)
uv run python benchmarks/db/load_benchmarks.py --apply      # write rows
uv run python benchmarks/db/load_benchmarks.py --apply      # again: counts must NOT change
```

All four pillars at once:

```bash
uv run python -m api.ingest              # dry run
uv run python -m api.ingest bootstrap --apply
```

## Verify

```sql
SELECT COUNT(*) FROM public.benchmark_runs;

SELECT benchmark_key, gateway_model_id, headline_metric, headline_value, n_items, completed_at
FROM public.benchmark_runs
ORDER BY completed_at DESC NULLS LAST
LIMIT 10;
```

## Idempotency

| Table | Unique key | Notes |
|-------|------------|-------|
| `benchmark_runs` | `output_slug` | file stem under `benchmarks/results/` |

Re-loading the same file cannot duplicate a row.

## Undo (review only)

```sql
DROP TABLE IF EXISTS public.benchmark_runs CASCADE;
```

## Files

| File | Role |
|------|------|
| `benchmark_schema.sql` | DDL for `benchmark_runs` |
| `transforms.py` | Pure parse/summary (no DB, no frontend) |
| `load_benchmarks.py` | Validator + transforms + `load_into` (uses `dbutils`) |

Column reference: `docs/data-model.md` (`benchmark_runs`).
