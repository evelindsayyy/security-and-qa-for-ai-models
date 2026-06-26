"""
Apply a pillar ``.sql`` schema file to Postgres (psycopg).

Run from repo root after ``uv sync`` and setting ``POSTGRES_DSN`` in ``.env``:

    uv run python -m dbutils.apply_schema benchmarks/db/benchmark_schema.sql
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dbutils import apply_sql_file, load_repo_env, resolve_dsn


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply a Postgres schema SQL file.")
    ap.add_argument("schema", type=Path, help="path to .sql file (e.g. scanner/db/scan_schema.sql)")
    ap.add_argument(
        "--dsn",
        default=None,
        help="Postgres DSN (default: POSTGRES_DSN / DATABASE_URL / EFFICACY_DB_DSN from .env)",
    )
    args = ap.parse_args(argv)

    if not args.schema.is_file():
        print(f"Schema file not found: {args.schema}", file=sys.stderr)
        return 1

    load_repo_env()
    dsn = args.dsn or resolve_dsn("POSTGRES_DSN", "DATABASE_URL", "EFFICACY_DB_DSN")
    if not dsn:
        print(
            "No DSN: set POSTGRES_DSN in .env (real credentials + ?sslmode=require) or pass --dsn",
            file=sys.stderr,
        )
        return 1

    apply_sql_file(dsn, args.schema)
    print(f"Applied {args.schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
