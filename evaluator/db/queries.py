"""
queries.py — the efficacy READ repository.

Single owner of the SQL + row reconstruction for reading eval runs out of
Postgres (efficacy_schema.sql). Both the dashboard (frontend/eval_db_data.py)
and the JSON API (api/) call these functions, so the SELECTs live in exactly
one place — the Repository Pattern. The runner never writes here; the loader
(load_results.py) is the only writer. This module only reads.

Two layers:

  - Connection: ``dsn()`` / ``available()`` / ``connect()``. Env-driven
    (EFFICACY_DB_DSN). Availability is TTL-cached so an unreachable database
    stalls one request by <=2s per minute, not every request.

  - Data access: ``fetch_runs(conn)`` / ``fetch_run(conn, source_file)`` /
    ``fetch_runs_for_model(conn, model)``. Pure given a DB-API connection (a
    psycopg connection in production, a fake in tests — same shape the loader's
    ``load_into`` accepts). Each returns plain "RunRecord" dicts::

        {"run": {<eval_runs columns>}, "results": [{<eval_results columns>}, ...]}

    Values come straight from the columns — no aggregation, no presentation.
    Callers (dashboard, API) shape them for their own output.
"""

from __future__ import annotations

import time

from dbutils.env import load_repo_env, resolve_dsn

load_repo_env()

_CONNECT_TIMEOUT_S = 2
_AVAILABILITY_TTL_S = 60.0

# Availability is probed at most once per TTL so an unreachable database
# stalls one request by <=2s per minute, not every request.
_avail_cache = {"checked_at": 0.0, "ok": False}


# ---------------------------------------------------------------------------
# Connection layer
# ---------------------------------------------------------------------------


def dsn() -> str | None:
    return resolve_dsn("EFFICACY_DB_DSN", "POSTGRES_DSN", "DATABASE_URL")


def available() -> bool:
    """True when a DSN is configured and the database answers a connect.

    Short-circuits to False with no DSN *before* importing psycopg, so a
    no-database deployment never needs the driver installed."""
    d = dsn()
    if not d:
        return False
    now = time.monotonic()
    if now - _avail_cache["checked_at"] < _AVAILABILITY_TTL_S:
        return _avail_cache["ok"]
    try:
        import psycopg

        with psycopg.connect(d, connect_timeout=_CONNECT_TIMEOUT_S):
            ok = True
    except Exception:
        ok = False
    _avail_cache.update(checked_at=now, ok=ok)
    return ok


def connect():
    """Open a psycopg connection to the configured DSN (caller closes it)."""
    import psycopg

    return psycopg.connect(dsn(), connect_timeout=_CONNECT_TIMEOUT_S)


# ---------------------------------------------------------------------------
# SQL — column order matches the reconstruction tuples below
# ---------------------------------------------------------------------------

def _run_visibility(
    *, visibility: str | None = None, owner_user_id: str | None = None
) -> tuple[str, dict]:
    """SQL visibility clause. Explicit ``visibility``/``owner_user_id`` (the
    resolved route scope) take precedence over the ambient session — omit
    both only for the list page, which still tracks the current toggle."""
    from dbutils.visibility import visibility_clause

    if visibility is None:
        from frontend.read_context import read_context

        visibility, owner_user_id = read_context()
    clause, params = visibility_clause("r", view_mode=visibility, user_id=owner_user_id, links_alias=True)
    return clause, params


_RUNS_SQL = """
SELECT r.id::text, r.source_file, r.gateway_model_id, r.judge_model,
       r.started_at, r.adaptation, r.config_json
FROM public.eval_runs r
WHERE {visibility_filter}
"""

_RESULTS_SQL = """
SELECT eval_run_id::text, task_id, metric, score, latency_ms, tokens_in,
       tokens_out, cost_usd, candidate_failed, judge_failed, detail
FROM public.eval_results
ORDER BY task_id
"""

_DETAIL_RUN_SQL = """
SELECT r.id::text, r.source_file, r.gateway_model_id, r.judge_model,
       r.started_at, r.adaptation
FROM public.eval_runs r
WHERE r.source_file = %(source_file)s AND ({visibility_filter})
"""
_DETAIL_RESULTS_SQL = """
SELECT task_id, score, latency_ms, tokens_in, tokens_out, cost_usd,
       candidate_failed, judge_failed, detail
FROM public.eval_results WHERE eval_run_id = %(run_id)s ORDER BY task_id
"""


# ---------------------------------------------------------------------------
# Row reconstruction (column tuple -> dict)
# ---------------------------------------------------------------------------


def _run_dict(row) -> dict:
    if len(row) >= 7:
        rid, sf, gm, jm, st, ad, config_json = row[:7]
    else:
        rid, sf, gm, jm, st, ad = row
        config_json = None
    out = {"id": rid, "source_file": sf, "gateway_model_id": gm,
            "judge_model": jm, "started_at": st, "adaptation": ad}
    if config_json is not None:
        out["config_json"] = config_json
    return out


def _result_dict(row) -> dict:
    """Detail-shaped result row (no eval_run_id / metric columns)."""
    task_id, score, lat, tin, tout, cost, cf, jf, detail = row
    return {"task_id": task_id, "score": score, "latency_ms": lat,
            "tokens_in": tin, "tokens_out": tout, "cost_usd": cost,
            "candidate_failed": cf, "judge_failed": jf, "detail": detail or {}}


# ---------------------------------------------------------------------------
# Public repository functions — return plain RunRecords
# ---------------------------------------------------------------------------


_RESULTS_LIST_SQL = """
SELECT eval_run_id::text, task_id, score, latency_ms, tokens_in, tokens_out,
       cost_usd, candidate_failed, judge_failed,
       detail->'scores' AS scores,
       detail->'dim_order' AS dim_order,
       (COALESCE(TRIM(detail->>'candidate_response'), '') = '') AS empty_response
FROM public.eval_results
WHERE metric = 'judge_score' AND eval_run_id = ANY(%(run_ids)s::uuid[])
ORDER BY task_id
"""


def fetch_runs_list(conn) -> list[dict]:
    """List-page runs: aggregate fields without full result detail JSONB."""
    vis_clause, vis_params = _run_visibility()
    with conn.cursor() as cur:
        cur.execute(_RUNS_SQL.format(visibility_filter=vis_clause), vis_params)
        runs = [_run_dict(r) for r in cur.fetchall()]
        run_ids = [r["id"] for r in runs if r["source_file"]]
        if not run_ids:
            return []
        cur.execute(_RESULTS_LIST_SQL, {"run_ids": run_ids})
        by_run: dict[str, list[dict]] = {}
        for (rid, task_id, score, lat, tin, tout, cost, cfail, jfail,
             scores, dim_order, empty_response) in cur.fetchall():
            by_run.setdefault(rid, []).append({
                "task_id": task_id, "score": score, "latency_ms": lat,
                "tokens_in": tin, "tokens_out": tout, "cost_usd": cost,
                "candidate_failed": cfail, "judge_failed": jfail,
                "detail": {
                    "scores": scores or {},
                    "dim_order": dim_order,
                    "candidate_response": "" if empty_response else "…",
                },
            })
    return [
        {"run": run, "results": by_run[run["id"]]}
        for run in runs
        if run["id"] in by_run and run["source_file"]
    ]


def fetch_runs(conn) -> list[dict]:
    """Every run with its judge_score results, as RunRecords.

    Runs with no results, or no source_file, are skipped (the same tolerance
    the dashboard's merge already assumed)."""
    vis_clause, vis_params = _run_visibility()
    with conn.cursor() as cur:
        cur.execute(_RUNS_SQL.format(visibility_filter=vis_clause), vis_params)
        runs = [_run_dict(r) for r in cur.fetchall()]
        cur.execute(_RESULTS_SQL)
        by_run: dict[str, list[dict]] = {}
        for (rid, task_id, metric, score, lat, tin, tout, cost,
             cfail, jfail, detail) in cur.fetchall():
            if metric != "judge_score":
                continue  # future rouge_l etc. rows aren't judge rows
            by_run.setdefault(rid, []).append({
                "task_id": task_id, "score": score, "latency_ms": lat,
                "tokens_in": tin, "tokens_out": tout, "cost_usd": cost,
                "candidate_failed": cfail, "judge_failed": jfail,
                "detail": detail or {},
            })
    return [
        {"run": run, "results": by_run[run["id"]]}
        for run in runs
        if run["id"] in by_run and run["source_file"]
    ]


def fetch_run(
    conn, source_file: str, *, visibility: str | None = None, owner_user_id: str | None = None
) -> dict | None:
    """One run by its source_file as a RunRecord, or None if absent.

    Returns the record even when ``results`` is empty; the caller decides
    whether an empty run is meaningful."""
    vis_clause, vis_params = _run_visibility(visibility=visibility, owner_user_id=owner_user_id)
    with conn.cursor() as cur:
        params = {"source_file": source_file, **vis_params}
        cur.execute(_DETAIL_RUN_SQL.format(visibility_filter=vis_clause), params)
        hit = cur.fetchone()
        if hit is None:
            return None
        run = _run_dict(hit)
        cur.execute(_DETAIL_RESULTS_SQL, {"run_id": run["id"]})
        results = [_result_dict(r) for r in cur.fetchall()]
    return {"run": run, "results": results}


def fetch_runs_for_model(conn, gateway_model_id: str) -> list[dict]:
    """All RunRecords whose run.gateway_model_id matches exactly."""
    return [rec for rec in fetch_runs(conn)
            if rec["run"]["gateway_model_id"] == gateway_model_id]
