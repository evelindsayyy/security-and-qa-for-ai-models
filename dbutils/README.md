# dbutils — shared Postgres ingest helpers

Reusable plumbing for **JSON → Postgres** loaders. Scan, safety, and benchmarks use
this package; ``evaluator/db/`` is standalone but shares the same DSN via ``api.ingest``.

Each pillar keeps its own ``pillar/db/`` directory (transforms + INSERT SQL).

## Modules

| Module | Use for |
|--------|---------|
| `env` | `load_repo_env()`, `resolve_dsn("POSTGRES_DSN", …)` |
| `files` | `read_json`, `read_jsonl`, `iter_files`, `exclude_substrings` |
| `stats` | `percentile` — run-level latency aggregates |
| `connection` | `connect`, `require_psycopg`, `DsnAvailability` (UI/API probes) |
| `ingest` | `jsonb_param`, `apply_loader`, dry-run exit helpers |
| `sql` | `apply_sql_file`, `execute_many`, `transaction` |
| `cli` | `add_ingest_arguments` — standard `--apply` / `--dsn` |
| `apply_schema.py` | `python -m dbutils.apply_schema` — apply pillar DDL (no `psql`) |
| `compose` | `compose_cmd`, `compose_run` — shared Docker Compose helpers |
| `post_run.py` | `maybe_sync_artifact` — auto-ingest after successful pillar runs |
| `startup.py` | Flask startup log for Postgres read path |

## Pillar loader template (scanner / safety / benchmarks)

```python
from pathlib import Path
import argparse

from dbutils import (
    apply_loader,
    apply_sql_file,
    exclude_substrings,
    iter_files,
    jsonb_param,
    load_repo_env,
    read_json,
)
from dbutils.cli import add_ingest_arguments
from dbutils.ingest import exit_if_apply_without_dsn, print_dry_run_hint

OUTPUT_DIR = Path("scanner/output")  # pillar-specific

def load_file(path: Path) -> dict | None:
    data = read_json(path / "scan_result.json")
    if data is None:
        return None
    return scan_row(data)  # pillar transform — unit test this

def load_into(conn, parsed: list[dict]) -> None:
    ...  # pillar INSERT SQL with ON CONFLICT DO NOTHING

def main() -> int:
    load_repo_env()
    ap = argparse.ArgumentParser(description="Load scan results into Postgres.")
    ap.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    add_ingest_arguments(ap)  # --apply, --dsn
    args = ap.parse_args()

    files = iter_files(args.output_dir, "*/scan_result.json")  # or custom walk
    parsed = [r for r in (load_file(p.parent) for p in files) if r is not None]
    print(f"{len(parsed)} loadable scan(s):")
    for row in parsed:
        print(f"  {row['hf_repo']}  tier={row['severity_tier']}")

    if not args.apply:
        print_dry_run_hint()
        return 0
    exit_if_apply_without_dsn(args.dsn)
    apply_loader(args.dsn, lambda c: load_into(c, parsed),
                 item_count=len(parsed), item_label="scan(s)")
    return 0
```

## Apply schema (one-time)

After ``uv sync --group dev`` (psycopg is a core dependency):

```bash
./scripts/apply-schemas.sh --bootstrap   # all four DDL files + seed from disk
uv run python -m dbutils.apply_schema scanner/db/scan_schema.sql   # single file
```

## Auto-ingest

When ``POSTGRES_DSN`` (or ``EFFICACY_DB_DSN``) is set, each pillar calls ``maybe_sync_artifact`` after a successful run. Disable with ``AUTO_INGEST=0``. Bulk backfill: ``python -m api.ingest --apply``.

## Pillar loaders

| Pillar | Directory | Input |
|--------|-----------|-------|
| Scanner | `scanner/db/` | `scanner/output/<slug>/scan_result.json` |
| Safety | `safety/db/` | `safety/output/<model>/merged_safety_result.json` |
| Evaluator | `evaluator/db/` | `evaluator/results/*.jsonl` (standalone CLI; shares DSN via `api.ingest`) |
| Benchmarks | `benchmarks/db/` | `benchmarks/results/*.{json,jsonl}` |

Unified orchestrator: `uv run python -m api.ingest` (dry-run all pillars) or `--apply` to load.

## Tests

```bash
uv run python -m unittest unit_tests.test_dbutils -v
```

Pillar loaders should add ``unit_tests/test_*_loader.py`` with pure-transform
tests and a fake-cursor ``load_into`` test (see ``test_db_loader.py`` for the
evaluator pattern).
