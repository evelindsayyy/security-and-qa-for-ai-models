"""One-line Postgres availability log on Flask startup."""

from __future__ import annotations

import logging

from dbutils.env import load_repo_env, resolve_dsn

log = logging.getLogger(__name__)

_DSN_KEYS = ("POSTGRES_DSN", "EFFICACY_DB_DSN", "DATABASE_URL")


def log_db_read_path() -> None:
    """Log whether the UI/API will read Postgres or fall back to disk."""
    load_repo_env()
    dsn = resolve_dsn(*_DSN_KEYS)
    if not dsn:
        return
    try:
        from dbutils.connection import psycopg_available

        if not psycopg_available():
            log.info("Postgres DSN set but psycopg missing — reads fall back to disk JSON")
            return
        from dbutils.connection import connect

        with connect(dsn, connect_timeout_s=2):
            log.info("Postgres read path active (DSN configured and reachable)")
            return
    except Exception:
        log.info("Postgres DSN set but unreachable — reads fall back to disk JSON")
