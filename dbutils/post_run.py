"""Best-effort post-run Postgres sync when a DSN is configured."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from dbutils.connection import psycopg_available
from dbutils.env import load_repo_env, resolve_dsn

Pillar = Literal["scan", "safety", "eval", "benchmark", "personality"]

_DSN_KEYS = ("POSTGRES_DSN", "DATABASE_URL", "EFFICACY_DB_DSN")


def should_auto_sync() -> bool:
    """True when a DSN is set and AUTO_INGEST is not explicitly disabled."""
    load_repo_env()
    flag = os.environ.get("AUTO_INGEST", "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return bool(resolve_dsn(*_DSN_KEYS))


def _resolve_dsn() -> str | None:
    load_repo_env()
    return resolve_dsn(*_DSN_KEYS)


def sync_artifact(path: Path, pillar: Pillar, *, dsn: str) -> None:
    """Load one artifact file. Raises if parse or DB write fails."""
    if pillar == "scan":
        from scanner.db.load_scans import sync_file
    elif pillar == "safety":
        from safety.db.load_safety import sync_file
    elif pillar == "eval":
        from evaluator.db.load_results import sync_file
    elif pillar == "benchmark":
        from benchmarks.db.load_benchmarks import sync_file
    else:
        from personality.db.load_personality import sync_file
    sync_file(path, dsn=dsn)


def maybe_sync_artifact(path: Path, pillar: Pillar) -> None:
    """Best-effort sync after a successful pillar run. Never raises."""
    if not should_auto_sync():
        return
    if not path.is_file():
        print(f"  WARN: auto-ingest: missing {path.name}; skipping.", file=sys.stderr)
        return
    dsn = _resolve_dsn()
    if not dsn:
        print(
            "  WARN: auto-ingest enabled but no DSN "
            "(POSTGRES_DSN / DATABASE_URL / EFFICACY_DB_DSN); skipping.",
            file=sys.stderr,
        )
        return
    if not psycopg_available():
        print(
            "  WARN: auto-ingest skipped — psycopg not installed "
            "(re-run uv sync). File kept on disk.",
            file=sys.stderr,
        )
        return
    try:
        sync_artifact(path, pillar, dsn=dsn)
        print(f"  DB: synced {path.name} into Postgres.")
    except ValueError as exc:
        print(f"  WARN: auto-ingest {exc}; skipping.", file=sys.stderr)
    except Exception as exc:
        print(
            f"  WARN: auto-ingest failed ({type(exc).__name__}: {exc}); "
            f"file intact — run `python -m api.ingest --apply` later.",
            file=sys.stderr,
        )
