"""
Postgres-backed data source for /eval-run — same dict contracts as
eval_run_data.py, used only when EFFICACY_DB_DSN is set and reachable.

Freshness model: the database holds whatever the loader last synced; brand-new
runs exist only as files until the next `load_results.py --apply`. So
`get_runs_data_db()` MERGES: DB rows are preferred per slug, and any results
file on disk that isn't in the DB yet is aggregated from the file. The detail
page falls back to files via the dispatcher when a slug isn't in the DB.

Severable by design: delete this module and the dispatcher in
eval_run_data.py reverts to pure file reads (the week-5 API will replace
this layer entirely).
"""

from __future__ import annotations

import os
import statistics
import time
from datetime import timezone

from frontend.path_safety import is_safe_slug

# Helpers shared with the file path — eval_run_data imports THIS module only
# lazily (inside functions), so this top-level import is not circular.
from frontend.eval_run_data import (
    RESULTS_DIR,
    _load_suite_questions,
    _percentile,
    _truncate,
)

_CONNECT_TIMEOUT_S = 2
_AVAILABILITY_TTL_S = 60.0

# Availability is probed at most once per TTL so an unreachable database
# stalls one request by <=2s per minute, not every request.
_avail_cache = {"checked_at": 0.0, "ok": False}


def _dsn() -> str | None:
    return os.environ.get("EFFICACY_DB_DSN") or None


def available() -> bool:
    """True when a DSN is configured and the database answers a connect."""
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


# ---------------------------------------------------------------------------
# Row reconstruction — compute the SAME aggregates as the file path, from the
# eval_results rows, so both paths render identically.
# ---------------------------------------------------------------------------

_RUNS_SQL = """
SELECT r.id::text, r.source_file, r.gateway_model_id, r.judge_model,
       r.started_at, r.adaptation
FROM public.eval_runs r
"""

_RESULTS_SQL = """
SELECT eval_run_id::text, task_id, metric, score, latency_ms, tokens_in,
       tokens_out, cost_usd, candidate_failed, judge_failed, detail
FROM public.eval_results
ORDER BY task_id
"""

_DETAIL_RUN_SQL = _RUNS_SQL + " WHERE r.source_file = %(source_file)s"
_DETAIL_RESULTS_SQL = """
SELECT task_id, score, latency_ms, tokens_in, tokens_out, cost_usd,
       candidate_failed, judge_failed, detail
FROM public.eval_results WHERE eval_run_id = %(run_id)s ORDER BY task_id
"""


def _ts(dt) -> str:
    """timestamptz -> the ISO-8601 Z string format the JSONL rows use."""
    try:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return str(dt)


def _aggregate_db_run(run: dict, results: list[dict]) -> dict:
    """Build the comparison-table row dict (same keys as _aggregate_file)."""
    n = len(results)
    ok = sum(1 for r in results
             if not r["candidate_failed"] and not r["judge_failed"])
    cand_fail = sum(1 for r in results if r["candidate_failed"])
    judge_fail = sum(1 for r in results if r["judge_failed"])

    dims = list(dict.fromkeys(
        d for r in results for d in (r["detail"].get("scores") or {})))
    dim_means: dict[str, float | None] = {}
    for d in dims:
        vals = [r["detail"]["scores"][d]["score"] for r in results
                if d in (r["detail"].get("scores") or {})]
        dim_means[d] = statistics.mean(vals) if vals else None

    overall_vals = [r["score"] for r in results if r["score"] is not None]
    latencies = [r["latency_ms"] for r in results]
    empty = sum(1 for r in results
                if not (r["detail"].get("candidate_response") or "").strip())

    slug = (run["source_file"] or "").removesuffix(".jsonl")
    return {
        "filename": run["source_file"],
        "slug": slug,
        "timestamp": _ts(run["started_at"]),
        "suite": (run["adaptation"] or {}).get("task_suite_version", ""),
        "candidate_model": run["gateway_model_id"],
        "judge_model": run["judge_model"],
        "n": n,
        "ok": ok,
        "cand_fail": cand_fail,
        "judge_fail": judge_fail,
        "dims": dims,
        "dim_means": dim_means,
        "overall": statistics.mean(overall_vals) if overall_vals else None,
        "mean_latency_ms": int(statistics.mean(latencies)) if latencies else 0,
        "p95_latency_ms": int(_percentile(latencies, 95)),
        "total_cost_usd": float(sum(r["cost_usd"] or 0 for r in results)),
        "note": f"⚠ {empty}/{n} empty" if empty else "",
    }


def _fetch_all_runs(conn) -> list[dict]:
    """All DB runs with their results, as comparison-table row dicts."""
    with conn.cursor() as cur:
        cur.execute(_RUNS_SQL)
        runs = [
            {"id": rid, "source_file": sf, "gateway_model_id": gm,
             "judge_model": jm, "started_at": st, "adaptation": ad}
            for rid, sf, gm, jm, st, ad in cur.fetchall()
        ]
        cur.execute(_RESULTS_SQL)
        by_run: dict[str, list[dict]] = {}
        for (rid, task_id, metric, score, lat, tin, tout, cost,
             cfail, jfail, detail) in cur.fetchall():
            if metric != "judge_score":
                continue  # future rouge_l etc. rows don't belong in this table
            by_run.setdefault(rid, []).append({
                "task_id": task_id, "score": score, "latency_ms": lat,
                "tokens_in": tin, "tokens_out": tout, "cost_usd": cost,
                "candidate_failed": cfail, "judge_failed": jfail,
                "detail": detail or {},
            })
    return [
        _aggregate_db_run(run, by_run[run["id"]])
        for run in runs
        if run["id"] in by_run and run["source_file"]
    ]


def get_runs_data_db() -> dict:
    """DB-preferred merge of every known run (DB rows + not-yet-loaded files)."""
    # Import here, not at module top: eval_run_data imports this module lazily,
    # and these two helpers are the file-side fallbacks we merge with.
    from frontend.eval_run_data import _aggregate_file, _postprocess_runs

    with _connect() as conn:
        db_runs = _fetch_all_runs(conn)

    seen_slugs = {r["slug"] for r in db_runs}
    file_runs = []
    if RESULTS_DIR.exists():
        for path in RESULTS_DIR.glob("*.jsonl"):
            if "_trace" in path.name or path.stem in seen_slugs:
                continue
            row = _aggregate_file(path)
            if row is not None:
                file_runs.append(row)

    return _postprocess_runs(db_runs + file_runs)


def get_run_detail_db(slug: str) -> dict | None:
    """Detail-page payload from the DB; None if the slug isn't loaded
    (the dispatcher then falls back to the file)."""
    if not is_safe_slug(slug):
        return None

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(_DETAIL_RUN_SQL, {"source_file": f"{slug}.jsonl"})
        hit = cur.fetchone()
        if hit is None:
            return None
        run_id, source_file, candidate, judge, started_at, adaptation = hit
        cur.execute(_DETAIL_RESULTS_SQL, {"run_id": run_id})
        results = [
            {"task_id": t, "score": s, "latency_ms": lat, "tokens_in": tin,
             "tokens_out": tout, "cost_usd": cost, "candidate_failed": cf,
             "judge_failed": jf, "detail": d or {}}
            for t, s, lat, tin, tout, cost, cf, jf, d in cur.fetchall()
        ]
    if not results:
        return None

    adaptation = adaptation or {}
    questions_by_id = _load_suite_questions(
        adaptation.get("task_suite_version", ""))
    dims = list(dict.fromkeys(
        d for r in results for d in (r["detail"].get("scores") or {})))

    questions_rows = []
    for r in results:
        scores = r["detail"].get("scores") or {}
        if r["candidate_failed"]:
            status = "CAND_FAIL"
        elif r["judge_failed"]:
            status = "JUDGE_FAIL"
        else:
            status = "OK"
        questions_rows.append({
            "question_id": r["task_id"],
            "question": _truncate(questions_by_id.get(r["task_id"], ""), 90),
            "candidate_empty": not (
                r["detail"].get("candidate_response") or "").strip(),
            "dim_scores": {
                d: (scores[d]["score"] if d in scores else None) for d in dims
            },
            "rationales": {d: scores[d]["rationale"] for d in scores},
            "overall": r["score"],
            "latency_ms": r["latency_ms"],
            "cost_usd": float(r["cost_usd"] or 0),
            "status": status,
            "error": r["detail"].get("error"),
        })

    latencies = [r["latency_ms"] for r in results]
    overall_vals = [r["score"] for r in results if r["score"] is not None]
    return {
        "slug": slug,
        "filename": source_file,
        "run_id": run_id,
        "timestamp": _ts(started_at),
        "candidate_model": candidate,
        "candidate_model_version": adaptation.get("candidate_model_version", ""),
        "judge_model": judge,
        "suite_version": adaptation.get("task_suite_version", ""),
        "rubric_version": adaptation.get("rubric_version", ""),
        "system_prompt_version": adaptation.get("system_prompt_version", ""),
        "judge_prompt_version": adaptation.get("judge_prompt_version", ""),
        "temperature": adaptation.get("temperature"),
        "max_tokens": adaptation.get("max_tokens"),
        "n": len(results),
        "ok": sum(1 for r in results
                  if not r["candidate_failed"] and not r["judge_failed"]),
        "cand_fail": sum(1 for r in results if r["candidate_failed"]),
        "judge_fail": sum(1 for r in results if r["judge_failed"]),
        "dims": dims,
        "mean_overall": (round(statistics.mean(overall_vals), 2)
                         if overall_vals else None),
        "mean_latency_ms": int(statistics.mean(latencies)) if latencies else 0,
        "p95_latency_ms": int(_percentile(latencies, 95)),
        "total_cost_usd": round(float(
            sum(r["cost_usd"] or 0 for r in results)), 4),
        "total_prompt_tokens": sum(r["tokens_in"] or 0 for r in results),
        "total_completion_tokens": sum(r["tokens_out"] or 0 for r in results),
        "questions": questions_rows,
    }
