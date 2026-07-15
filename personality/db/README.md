# Personality Postgres

DDL and loader for `public.personality_runs` (BFI, compass, …).

```bash
# Apply schema (also included in ./scripts/apply-schemas.sh)
uv run python -m dbutils.apply_schema personality/db/personality_schema.sql
uv run python -m dbutils.apply_schema db/auth_schema.sql

# Dry-run / apply
uv run python personality/db/load_personality.py
uv run python personality/db/load_personality.py --apply

# Via orchestrator
uv run python -m api.ingest --personality
uv run python -m api.ingest --personality --apply
```

Idempotent on `output_slug`. Auth columns come from `db/auth_schema.sql` and are
filled from `personality/results/<stem>/run_meta.json` at ingest time.

UI reads via `frontend/personality_db_data.py` when `POSTGRES_DSN` is reachable.
