"""
Postgres-backed data source for /personality — same dict contracts as
personality_data.py, used only when POSTGRES_DSN is set and reachable.
"""

from __future__ import annotations

import time
from typing import Any

from dbutils import load_repo_env, resolve_dsn

from frontend.personality_data import (
    PRIMARY_DIR,
    TRAIT_ORDER,
    _attach_test_fields,
    _format_ts,
    _iso_ts,
    _normalize_model_name,
    _test_label,
    build_detail_payload,
)

load_repo_env()

_DSN_KEYS = ("POSTGRES_DSN", "DATABASE_URL")
_CONNECT_TIMEOUT_S = 2
_AVAILABILITY_TTL_S = 60.0
_avail_cache = {"checked_at": float("-inf"), "ok": False}


def _dsn() -> str | None:
    return resolve_dsn(*_DSN_KEYS)


def available() -> bool:
    """True when a DSN is configured, psycopg is installed, and Postgres answers."""
    dsn = _dsn()
    if not dsn:
        return False
    now = time.monotonic()
    if now - _avail_cache["checked_at"] < _AVAILABILITY_TTL_S:
        return _avail_cache["ok"]
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=_CONNECT_TIMEOUT_S):
            ok = True
    except Exception:
        ok = False
    _avail_cache.update(checked_at=now, ok=ok)
    return ok


def _connect():
    import psycopg

    return psycopg.connect(_dsn(), connect_timeout=_CONNECT_TIMEOUT_S)


_LIST_SQL = """
SELECT output_slug, source_filename, gateway_model_id, test_key,
       n_items, attempted, scored, coverage, traits, summary, completed_at
FROM public.personality_runs p
WHERE {visibility_filter}
ORDER BY completed_at DESC NULLS LAST, output_slug
"""

_DETAIL_SQL = """
SELECT output_slug, source_filename, gateway_model_id, test_key,
       n_items, attempted, scored, coverage, traits, items, summary, completed_at
FROM public.personality_runs p
WHERE output_slug = %(slug)s AND ({visibility_filter})
LIMIT 1
"""


def _ts_raw(completed_at: Any) -> str:
    if completed_at is None:
        return ""
    if hasattr(completed_at, "isoformat"):
        return completed_at.isoformat()
    return str(completed_at)


def _visibility_params(
    *, visibility: str | None = None, owner_user_id: str | None = None
) -> tuple[str, dict]:
    from dbutils.visibility import visibility_clause

    if visibility is None:
        from frontend.read_context import read_context

        visibility, owner_user_id = read_context()
    clause, params = visibility_clause(
        "p", view_mode=visibility, user_id=owner_user_id, links_alias=True
    )
    return clause, params


def _summarize_db_run(row: tuple) -> dict:
    (
        output_slug,
        source_filename,
        gateway_model_id,
        test_key,
        _n_items,
        attempted,
        scored,
        coverage,
        traits,
        summary,
        completed_at,
    ) = row
    summary = dict(summary or {})
    if traits and "traits" not in summary and test_key == "bfi":
        summary["traits"] = traits
    # Prefer summary coverage fields when present; fall back to columns.
    if attempted is not None:
        summary.setdefault("attempted", attempted)
    if scored is not None:
        summary.setdefault("scored", scored)
    if coverage is not None:
        summary.setdefault("coverage", coverage)
    ts_raw = _ts_raw(completed_at)
    row_out = {
        "slug": output_slug,
        "test": test_key,
        "test_label": _test_label(test_key),
        "model": _normalize_model_name(gateway_model_id or "—"),
        "timestamp_raw": ts_raw,
        "timestamp": _format_ts(ts_raw),
        "timestamp_iso": _iso_ts(ts_raw),
        "filename": source_filename,
        "coverage": summary.get("coverage", coverage),
        "attempted": summary.get("attempted", attempted),
        "scored": summary.get("scored", scored),
    }
    return _attach_test_fields(row_out, test_key=test_key, summary=summary)


def get_personality_data_db(
    *, visibility: str | None = None, owner_user_id: str | None = None
) -> dict:
    """Every known personality run, straight from Postgres."""
    vis_clause, vis_params = _visibility_params(
        visibility=visibility, owner_user_id=owner_user_id
    )

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_LIST_SQL.format(visibility_filter=vis_clause), vis_params)
            run_rows = cur.fetchall()
    rows = [_summarize_db_run(row) for row in run_rows]
    from frontend.personality_data import _postprocess_runs

    out = _postprocess_runs(rows)
    out["search_paths"] = [str(PRIMARY_DIR)]
    out["trait_order"] = list(TRAIT_ORDER)
    return out


def get_personality_detail_db(
    slug: str, *, visibility: str | None = None, owner_user_id: str | None = None
) -> dict | None:
    """Detail-page payload from Postgres; None if slug isn't loaded."""
    vis_clause, vis_params = _visibility_params(
        visibility=visibility, owner_user_id=owner_user_id
    )

    with _connect() as conn:
        with conn.cursor() as cur:
            params = {"slug": slug, **vis_params}
            cur.execute(_DETAIL_SQL.format(visibility_filter=vis_clause), params)
            row = cur.fetchone()
            if row is None:
                return None

    (
        output_slug,
        source_filename,
        gateway_model_id,
        test_key,
        _n_items,
        attempted,
        scored,
        coverage,
        traits,
        items,
        summary,
        completed_at,
    ) = row
    summary = dict(summary or {})
    if traits and "traits" not in summary and test_key == "bfi":
        summary["traits"] = traits
    if attempted is not None:
        summary.setdefault("attempted", attempted)
    if scored is not None:
        summary.setdefault("scored", scored)
    if coverage is not None:
        summary.setdefault("coverage", coverage)
    return build_detail_payload(
        slug=output_slug,
        test_key=test_key,
        model=gateway_model_id or "—",
        timestamp_raw=_ts_raw(completed_at),
        filename=source_filename,
        items=items or [],
        summary=summary,
        visibility=visibility or "public",
    )


def delete_run(
    slug: str, *, visibility: str | None = None, owner_user_id: str | None = None
) -> bool:
    """Delete one row from ``personality_runs``. Returns True if a row was removed."""
    vis_clause, vis_params = _visibility_params(
        visibility=visibility, owner_user_id=owner_user_id
    )
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM public.personality_runs AS p "
                f"WHERE output_slug = %(slug)s AND ({vis_clause})",
                {"slug": slug, **vis_params},
            )
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted
