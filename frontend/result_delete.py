"""Shared delete-confirmation page context for pillar result pages."""

from __future__ import annotations

from pathlib import Path

from flask import url_for

ROOT = Path(__file__).resolve().parent.parent


def _existing_repo_paths(repo_relative: list[str]) -> list[str]:
    """Return paths that exist on disk (for optional technical details)."""
    out: list[str] = []
    for rel in repo_relative:
        path = ROOT / rel.rstrip("/")
        if path.is_file() or path.is_dir():
            out.append(rel)
    return out


def _base_context(
    *,
    pillar_label: str,
    summary_items: list[tuple[str, str]],
    removal_summary: list[str],
    paths: list[str],
    delete_url: str,
    cancel_url: str,
    cancel_label: str,
    error_message: str | None = None,
    delete_disabled: bool = False,
) -> dict:
    return {
        "pillar_label": pillar_label,
        "summary_items": summary_items,
        "removal_summary": removal_summary,
        "paths": _existing_repo_paths(paths),
        "delete_url": delete_url,
        "cancel_url": cancel_url,
        "cancel_label": cancel_label,
        "error_message": error_message,
        "delete_disabled": delete_disabled,
    }


def benchmark_delete_context(
    slug: str,
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
    error_message: str | None = None,
) -> dict | None:
    from frontend.benchmark_data import _artifact_paths, get_benchmark_detail
    from frontend.benchmark_launch import is_run_in_progress

    private = visibility == "private"
    in_progress = is_run_in_progress(slug)
    detail = get_benchmark_detail(slug, visibility=visibility, owner_user_id=owner_user_id)
    if detail is None:
        return None
    model = detail.get("model", "—")
    benchmark = detail.get("kind_label", "—")
    paths = [f"benchmarks/results/{p.name}" for p in _artifact_paths(slug)]
    delete_endpoint = "benchmark_delete_private" if private else "benchmark_delete"
    detail_endpoint = "benchmark_detail_private" if private else "benchmark_detail"
    return _base_context(
        pillar_label="Benchmark",
        summary_items=[
            ("Model", model),
            ("Benchmark", benchmark),
        ],
        removal_summary=[
            f"Benchmark run for {model} ({benchmark})",
        ],
        paths=paths,
        delete_url=url_for(delete_endpoint, slug=slug),
        cancel_url=url_for(detail_endpoint, slug=slug),
        cancel_label="Back to result",
        error_message=error_message
        or ("This run is still in progress and cannot be deleted yet." if in_progress else None),
        delete_disabled=in_progress,
    )


def scan_delete_context(
    slug: str,
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
    error_message: str | None = None,
) -> dict | None:
    from frontend.scan_data import delete_scan_paths, get_scan_detail
    from frontend.scan_launch import inflight_scan_slugs

    private = visibility == "private"
    in_progress = slug in inflight_scan_slugs()
    detail = get_scan_detail(slug, visibility=visibility, owner_user_id=owner_user_id)
    if detail is None:
        return None
    model = detail.get("model_id", "—")
    delete_endpoint = "scan_delete_private" if private else "scan_delete"
    detail_endpoint = "scan_detail_private" if private else "scan_detail"
    return _base_context(
        pillar_label="Scanner",
        summary_items=[
            ("HF model", model),
            ("Tier", detail.get("severity_tier", "—")),
            ("Scanned", detail.get("scanned_at", "—")),
        ],
        removal_summary=[
            f"Scan results and findings for {model}",
        ],
        paths=delete_scan_paths(slug, visibility=visibility, owner_user_id=owner_user_id),
        delete_url=url_for(delete_endpoint, slug=slug),
        cancel_url=url_for(detail_endpoint, slug=slug),
        cancel_label="Back to result",
        error_message=error_message
        or ("This scan is still running and cannot be deleted yet." if in_progress else None),
        delete_disabled=in_progress,
    )


def safety_delete_context(
    slug: str,
    profile: str,
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
    error_message: str | None = None,
) -> dict | None:
    from frontend.safety_data import delete_safety_paths, get_safety_detail
    from frontend.safety_launch import inflight_safety_keys

    private = visibility == "private"
    in_progress = f"{slug}/{profile}" in inflight_safety_keys()
    detail = get_safety_detail(slug, profile, visibility=visibility, owner_user_id=owner_user_id)
    if detail is None:
        return None
    model = detail.get("gateway_model_id", slug)
    profile_label = profile if profile != "base" else "base profile"
    delete_endpoint = "safety_delete_private" if private else "safety_delete"
    detail_endpoint = "safety_detail_private" if private else "safety_detail"
    return _base_context(
        pillar_label="Safety",
        summary_items=[
            ("Model", model),
            ("Profile", profile),
            ("Tier", detail.get("tier", "—")),
            ("Completed", detail.get("completed_at", "—")),
        ],
        removal_summary=[
            f"Safety evaluation for {model} ({profile_label})",
        ],
        paths=delete_safety_paths(slug, profile, visibility=visibility, owner_user_id=owner_user_id),
        delete_url=url_for(delete_endpoint, slug=slug, profile=profile),
        cancel_url=url_for(detail_endpoint, slug=slug, profile=profile),
        cancel_label="Back to result",
        error_message=error_message
        or ("This run is still in progress and cannot be deleted yet." if in_progress else None),
        delete_disabled=in_progress,
    )


def eval_delete_context(
    slug: str,
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
    error_message: str | None = None,
) -> dict | None:
    from frontend.eval_launch import is_eval_run_in_progress
    from frontend.eval_run_data import delete_eval_run_paths, get_run_detail

    private = visibility == "private"
    in_progress = is_eval_run_in_progress(slug)
    detail = get_run_detail(slug, visibility=visibility, owner_user_id=owner_user_id)
    delete_endpoint = "eval_run_delete_private" if private else "eval_run_delete"
    detail_endpoint = "eval_run_detail_private" if private else "eval_run_detail"
    if detail is None:
        # Never silently redirect — show a disabled confirm page with the error.
        return _base_context(
            pillar_label="Efficacy eval",
            summary_items=[("Slug", slug)],
            removal_summary=[f"Eval run {slug}"],
            paths=delete_eval_run_paths(slug),
            delete_url=url_for(delete_endpoint, slug=slug),
            cancel_url=url_for("eval_run"),
            cancel_label="Back to eval runs",
            error_message=error_message
            or f"No eval run found for slug {slug!r}.",
            delete_disabled=True,
        )
    candidate = detail.get("candidate_model", "—")
    judge = detail.get("judge_model") or "—"
    suite = detail.get("suite_version") or detail.get("suite") or "—"
    return _base_context(
        pillar_label="Efficacy eval",
        summary_items=[
            ("Candidate", candidate),
            ("Judge", judge),
            ("Suite", suite),
        ],
        removal_summary=[
            f"All eval runs for {candidate} on suite {suite} in this catalog view",
            "(the list shows one row per combo — older duplicates are removed too)",
        ],
        paths=delete_eval_run_paths(slug),
        delete_url=url_for(delete_endpoint, slug=slug),
        cancel_url=url_for(detail_endpoint, slug=slug),
        cancel_label="Back to result",
        error_message=error_message
        or ("This run is still in progress and cannot be deleted yet." if in_progress else None),
        delete_disabled=in_progress,
    )
