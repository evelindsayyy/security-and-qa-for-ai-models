"""Shared helpers for pillar delete flows when Postgres is authoritative."""

from __future__ import annotations


def db_delete_error(
    *,
    db_available: bool,
    db_row_existed: bool,
    removed_db: bool,
    db_exc: BaseException | None = None,
) -> str | None:
    """Return an error message when a DB delete failed; None on success or no DB."""
    if db_exc is not None:
        return f"database delete failed: {db_exc}"
    if db_available and db_row_existed and not removed_db:
        return "database delete failed: row was not removed"
    return None
