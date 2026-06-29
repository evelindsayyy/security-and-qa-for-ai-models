"""Shared delete-confirmation page context for pillar result pages."""

from __future__ import annotations

from flask import url_for


def _db_note() -> str | None:
    try:
        from frontend import benchmark_db_data

        if benchmark_db_data.available():
            return "Postgres"
    except Exception:
        pass
    return None


def benchmark_delete_context(slug: str) -> dict | None:
    from frontend.benchmark_data import _artifact_paths, get_benchmark_detail
    from frontend.benchmark_launch import is_run_in_progress

    if is_run_in_progress(slug):
        return {"error": "cannot delete while the run is still in progress"}
    detail = get_benchmark_detail(slug)
    if detail is None:
        return None
    paths = [p.name for p in _artifact_paths(slug)]
    if not paths:
        paths = [f"{slug}.json/jsonl/log"]
    return {
        "pillar_label": "Benchmark",
        "summary_items": [
            ("Model", detail.get("model", "—")),
            ("Benchmark", detail.get("kind_label", "—")),
            ("Slug", slug),
        ],
        "paths": [f"benchmarks/results/{name}" for name in paths],
        "delete_url": url_for("benchmark_delete", slug=slug),
        "cancel_url": url_for("benchmark_detail", slug=slug),
        "cancel_label": "Back to result",
        "db_note": _db_note(),
    }


def scan_delete_context(slug: str) -> dict | None:
    from frontend.scan_data import delete_scan_paths, get_scan_detail
    from frontend.scan_launch import inflight_scan_slugs

    if slug in inflight_scan_slugs():
        return {"error": "cannot delete while the scan is still in progress"}
    detail = get_scan_detail(slug)
    if detail is None:
        return None
    return {
        "pillar_label": "Scanner",
        "summary_items": [
            ("HF model", detail.get("model_id", "—")),
            ("Tier", detail.get("severity_tier", "—")),
            ("Slug", slug),
        ],
        "paths": delete_scan_paths(slug),
        "delete_url": url_for("scan_delete", slug=slug),
        "cancel_url": url_for("scan_detail", slug=slug),
        "cancel_label": "Back to result",
        "db_note": _db_note(),
    }


def safety_delete_context(slug: str, profile: str) -> dict | None:
    from frontend.safety_data import delete_safety_paths, get_safety_detail
    from frontend.safety_launch import inflight_safety_keys

    if f"{slug}/{profile}" in inflight_safety_keys():
        return {"error": "cannot delete while the run is still in progress"}
    detail = get_safety_detail(slug, profile)
    if detail is None:
        return None
    return {
        "pillar_label": "Safety",
        "summary_items": [
            ("Model", detail.get("gateway_model_id", "—")),
            ("Profile", profile),
            ("Tier", detail.get("tier", "—")),
            ("Slug", slug),
        ],
        "paths": delete_safety_paths(slug, profile),
        "delete_url": url_for("safety_delete", slug=slug, profile=profile),
        "cancel_url": url_for("safety_detail", slug=slug, profile=profile),
        "cancel_label": "Back to result",
        "db_note": _db_note(),
    }


def eval_delete_context(slug: str) -> dict | None:
    from frontend.eval_launch import is_eval_run_in_progress
    from frontend.eval_run_data import delete_eval_run_paths, get_run_detail

    if is_eval_run_in_progress(slug):
        return {"error": "cannot delete while the run is still in progress"}
    detail = get_run_detail(slug)
    if detail is None:
        return None
    return {
        "pillar_label": "Efficacy eval",
        "summary_items": [
            ("Candidate", detail.get("candidate_model", "—")),
            ("Judge", detail.get("judge_model") or "—"),
            ("Suite", detail.get("suite_version", "—")),
            ("Slug", slug),
        ],
        "paths": delete_eval_run_paths(slug),
        "delete_url": url_for("eval_run_delete", slug=slug),
        "cancel_url": url_for("eval_run_detail", slug=slug),
        "cancel_label": "Back to result",
        "db_note": _db_note(),
    }
