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
    adaptation = run["adaptation"] or {}
    data = {
        "filename": run["source_file"],
        "slug": slug,
        "timestamp": _ts(run["started_at"]),
        "suite": adaptation.get("task_suite_version", ""),
        "rubric_version": adaptation.get("rubric_version", ""),
        "system_prompt_version": adaptation.get("system_prompt_version", ""),
        "judge_prompt_version": adaptation.get("judge_prompt_version", ""),
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
    _attach_execution_pass_rate(data, results, adaptation)
    config_json = run.get("config_json")
    if isinstance(config_json, dict):
        data["config_json"] = config_json
        digests = config_json.get("eval_suite_file_digests")
        if isinstance(digests, dict):
            data["eval_suite_file_digests"] = digests
    return data


def _execution_for_results(results: list[dict], adaptation: dict) -> dict | None:
    """Full functional scoring (run totals + per-question rows) for the DB
    result rows, or None for a judge-only suite / any error. Scores from the DB
    payload so the Postgres path matches the file path (``_execution_summary``).
    Never raises: a scoring hiccup must not break the dashboard."""
    suite_version = adaptation.get("task_suite_version", "")
    if not suite_version:
        return None
    try:
        import execution_eval  # lazy: a bad import mustn't break the dashboard

        rows = [
            {
                "question_id": r["task_id"],
                "candidate_response": (r["detail"] or {}).get("candidate_response", ""),
                "overall": r["score"],
            }
            for r in results
        ]
        ex = execution_eval.score_results_rows(rows, suite_version)
    except Exception:
        return None
    return ex if ex.get("n") else None


def _attach_execution_pass_rate(
    data: dict, results: list[dict], adaptation: dict
) -> None:
    """Add the functional pass-rate for execution suites (SQL/JSON/numeric) to a
    comparison-table row. Judge-only suites leave the field unset, so the table
    renders ``—``."""
    ex = _execution_for_results(results, adaptation)
    if ex:
        data["execution_pass_rate"] = ex["pass_rate"]
        data["execution_passed"] = ex["passed"]
        data["execution_n"] = ex["n"]


def get_runs_data_db() -> dict:
    """Every known eval run, straight from Postgres.

    Postgres is the single source of truth when a DSN is reachable — we do NOT
    merge in on-disk artifacts here. Disk is only consulted when no DSN is
    configured (see eval_run_data.get_runs_data)."""
    from frontend.eval_run_data import _postprocess_runs

    with queries.connect() as conn:
        records = queries.fetch_runs_list(conn)
    db_runs = [_aggregate_db_run(rec["run"], rec["results"]) for rec in records]

    return _postprocess_runs(db_runs)


def get_run_detail_db(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> dict | None:
    """Detail-page payload from the DB; None if the slug isn't loaded
    (the dispatcher then falls back to the file)."""
    if not is_safe_slug(slug):
        return None

    with queries.connect() as conn:
        rec = queries.fetch_run(
            conn, f"{slug}.jsonl", visibility=visibility, owner_user_id=owner_user_id
        )
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

    # Execution (functional) scoring, if this is an execution suite — drives the
    # per-question pass/fail and the run-level exec metric. None on judge-only
    # suites so those rows render — instead of a spurious "fail".
    exec_summary = _execution_for_results(results, adaptation)
    exec_by_qid = {
        row["question_id"]: row for row in (exec_summary or {}).get("rows", [])
    }

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
            "exec_passed": (exec_by_qid.get(r["task_id"]) or {}).get("passed"),
            "exec_error": (exec_by_qid.get(r["task_id"]) or {}).get("error"),
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
        "execution": (
            {"pass_rate": exec_summary["pass_rate"],
             "passed": exec_summary["passed"], "n": exec_summary["n"],
             "check": exec_summary.get("check")}
            if exec_summary else None
        ),
    }


def run_row_exists(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> bool:
    """True when an ``eval_runs`` row exists for this slug in the given scope.

    Unlike ``get_run_detail_db``, this does not require judge_score results —
    used so delete can tell "row existed" even for sparse/smoke stubs.
    """
    if not is_safe_slug(slug):
        return False
    with queries.connect() as conn:
        rec = queries.fetch_run(
            conn, f"{slug}.jsonl", visibility=visibility, owner_user_id=owner_user_id
        )
    return rec is not None


def delete_run(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> bool:
    """Delete one eval_runs row (results cascade). Returns True if removed.

    Scoped by ``visibility``/``owner_user_id`` so a public delete can never
    remove someone else's private row for the same slug, or vice versa.
    """
    from dbutils.visibility import visibility_clause

    if not is_safe_slug(slug):
        return False
    source_file = f"{slug}.jsonl"
    vis_clause, vis_params = visibility_clause(
        "public.eval_runs", view_mode=visibility, user_id=owner_user_id, links_alias=True
    )
    with queries.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM public.eval_runs
                WHERE source_file = %(source_file)s AND ({vis_clause})
                """,
                {"source_file": source_file, **vis_params},
            )
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def delete_runs_for_combo(
    suite_key: str,
    candidate: str,
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> int:
    """Delete every eval run for one (suite, candidate) in the given scope."""
    from dbutils.visibility import visibility_clause

    vis_clause, vis_params = visibility_clause("r", view_mode=visibility, user_id=owner_user_id)
    with queries.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM public.eval_runs AS r
                USING public.task_suites AS s
                WHERE r.suite_id = s.id
                  AND s.suite_key = %(suite_key)s
                  AND r.gateway_model_id = %(candidate)s
                  AND ({vis_clause})
                """,
                {"suite_key": suite_key, "candidate": candidate, **vis_params},
            )
            deleted = cur.rowcount
        conn.commit()
    return deleted
