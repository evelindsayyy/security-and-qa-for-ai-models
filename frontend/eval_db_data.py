"""
Postgres-backed data source for /eval-run — same dict contracts as
eval_run_data.py, used only when EFFICACY_DB_DSN is set and reachable.

The SQL + connection + raw row reconstruction now live in the shared
repository ``evaluator/db/queries.py`` (the Repository Pattern), which the
JSON API also calls. This module is the dashboard's *presentation* layer over
that repository: it turns the repository's plain RunRecords into the exact
dicts the templates expect (comparison-table rows, the detail page payload).

Merges DB rows with eval runs not yet loaded. Detail uses artifact fallback
when a slug is missing from Postgres.
"""

from __future__ import annotations

import statistics
from datetime import timezone

from evaluator.db import queries
from frontend.path_safety import is_safe_slug

# Helpers shared with the file path — eval_run_data imports THIS module only
# lazily (inside functions), so this top-level import is not circular.
from frontend.eval_run_data import (
    RESULTS_DIR,
    _load_suite_questions,
    _percentile,
    _truncate,
)

# Connection + availability live in the repository now. Re-export them so the
# dispatcher (eval_run_data) and the tests keep referring to them as
# eval_db_data.available / eval_db_data._avail_cache exactly as before.
available = queries.available
_avail_cache = queries._avail_cache


# ---------------------------------------------------------------------------
# Presentation — turn repository RunRecords into the dicts the templates use.
# The aggregates here must match the file path (eval_run_data._aggregate_file)
# so DB-backed and file-backed pages render identically.
# ---------------------------------------------------------------------------


def _ts(dt) -> str:
    """timestamptz -> the ISO-8601 Z string format the JSONL rows use."""
    try:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return str(dt)


def _ordered_dims(results: list[dict]) -> list[str]:
    """Rubric-ordered dimension union. jsonb normalizes object key order, so
    the loader records the original order as a detail['dim_order'] ARRAY
    (arrays keep order); fall back to scores keys for rows loaded before
    that field existed."""
    return list(dict.fromkeys(
        d for r in results
        for d in (r["detail"].get("dim_order")
                  or list(r["detail"].get("scores") or {}))
    ))


def _aggregate_db_run(run: dict, results: list[dict]) -> dict:
    """Build the comparison-table row dict (same keys as _aggregate_file)."""
    n = len(results)
    ok = sum(1 for r in results
             if not r["candidate_failed"] and not r["judge_failed"])
    cand_fail = sum(1 for r in results if r["candidate_failed"])
    judge_fail = sum(1 for r in results if r["judge_failed"])

    dims = _ordered_dims(results)
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
        "inference_backend": (run["adaptation"] or {}).get("inference_backend", "gateway"),
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


def get_runs_data_db() -> dict:
    """DB-preferred merge of every known run (DB rows + not-yet-loaded files)."""
    # Import here, not at module top: eval_run_data imports this module lazily,
    # and these two helpers are the file-side fallbacks we merge with.
    from frontend.eval_run_data import _aggregate_file, _postprocess_runs

    with queries.connect() as conn:
        records = queries.fetch_runs(conn)
    db_runs = [_aggregate_db_run(rec["run"], rec["results"]) for rec in records]

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

    with queries.connect() as conn:
        rec = queries.fetch_run(conn, f"{slug}.jsonl")
    if rec is None or not rec["results"]:
        return None

    run, results = rec["run"], rec["results"]
    run_id = run["id"]
    source_file = run["source_file"]
    candidate = run["gateway_model_id"]
    judge = run["judge_model"]
    started_at = run["started_at"]
    adaptation = run["adaptation"] or {}

    questions_by_id = _load_suite_questions(
        adaptation.get("task_suite_version", ""))
    dims = _ordered_dims(results)

    questions_rows = []
    for r in results:
        scores = r["detail"].get("scores") or {}
        # rubric order for THIS row (jsonb lost the object key order)
        row_dims = [d for d in (r["detail"].get("dim_order") or list(scores))
                    if d in scores]
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
            "rationales": {d: scores[d]["rationale"] for d in row_dims},
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
