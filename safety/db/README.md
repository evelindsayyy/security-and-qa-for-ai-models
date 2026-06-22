# Safety Postgres ingest (`safety/db/`)

Load `safety/output/<model>/merged_safety_result.json` into `public.safety_runs` and
`public.safety_findings` on the shared Duke Postgres (`qa_ai_models`). Built on
**`dbutils/`** — dry-run by default, idempotent upserts.

Disk JSON remains the source of truth until you run `--apply`.

## One-time setup

```bash
uv sync --group db
cp .env.example .env    # set POSTGRES_DSN
```

## Apply schema (one-time)

Requires ``uv sync --group db`` and a real ``POSTGRES_DSN`` in ``.env`` (include ``?sslmode=require``).

```bash
uv run python -m dbutils.apply_schema safety/db/safety_schema.sql
```

## Load safety runs

```bash
uv run python safety/db/load_safety.py              # dry run (no DB)
uv run python safety/db/load_safety.py --apply      # write rows
uv run python safety/db/load_safety.py --apply      # again: counts must NOT change
```

All pillars: `uv run python -m api.ingest` — see [`docs/cli.md`](../../docs/cli.md).

## Verify

```sql
SELECT COUNT(*) FROM public.safety_runs;
SELECT COUNT(*) FROM public.safety_findings;

SELECT gateway_model_id, composite_tier, composite_score, completed_at
FROM public.safety_runs
ORDER BY completed_at DESC
LIMIT 10;

SELECT r.gateway_model_id, f.source, f.category, f.severity, f.passed, f.title
FROM public.safety_findings f
JOIN public.safety_runs r ON r.id = f.run_id
ORDER BY r.completed_at DESC
LIMIT 20;
```

## Idempotency

| Table | Unique key | Notes |
|-------|------------|-------|
| `safety_runs` | `(gateway_model_id, completed_at)` | `completed_at` from `MergedSafetyResult` |
| `safety_findings` | `(run_id, finding_key)` | `finding_key` = `SafetyFinding.id` UUID |

Re-running the same model produces a **new** row only when `completed_at` changes.

## Undo (review only)

```sql
DROP TABLE IF EXISTS public.safety_findings, public.safety_runs CASCADE;
```

## Files

| File | Role |
|------|------|
| `safety_schema.sql` | DDL for `safety_runs` + `safety_findings` |
| `load_safety.py` | Validator + transforms + `load_into` (uses `dbutils`) |

## Tests

```bash
uv run python -m unittest unit_tests.test_safety_db_loader -v
```
