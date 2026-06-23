# evaluator/db — Postgres for the Efficacy pillar

Results JSONLs (`evaluator/results/`) stay the pipeline's **source of truth**;
the database is a queryable projection of them. The runner never writes to
Postgres — the loader syncs files → tables, and re-running it can never
duplicate a row.

| File | Purpose |
|---|---|
| `efficacy_schema.sql` | DDL: `task_suites` → `eval_runs` → `eval_results` (Option A: per-dimension scores in `detail` JSONB). `CREATE TABLE IF NOT EXISTS` — safe to re-run. |
| `load_results.py` | JSONL → tables. **Dry-run by default**; `--apply` + DSN required to write. Idempotent via the schema's unique keys (`ON CONFLICT DO NOTHING`). |

Column-level docs: `docs/data-model.md` (Track B section).

## Setup (one-time)

```bash
uv sync --group db            # installs psycopg (optional dependency group)
cp .env.example .env          # if you don't have one; then fill in:
# EFFICACY_DB_DSN="postgresql://USER:PASSWORD@codeplus-postgres-test-01.oit.duke.edu:5432/qa_ai_models"
```

Set `EFFICACY_DB_DSN` in `.env` (credentials from team lead; never commit them).

## Apply the schema (one-time)

Requires ``uv sync --group db`` and ``EFFICACY_DB_DSN`` (or ``POSTGRES_DSN``) in ``.env`` with ``?sslmode=require``:

```bash
uv run python -m dbutils.apply_schema evaluator/db/efficacy_schema.sql
```

## Load results

```bash
uv run python evaluator/db/load_results.py            # dry run — prints what would load
uv run python evaluator/db/load_results.py --apply    # real load
uv run python evaluator/db/load_results.py --apply    # again: counts must NOT change (idempotency)
```

All pillars: `uv run python -m api.ingest` — see [`docs/cli.md`](../docs/cli.md).

## Verify

```sql
-- counts: runs == dry-run's file count; results == sum of question counts
SELECT (SELECT count(*) FROM public.task_suites)  AS suites,
       (SELECT count(*) FROM public.eval_runs)    AS runs,
       (SELECT count(*) FROM public.eval_results) AS results;

-- the policy_qa comparison table, straight from SQL
SELECT r.gateway_model_id, r.judge_model,
       round(r.aggregate_score::numeric, 2) AS overall,
       r.latency_p50_ms, r.cost_usd_total, count(er.id) AS questions
FROM public.eval_runs r
JOIN public.task_suites s ON s.id = r.suite_id
LEFT JOIN public.eval_results er ON er.eval_run_id = r.id
WHERE s.suite_key = 'policy_qa'
GROUP BY r.id, r.gateway_model_id, r.judge_model, r.aggregate_score,
         r.latency_p50_ms, r.cost_usd_total
ORDER BY r.aggregate_score DESC NULLS LAST;

-- JSONB smoke test: per-dimension extraction
SELECT task_id, score,
       detail->'scores'->'accuracy'->>'score' AS accuracy,
       detail->>'schema_version'              AS schema_version
FROM public.eval_results LIMIT 5;
```

## Undo (review/testing only)

```sql
DROP TABLE IF EXISTS public.eval_results, public.eval_runs, public.task_suites CASCADE;
```

## Week-5 notes (for whoever builds the API)

- Stay on raw SQL until the API lands; then write SQLAlchemy models mirroring
  these tables, create an Alembic baseline revision matching
  `efficacy_schema.sql`, and `alembic stamp head` against the live DB —
  adopting existing tables, not recreating them.
- The shared `models` table (cross-pillar join anchor from `docs/data-model.md`)
  is deliberately NOT created here; `eval_runs.gateway_model_id` is the string
  key until the team owns that table.
- The dashboard's DB read path (`frontend/eval_db_data.py`) keys on
  `eval_runs.source_file` == `<slug>.jsonl` and falls back to files whenever
  the DB is unreachable — delete it when the API replaces it.
