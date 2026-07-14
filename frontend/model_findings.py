"""Top findings per pillar for the model nutrition-label page."""

from __future__ import annotations

from typing import Any


def get_model_findings(rollup: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return up to three headline findings per pillar for one model rollup."""
    return {
        "scan": _scan_findings(rollup),
        "safety": _safety_findings(rollup),
        "benchmark": _benchmark_findings(rollup),
    }


def _scan_findings(rollup: dict[str, Any]) -> list[dict[str, Any]]:
    scan = rollup.get("scan")
    if not scan or not scan.get("slug"):
        return []
    try:
        from frontend.scan_data import get_scan_detail

        detail = get_scan_detail(scan["slug"])
    except Exception:
        return []
    if not detail:
        return []
    slug = scan["slug"]
    return [
        {
            "title": row.get("title") or "Finding",
            "severity": row.get("severity") or "unknown",
            "label": row.get("source") or "",
            "detail_url": f"/scans/{slug}",
        }
        for row in (detail.get("findings") or [])[:3]
    ]


def _safety_findings(rollup: dict[str, Any]) -> list[dict[str, Any]]:
    safety = rollup.get("safety")
    if not safety or not safety.get("slug"):
        return []
    slug = safety["slug"]
    profile = safety.get("profile") or "base"
    try:
        from frontend.safety_data import get_safety_detail

        detail = get_safety_detail(slug, profile)
    except Exception:
        return []
    if not detail:
        return []
    findings = detail.get("findings") or []
    failed = [f for f in findings if not f.get("passed")]
    top = (failed or findings)[:3]
    return [
        {
            "title": row.get("title") or row.get("probe_id") or "Probe",
            "severity": row.get("severity") or "unknown",
            "label": "fail" if not row.get("passed") else "pass",
            "detail_url": f"/safety/{slug}/{profile}",
        }
        for row in top
    ]


def _benchmark_findings(rollup: dict[str, Any]) -> list[dict[str, Any]]:
    slug_key = rollup.get("slug")
    if not slug_key:
        return []
    try:
        from frontend.benchmark_data import (
            _DETAIL_ITEM_KEYS,
            _sort_detail_items,
            get_benchmark_detail,
            get_benchmarks_data,
        )
        from frontend.model_identity import gateway_slug
    except Exception:
        return []

    runs = [
        r
        for r in get_benchmarks_data().get("all_runs", [])
        if gateway_slug(r.get("model", "")) == slug_key and r.get("is_latest")
    ]
    if not runs:
        return []

    out: list[dict[str, Any]] = []
    for run in runs[:3]:
        bench_slug = run.get("slug")
        if not bench_slug:
            continue
        detail = get_benchmark_detail(bench_slug)
        if not detail:
            continue
        kind = detail.get("kind") or ""
        key = _DETAIL_ITEM_KEYS.get(kind, "")
        items = _sort_detail_items(kind, detail.get(key) or [])
        weak = _weak_benchmark_items(kind, items)
        for item in weak[:3]:
            if len(out) >= 3:
                break
            out.append(
                {
                    "title": _benchmark_item_title(kind, item),
                    "severity": _benchmark_item_severity(kind, item),
                    "label": detail.get("kind_label") or kind,
                    "detail_url": f"/benchmarks/{bench_slug}",
                }
            )
        if len(out) >= 3:
            break
    return out[:3]


def _weak_benchmark_items(kind: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if kind == "truthfulqa":
        return [i for i in items if i.get("model_answer") != i.get("correct_letter")]
    if kind == "consistency":
        return [i for i in items if (i.get("bertscore") or {}).get("mean_f1", 1) < 0.75]
    if kind in ("ifeval", "mmlu", "tomi", "mbpp", "quality"):
        failed = [i for i in items if i.get("passed") is False or i.get("answered") is False]
        return failed or items
    return items


def _benchmark_item_title(kind: str, item: dict[str, Any]) -> str:
    for key in ("question", "prompt", "problem", "title", "id", "key"):
        val = item.get(key)
        if val:
            text = str(val).strip()
            return text[:120] + ("…" if len(text) > 120 else "")
    return "Item"


def _benchmark_item_severity(kind: str, item: dict[str, Any]) -> str:
    if kind == "consistency":
        mean = (item.get("bertscore") or {}).get("mean_f1")
        if mean is not None and mean < 0.75:
            return "medium"
        return "low"
    if item.get("passed") is False:
        return "high"
    if item.get("answered") is False:
        return "medium"
    return "low"
