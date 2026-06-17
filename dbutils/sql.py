"""Apply SQL schema files and run parameterized statements."""

from __future__ import annotations

from pathlib import Path

from dbutils.connection import connect


def apply_sql_file(dsn: str, sql_path: Path) -> None:
    """Execute a ``.sql`` file (DDL or migrations) against Postgres.

    Use for one-time ``CREATE TABLE IF NOT EXISTS`` scripts in ``pillar/db/``.
    Prefer ``psql -f`` when available; this is the psycopg fallback (same as
    documented in pillar READMEs).
    """
    sql = sql_path.read_text(encoding="utf-8")
    with connect(dsn) as conn:
        conn.execute(sql)
        conn.commit()


def execute_many(
    conn,
    statements: list[tuple[str, dict | None]],
) -> None:
    """Run a list of ``(sql, params)`` pairs on an open connection.

    ``params`` may be ``None`` for statements without bind parameters.
    Does **not** commit — caller or ``transaction()`` owns the commit.
    """
    with conn.cursor() as cur:
        for sql, params in statements:
            if params is None:
                cur.execute(sql)
            else:
                cur.execute(sql, params)


def transaction(conn, fn) -> None:
    """Call ``fn(conn)`` then commit. Use inside custom ``load_into`` implementations."""
    fn(conn)
    conn.commit()
