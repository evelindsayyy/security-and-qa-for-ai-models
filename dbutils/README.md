# dbutils — shared Postgres ingest helpers

Reusable plumbing for **JSON → Postgres** loaders. Each pillar keeps its own
``pillar/db/`` directory (transforms + INSERT SQL). **Do not** put
pillar-specific table logic here.

**Status:** Track A/B loaders for scanner, safety, and benchmarks should use
this package (W5). The efficacy loader in ``evaluator/db/`` is **standalone**
(Grace) until it is migrated — use it as a behavioral reference, not an import
dependency.

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

```bash
# Option A — psql
psql "$POSTGRES_DSN" -f scanner/db/schema.sql

# Option B — dbutils (no psql on PATH)
uv run python -c "
from dbutils import apply_sql_file, load_repo_env, resolve_dsn
load_repo_env()
apply_sql_file(resolve_dsn('POSTGRES_DSN'), __import__('pathlib').Path('scanner/db/schema.sql'))
"
```

## Dependencies

```bash
uv sync --group db   # psycopg — optional; plain uv sync skips it
```

## Planned pillar loaders (W5)

| Pillar | Directory | Input |
|--------|-----------|-------|
| Scanner | `scanner/db/` | `scanner/output/<slug>/scan_result.json` |
| Safety | `safety/db/` | `safety/output/<model>/merged_safety_result.json` |
| Benchmarks | `benchmarks/db/` | `benchmarks/results/*.{json,jsonl}` |
| Evaluator | `evaluator/db/` | *(standalone today — migrate to dbutils later)* |

Unified orchestrator ``api/ingest`` (W5-15) should call each pillar's ``load_into``.

## Tests

```bash
uv run python -m unittest unit_tests.test_dbutils -v
```

Pillar loaders should add ``unit_tests/test_*_loader.py`` with pure-transform
tests and a fake-cursor ``load_into`` test (see ``test_db_loader.py`` for the
evaluator pattern).
