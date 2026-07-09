"""
Postgres-backed data source for /safety — same dict contracts as safety_data.py,
used only when POSTGRES_DSN is set and reachable.

Merges DB rows with safety runs not yet loaded. Detail uses artifact fallback
when the slug is missing from Postgres.
"""

from __future__ import annotations

import time

from dbutils import load_repo_env, resolve_dsn

from frontend.path_safety import is_safe_slug
from frontend.safety_data import (
    OUTPUT_DIR,
    _build_safety_detail,
    _summarize_merged_data,
)

load_repo_env()

_DSN_KEYS = ("POSTGRES_DSN", "DATABASE_URL")
_CONNECT_TIMEOUT_S = 2
_AVAILABILITY_TTL_S = 60.0
_avail_cache = {"checked_at": 0.0, "ok": False}

_SUITE_ORDER = ("promptfoo_duke_policy_v1", "promptfoo_duke_redteam_v1", "garak_subset_v1")


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


_LATEST_RUNS_SQL = """
SELECT DISTINCT ON (gateway_model_id, redteam_profile)
    id::text, gateway_model_id, redteam_profile, display_name, status, deployment_context,
    summary_pass_rate, safety_tier, adversarial_tier, composite_tier,
    composite_score, missing_suites, runs, tool_results, started_at, completed_at,
    config_fingerprint, config_json
FROM public.safety_runs s
WHERE {visibility_filter}
ORDER BY gateway_model_id, redteam_profile, completed_at DESC NULLS LAST
"""

_DETAIL_RUN_SQL = """
SELECT id::text, gateway_model_id, redteam_profile, display_name, status, deployment_context,
       summary_pass_rate, safety_tier, adversarial_tier, composite_tier,
       composite_score, missing_suites, runs, tool_results, started_at, completed_at
FROM public.safety_runs s
WHERE gateway_model_id = %(gateway_model_id)s
  AND redteam_profile = %(redteam_profile)s
  AND ({visibility_filter})
ORDER BY completed_at DESC NULLS LAST
LIMIT 1
"""

_FINDINGS_SQL = """
SELECT finding_key, category, source, passed, severity, title, description,
       probe_id, probe_suite, corroborated_by
FROM public.safety_findings
WHERE run_id = %(run_id)s::uuid
ORDER BY passed, severity, source, probe_id
"""

_FINDINGS_FOR_RUNS_SQL = """
SELECT run_id::text, finding_key, category, source, passed, severity, title,
       description, probe_id, probe_suite, corroborated_by
FROM public.safety_findings
WHERE run_id = ANY(%(run_ids)s::uuid[])
ORDER BY run_id, passed, severity, source, probe_id
"""


def _findings_to_json(rows: list[tuple]) -> list[dict]:
    out: list[dict] = []
    for (
        finding_key,
        category,
        source,
        passed,
        severity,
        title,
        description,
        probe_id,
        probe_suite,
        corroborated_by,
    ) in rows:
        out.append(
            {
                "id": finding_key,
                "category": (category or "unknown").lower(),
                "source": (source or "unknown").lower(),
                "passed": bool(passed),
                "severity": (severity or "unknown").lower(),
                "title": title or "—",
                "description": description or "",
                "probe_id": probe_id or "—",
                "probe_suite": probe_suite,
                "corroborated_by": corroborated_by or [],
            }
        )
    return out


def _run_tuple_to_data(run_row: tuple, findings_json: list[dict]) -> dict:
    """Rebuild MergedSafetyResult-shaped dict from DB columns."""
    (
        _run_id,
        gateway_model_id,
        redteam_profile,
        display_name,
        status,
        deployment_context,
        summary_pass_rate,
        safety_tier,
        adversarial_tier,
        composite_tier,
        composite_score,
        missing_suites,
        runs,
        tool_results,
        started_at,
        completed_at,
    ) = run_row
    return {
        "gateway_model_id": gateway_model_id,
        "redteam_profile": redteam_profile or "base",
        "display_name": display_name,
        "status": status or "complete",
        "deployment_context": deployment_context or {},
        "summary_pass_rate": float(summary_pass_rate or 0.0),
        "safety_tier": safety_tier or "low",
        "adversarial_tier": adversarial_tier or "low",
        "composite_tier": composite_tier or "low",
        "composite_score": float(composite_score or 0.0),
        "missing_suites": missing_suites or [],
        "runs": runs or [],
        "findings": findings_json,
        "tool_results": tool_results or {},
        "started_at": str(started_at) if started_at else None,
        "completed_at": str(completed_at) if completed_at else None,
    }


def _summarize_db_run(run_row: tuple, findings_json: list[dict] | None = None) -> dict | None:
    """List-table row from one safety_runs tuple (same keys as _summarize_merged_data)."""
    slug = run_row[1]  # gateway_model_id doubles as slug
    data = _run_tuple_to_data(run_row, findings_json or [])
    row = _summarize_merged_data(data, slug)
    if row is None:
        return None
    sidecar: dict = {}
    if len(run_row) > 17 and run_row[17]:
        sidecar["config_json"] = run_row[17]
    if len(run_row) > 16 and run_row[16]:
        sidecar["config_fingerprint"] = run_row[16]
    from frontend.safety_data import _attach_safety_staleness_fields

    _attach_safety_staleness_fields(row, data, sidecar=sidecar)
    return row


def _fetch_findings_by_run_id(conn, run_ids: list[str]) -> dict[str, list[dict]]:
    """Batch-load findings for list-table rows (one query for all run ids)."""
    if not run_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(_FINDINGS_FOR_RUNS_SQL, {"run_ids": run_ids})
        rows = cur.fetchall()
    grouped: dict[str, list[dict]] = {run_id: [] for run_id in run_ids}
    for run_id, *finding in rows:
        grouped.setdefault(run_id, []).extend(_findings_to_json([finding]))
    return grouped


def _visibility_params(
    *, visibility: str | None = None, owner_user_id: str | None = None
) -> tuple[str, dict]:
    """SQL visibility clause. Explicit ``visibility``/``owner_user_id`` (the
    resolved route scope) take precedence over the ambient session — omit
    both only for the list page, which still tracks the current toggle."""
    from dbutils.visibility import visibility_clause

    if visibility is None:
        from frontend.read_context import read_context

        visibility, owner_user_id = read_context()
    clause, params = visibility_clause("s", view_mode=visibility, user_id=owner_user_id, links_alias=True)
    return clause, params


def get_safety_data_db() -> dict:
    """Every known safety run, straight from Postgres.

    Postgres is the single source of truth when a DSN is reachable — we do NOT
    merge in on-disk artifacts here. Merging disk rows is what let a deleted
    run reappear (the DB row was gone but a stale JSON on the VM resurrected
    it). Not-yet-ingested runs surface once auto-sync loads them; disk is only
    consulted when no DSN is configured (see safety_data.get_safety_data)."""
    from frontend.safety_data import _SUITE_ORDER as _SO
    from frontend.safety_data import _suite_label

    vis_clause, vis_params = _visibility_params()

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_LATEST_RUNS_SQL.format(visibility_filter=vis_clause), vis_params)
            run_rows = cur.fetchall()
        findings_by_run = _fetch_findings_by_run_id(conn, [row[0] for row in run_rows])
        db_rows = [
            _summarize_db_run(row, findings_by_run.get(row[0], []))
            for row in run_rows
        ]
    rows = [r for r in db_rows if r is not None]
    rows.sort(key=lambda r: (r["composite_score"], r["summary_pass_rate"]))

    return {
        "has_safety": bool(rows),
        "output_dir": str(OUTPUT_DIR),
        "models": rows,
        "suite_labels": [_suite_label(s) for s in _SO],
    }


def get_safety_detail_db(
    slug: str,
    profile: str = "base",
    *,
    visibility: str | None = None,
    owner_user_id: str | None = None,
) -> dict | None:
    """Detail-page payload from Postgres; None if slug isn't loaded."""
    vis_clause, vis_params = _visibility_params(visibility=visibility, owner_user_id=owner_user_id)

    with _connect() as conn:
        with conn.cursor() as cur:
            params = {"gateway_model_id": slug, "redteam_profile": profile, **vis_params}
            cur.execute(_DETAIL_RUN_SQL.format(visibility_filter=vis_clause), params)
            run_row = cur.fetchone()
            if run_row is None:
                return None

            cur.execute(_FINDINGS_SQL, {"run_id": run_row[0]})
            findings_json = _findings_to_json(cur.fetchall())

    data = _run_tuple_to_data(run_row, findings_json)
    return _build_safety_detail(slug, data, profile)


def _resolve_delete_row(
    gateway_model_id: str,
    profile: str = "base",
    *,
    visibility: str | None = None,
    owner_user_id: str | None = None,
) -> tuple[str, str, str] | None:
    """Map UI slug to ``(run_id, gateway_model_id, completed_at)`` for the latest row."""
    if not is_safe_slug(gateway_model_id) or not is_safe_slug(profile):
        return None

    vis_clause, vis_params = _visibility_params(visibility=visibility, owner_user_id=owner_user_id)
    sql = _DETAIL_RUN_SQL.format(visibility_filter=vis_clause)

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                {"gateway_model_id": gateway_model_id, "redteam_profile": profile, **vis_params},
            )
            run_row = cur.fetchone()
            if run_row is None:
                return None
            run_id = run_row[0]
            model_id = run_row[1]
            completed_at = run_row[14]
            if not run_id or not model_id or completed_at is None:
                return None
            if hasattr(completed_at, "isoformat"):
                completed_at = completed_at.isoformat()
            else:
                completed_at = str(completed_at)
            return run_id, model_id, completed_at


def resolve_delete_keys(
    gateway_model_id: str,
    profile: str = "base",
    *,
    visibility: str | None = None,
    owner_user_id: str | None = None,
) -> tuple[str, str] | None:
    """Map UI slug to ``(gateway_model_id, completed_at)`` for the latest Postgres row
    matching ``visibility``/``owner_user_id`` (defaults to the ambient session's scope)."""
    row = _resolve_delete_row(
        gateway_model_id, profile, visibility=visibility, owner_user_id=owner_user_id
    )
    if row is None:
        return None
    return row[1], row[2]


def resolve_delete_run_id(
    gateway_model_id: str,
    profile: str = "base",
    *,
    visibility: str | None = None,
    owner_user_id: str | None = None,
) -> str | None:
    """Return the Postgres ``safety_runs.id`` for the latest scoped row, if any."""
    row = _resolve_delete_row(
        gateway_model_id, profile, visibility=visibility, owner_user_id=owner_user_id
    )
    return row[0] if row else None


def delete_run_by_slug(
    gateway_model_id: str,
    profile: str = "base",
    *,
    visibility: str | None = None,
    owner_user_id: str | None = None,
) -> bool:
    """Delete the latest Postgres safety row for a gateway model slug (scoped
    to ``visibility``/``owner_user_id`` — see scan_db_data.delete_run_by_slug)."""
    run_id = resolve_delete_run_id(
        gateway_model_id, profile, visibility=visibility, owner_user_id=owner_user_id
    )
    if run_id is None:
        return False
    return delete_run_by_id(run_id)


def delete_run_by_id(run_id: str) -> bool:
    """Delete one safety_runs row by primary key (findings cascade)."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM public.safety_runs
                WHERE id = %(run_id)s::uuid
                """,
                {"run_id": run_id},
            )
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def delete_run(gateway_model_id: str, completed_at: str) -> bool:
    """Delete one safety_runs row (findings cascade). Returns True if removed."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM public.safety_runs
                WHERE gateway_model_id = %(gateway_model_id)s
                  AND completed_at = %(completed_at)s::timestamptz
                """,
                {"gateway_model_id": gateway_model_id, "completed_at": completed_at},
            )
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted
