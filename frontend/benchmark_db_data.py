"""
Postgres-backed data source for /benchmarks — same dict contracts as benchmark_data.py,
used only when POSTGRES_DSN is set and reachable.

Merges DB rows with any benchmark results not yet loaded. Detail uses artifact
fallback when the slug is missing from Postgres.
"""

from __future__ import annotations

import time
from typing import Any

from dbutils import load_repo_env, resolve_dsn

from frontend.benchmark_data import (
    PRIMARY_DIR,
    _attach_meta,
    _attach_per_subject,
    _format_ts,
    _paginate_detail_items,
)

load_repo_env()

_DSN_KEYS = ("POSTGRES_DSN", "DATABASE_URL")
_CONNECT_TIMEOUT_S = 2
_AVAILABILITY_TTL_S = 60.0
_avail_cache = {"checked_at": 0.0, "ok": False}

_KIND_LABELS = {
    "truthfulqa": "TruthfulQA",
    "ifeval": "IFEval",
    "mmlu": "MMLU",
    "tomi": "ToMi",
    "consistency": "Consistency",
    "mbpp": "MBPP",
    "quality": "QuALITY",
}


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
SELECT output_slug, source_filename, gateway_model_id, benchmark_key,
       headline_metric, headline_value, n_items, metrics, completed_at, config_json
FROM public.benchmark_runs b
WHERE {visibility_filter}
ORDER BY completed_at DESC NULLS LAST, output_slug
"""

_DETAIL_SQL = """
SELECT output_slug, source_filename, gateway_model_id, benchmark_key,
       headline_metric, headline_value, n_items, metrics, items, run_params,
       completed_at, config_json
FROM public.benchmark_runs b
WHERE output_slug = %(slug)s AND ({visibility_filter})
LIMIT 1
"""


def _metric_label(metric: str | None) -> str:
    if metric == "mean_f1":
        return "mean F1"
    if metric == "pass_rate":
        return "pass rate"
    return metric or "—"


def _headline_display(kind: str, metric: str | None, value: float | None) -> str:
    if value is None:
        return "—"
    if kind == "mbpp" or (metric == "mean_f1"):
        return f"{value:.3f}"
    if metric in ("accuracy", "pass_rate") or kind in (
        "truthfulqa",
        "mmlu",
        "tomi",
        "quality",
        "ifeval",
    ):
        return f"{value:.1%}"
    return f"{value:.4f}"


def _ts_raw(completed_at: Any) -> str:
    if completed_at is None:
        return ""
    if hasattr(completed_at, "isoformat"):
        return completed_at.isoformat()
    return str(completed_at)


def _extras_from_metrics(kind: str, metrics: dict[str, Any]) -> dict[str, Any]:
    if kind == "ifeval":
        return {"passed": metrics.get("passed"), "total": metrics.get("total")}
    if kind == "truthfulqa":
        return {
            "correct": metrics.get("correct"),
            "total_evaluated": metrics.get("total_evaluated"),
        }
    if kind == "mmlu":
        per_subject = metrics.get("per_subject") or {}
        return {"subjects": len(per_subject) if isinstance(per_subject, dict) else 0}
    if kind == "mbpp":
        summary = metrics.get("summary") or metrics
        return {"correct": summary.get("correct")}
    if kind == "quality":
        summary = metrics.get("summary") or metrics
        return {
            "hard_accuracy": summary.get("hard_accuracy"),
            "hard_questions": summary.get("hard_questions"),
        }
    return {}


def _summarize_db_run(row: tuple) -> dict:
    (
        output_slug,
        source_filename,
        gateway_model_id,
        benchmark_key,
        headline_metric,
        headline_value,
        n_items,
        metrics,
        completed_at,
        config_json,
    ) = row
    metrics = metrics or {}
    kind = benchmark_key
    ts_raw = _ts_raw(completed_at)
    summary = {
        "slug": output_slug,
        "filename": source_filename,
        "kind": kind,
        "kind_label": _KIND_LABELS.get(kind, kind.replace("_", " ").title()),
        "model": gateway_model_id or "—",
        "timestamp_raw": ts_raw,
        "timestamp": _format_ts(ts_raw),
        "headline_metric": _metric_label(headline_metric),
        "headline_value": headline_value,
        "headline_display": _headline_display(kind, headline_metric, headline_value),
        "n": n_items,
        "extras": _extras_from_metrics(kind, metrics),
    }
    if isinstance(config_json, dict) and config_json.get("benchmark_spec_digest"):
        summary["benchmark_spec_digest"] = config_json["benchmark_spec_digest"]
    return summary


def _build_detail_db(row: tuple) -> dict:
    summary = _summarize_db_run(row)
    kind = row[3]
    metrics = row[7] or {}
    items = row[8] or []
    run_params = row[9]
    detail = dict(summary)
    if run_params:
        detail["run_params"] = run_params
    if kind == "mmlu":
        _attach_per_subject(detail, metrics.get("per_subject") or {})
    _paginate_detail_items(detail, items)
    return _attach_meta(detail)


def fetch_detail_row(
    slug: str, *, visibility: str | None = None, owner_user_id: str | None = None
) -> tuple | None:
    """Raw DB row for detail / pagination loaders."""
    vis_clause, vis_params = _visibility_params(visibility=visibility, owner_user_id=owner_user_id)
    with _connect() as conn:
        with conn.cursor() as cur:
            params = {"slug": slug, **vis_params}
            cur.execute(_DETAIL_SQL.format(visibility_filter=vis_clause), params)
            return cur.fetchone()


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
    clause, params = visibility_clause("b", view_mode=visibility, user_id=owner_user_id, links_alias=True)
    return clause, params


def get_benchmarks_data_db() -> dict:
    """Every known benchmark run, straight from Postgres.

    Postgres is the single source of truth when a DSN is reachable — we do NOT
    merge in on-disk artifacts here. Disk is only consulted when no DSN is
    configured (see benchmark_data.get_benchmarks_data)."""
    vis_clause, vis_params = _visibility_params()

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_LIST_SQL.format(visibility_filter=vis_clause), vis_params)
            run_rows = cur.fetchall()
    rows = [_summarize_db_run(row) for row in run_rows]
    rows.sort(key=lambda r: r["timestamp_raw"], reverse=True)
    kinds = sorted({r["kind_label"] for r in rows})
    models = sorted({r["model"] for r in rows if r["model"] and not r["model"].startswith("—")})
    return {
        "has_runs": bool(rows),
        "search_paths": [str(PRIMARY_DIR)],
        "runs": rows,
        "kinds": kinds,
        "models": models,
    }


def get_benchmark_detail_db(
    slug: str, *, visibility: str | None = None, owner_user_id: str | None = None
) -> dict | None:
    """Detail-page payload from Postgres; None if slug isn't loaded."""
    vis_clause, vis_params = _visibility_params(visibility=visibility, owner_user_id=owner_user_id)

    with _connect() as conn:
        with conn.cursor() as cur:
            params = {"slug": slug, **vis_params}
            cur.execute(_DETAIL_SQL.format(visibility_filter=vis_clause), params)
            row = cur.fetchone()
            if row is None:
                return None
    return _build_detail_db(row)


def delete_run(
    slug: str, *, visibility: str | None = None, owner_user_id: str | None = None
) -> bool:
    """Delete one row from ``benchmark_runs``. Returns True if a row was removed.

    Scoped by ``visibility``/``owner_user_id`` so a public delete can never
    remove someone else's private row for the same slug, or vice versa.
    """
    vis_clause, vis_params = _visibility_params(visibility=visibility, owner_user_id=owner_user_id)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM public.benchmark_runs AS b WHERE output_slug = %(slug)s AND ({vis_clause})",
                {"slug": slug, **vis_params},
            )
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def delete_runs_for_combo(
    benchmark_key: str,
    model: str,
    *,
    visibility: str | None = None,
    owner_user_id: str | None = None,
) -> int:
    """Delete every benchmark run for one (benchmark, model) in the given scope."""
    vis_clause, vis_params = _visibility_params(visibility=visibility, owner_user_id=owner_user_id)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM public.benchmark_runs AS b
                WHERE b.benchmark_key = %(benchmark_key)s
                  AND b.gateway_model_id = %(model)s
                  AND ({vis_clause})
                """,
                {"benchmark_key": benchmark_key, "model": model, **vis_params},
            )
            deleted = cur.rowcount
        conn.commit()
    return deleted
