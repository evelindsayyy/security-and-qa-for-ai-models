"""
dbutils — shared Postgres ingest helpers for all pillars.

Pillar packages own schema-specific transforms and SQL (``scanner/db/``,
``safety/db/``, ``benchmarks/db/``, …). Import dbutils for env/DSN, file IO,
psycopg connect, JSONB params, dry-run CLI, and schema apply.

**Note:** ``evaluator/db/`` is maintained separately (Grace) and does not
use dbutils yet — integrate later when ready.

See ``dbutils/README.md``.
"""

from dbutils.connection import DsnAvailability, connect, require_psycopg
from dbutils.env import REPO_ROOT, load_repo_env, resolve_dsn
from dbutils.files import exclude_substrings, iter_files, read_json, read_jsonl
from dbutils.ingest import apply_loader, jsonb_param
from dbutils.sql import apply_sql_file, execute_many, transaction
from dbutils.stats import percentile

__all__ = [
    "REPO_ROOT",
    "DsnAvailability",
    "apply_loader",
    "apply_sql_file",
    "connect",
    "exclude_substrings",
    "execute_many",
    "iter_files",
    "jsonb_param",
    "load_repo_env",
    "percentile",
    "read_json",
    "read_jsonl",
    "require_psycopg",
    "resolve_dsn",
    "transaction",
]
