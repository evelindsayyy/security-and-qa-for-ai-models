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


def benchmark_delete_context(slug: str, *, error_message: str | None = None) -> dict | None:
    from frontend.benchmark_data import _artifact_paths, get_benchmark_detail
    from frontend.benchmark_launch import is_run_in_progress

    in_progress = is_run_in_progress(slug)
    detail = get_benchmark_detail(slug)
    if detail is None:
        return None
    model = detail.get("model", "—")
    benchmark = detail.get("kind_label", "—")
    paths = [f"benchmarks/results/{p.name}" for p in _artifact_paths(slug)]
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
        delete_url=url_for("benchmark_delete", slug=slug),
        cancel_url=url_for("benchmark_detail", slug=slug),
        cancel_label="Back to result",
        error_message=error_message
        or ("This run is still in progress and cannot be deleted yet." if in_progress else None),
        delete_disabled=in_progress,
    )


def scan_delete_context(slug: str, *, error_message: str | None = None) -> dict | None:
    from frontend.scan_data import delete_scan_paths, get_scan_detail
    from frontend.scan_launch import inflight_scan_slugs

    in_progress = slug in inflight_scan_slugs()
    detail = get_scan_detail(slug)
    if detail is None:
        return None
    model = detail.get("model_id", "—")
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
        paths=delete_scan_paths(slug),
        delete_url=url_for("scan_delete", slug=slug),
        cancel_url=url_for("scan_detail", slug=slug),
        cancel_label="Back to result",
        error_message=error_message
        or ("This scan is still running and cannot be deleted yet." if in_progress else None),
        delete_disabled=in_progress,
    )


def safety_delete_context(
    slug: str,
    profile: str,
    *,
    error_message: str | None = None,
) -> dict | None:
    from frontend.safety_data import delete_safety_paths, get_safety_detail
    from frontend.safety_launch import inflight_safety_keys

    in_progress = f"{slug}/{profile}" in inflight_safety_keys()
    detail = get_safety_detail(slug, profile)
    if detail is None:
        return None
    model = detail.get("gateway_model_id", slug)
    profile_label = profile if profile != "base" else "base profile"
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
        paths=delete_safety_paths(slug, profile),
        delete_url=url_for("safety_delete", slug=slug, profile=profile),
        cancel_url=url_for("safety_detail", slug=slug, profile=profile),
        cancel_label="Back to result",
        error_message=error_message
        or ("This run is still in progress and cannot be deleted yet." if in_progress else None),
        delete_disabled=in_progress,
    )


def eval_delete_context(slug: str, *, error_message: str | None = None) -> dict | None:
    from frontend.eval_launch import is_eval_run_in_progress
    from frontend.eval_run_data import delete_eval_run_paths, get_run_detail

    in_progress = is_eval_run_in_progress(slug)
    detail = get_run_detail(slug)
    if detail is None:
        return None
    candidate = detail.get("candidate_model", "—")
    judge = detail.get("judge_model") or "—"
    suite = detail.get("suite_version", "—")
    return _base_context(
        pillar_label="Efficacy eval",
        summary_items=[
            ("Candidate", candidate),
            ("Judge", judge),
            ("Suite", suite),
        ],
        removal_summary=[
            f"Eval run for {candidate} (judge: {judge}, suite: {suite})",
        ],
        paths=delete_eval_run_paths(slug),
        delete_url=url_for("eval_run_delete", slug=slug),
        cancel_url=url_for("eval_run_detail", slug=slug),
        cancel_label="Back to result",
        error_message=error_message
        or ("This run is still in progress and cannot be deleted yet." if in_progress else None),
        delete_disabled=in_progress,
    )
