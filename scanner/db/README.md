# Scanner Postgres ingest (`scanner/db/`)

Load `scanner/output/<slug>/scan_result.json` into `public.scans` and
`public.findings` on the shared Duke Postgres (`qa_ai_models`). Built on
**`dbutils/`** — dry-run by default, idempotent upserts.

Disk JSON remains the source of truth until you run `--apply`. The frontend
reads Postgres when `POSTGRES_DSN` is set and reachable, else files (see
`frontend/scan_db_data.py`).

## One-time setup

```bash
uv sync --group db
cp .env.example .env    # set POSTGRES_DSN (same login as EFFICACY_DB_DSN)
```

## Apply schema (one-time)

Requires ``uv sync --group db`` and a real ``POSTGRES_DSN`` in ``.env`` (include ``?sslmode=require``).

```bash
uv run python -m dbutils.apply_schema scanner/db/scan_schema.sql
```

## Load scans

```bash
uv run python scanner/db/load_scans.py              # dry run (no DB)
uv run python scanner/db/load_scans.py --apply      # write rows
uv run python scanner/db/load_scans.py --apply      # again: counts must NOT change
```

All pillars: `uv run python -m api.ingest` — see [`docs/cli.md`](../../docs/cli.md).

## Verify

```sql
SELECT COUNT(*) FROM public.scans;
SELECT COUNT(*) FROM public.findings;

SELECT hf_repo, severity_tier, overall_risk_score, completed_at
FROM public.scans
ORDER BY completed_at DESC
LIMIT 10;

SELECT s.hf_repo, f.source, f.severity, f.title
FROM public.findings f
JOIN public.scans s ON s.id = f.scan_id
ORDER BY s.completed_at DESC
LIMIT 20;
```

## Idempotency

| Table | Unique key | Notes |
|-------|------------|-------|
| `scans` | `(hf_repo, completed_at)` | `completed_at` = `scan_metadata.scanned_at` |
| `findings` | `(scan_id, finding_key)` | `finding_key` = deterministic `Finding.id` from JSON |

Re-scanning the same model produces a **new** row when `scanned_at` changes.
The UI list shows the **latest** `completed_at` per `hf_repo`.

## Undo (review only)

```sql
DROP TABLE IF EXISTS public.findings, public.scans CASCADE;
```

## Files

| File | Role |
|------|------|
| `scan_schema.sql` | DDL for `scans` + `findings` |
| `load_scans.py` | Validator + transforms + `load_into` (uses `dbutils`) |

Column reference: `docs/data-model.md` (Track A — scanning).
