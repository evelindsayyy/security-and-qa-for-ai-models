"""Overview dashboard data: KPIs, chart aggregates, and recent activity feed."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from frontend import launch_registry

_TIER_ORDER = ("critical", "high", "medium", "low", "unknown")


def _parse_ts(value: str | None) -> datetime | None:
    if not value or value == "—":
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    if len(value) >= 10:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return None


def _detail_path(kind: str, slug: str, *, profile: str = "base") -> str:
    from frontend.read_context import read_context

    view_mode, _ = read_context()
    private = view_mode == "private"
    if kind == "scan":
        return f"/scans/{slug}/private" if private else f"/scans/{slug}"
    if kind == "safety":
        return f"/safety/{slug}/{profile}/private" if private else f"/safety/{slug}/{profile}"
    if kind == "eval":
        return f"/eval-run/{slug}/private" if private else f"/eval-run/{slug}"
    if kind == "benchmark":
        return f"/benchmarks/{slug}/private" if private else f"/benchmarks/{slug}"
    return ""


def _collect_stale_and_critical() -> dict[str, Any]:
    stale_count = 0
    critical_count = 0
    high_risk_scans = 0

    try:
        from frontend.scan_data import get_scans_data

        for row in get_scans_data().get("scans", []):
            if row.get("staleness", {}).get("stale"):
                stale_count += 1
            if row.get("severity_tier") == "critical":
                critical_count += 1
            if row.get("severity_tier") in ("critical", "high"):
                high_risk_scans += 1
    except Exception:
        pass

    try:
        from frontend.safety_data import get_safety_data

        for row in get_safety_data().get("models", []):
            if row.get("staleness", {}).get("stale"):
                stale_count += 1
            if row.get("tier") == "critical":
                critical_count += 1
    except Exception:
        pass

    try:
        from frontend.eval_run_data import get_runs_data

        for row in get_runs_data().get("runs", []):
            if row.get("staleness", {}).get("stale"):
                stale_count += 1
    except Exception:
        pass

    try:
        from frontend.benchmark_data import get_benchmarks_data

        for row in get_benchmarks_data().get("runs", []):
            if row.get("staleness", {}).get("stale"):
                stale_count += 1
    except Exception:
        pass

    return {
        "stale_count": stale_count,
        "critical_count": critical_count,
        "high_risk_scans": high_risk_scans,
    }


def _chart_aggregates() -> dict[str, Any]:
    scan_tiers: Counter[str] = Counter()
    safety_pass: list[dict[str, Any]] = []
    pillar_counts = {"scan": 0, "safety": 0, "eval": 0, "benchmark": 0}

    try:
        from frontend.scan_data import get_scans_data

        scans = get_scans_data().get("scans", [])
        pillar_counts["scan"] = len(scans)
        for row in scans:
            tier = (row.get("severity_tier") or "unknown").lower()
            scan_tiers[tier] += 1
    except Exception:
        pass

    try:
        from frontend.safety_data import get_safety_data

        models = get_safety_data().get("models", [])
        pillar_counts["safety"] = len(models)
        for row in models[:12]:
            rate = row.get("summary_pass_rate")
            if rate is None:
                continue
            label = row.get("display_name") or row.get("slug") or "—"
            safety_pass.append({"label": label, "value": round(rate * 100, 1)})
    except Exception:
        pass

    try:
        from frontend.eval_run_data import get_runs_data

        pillar_counts["eval"] = len(get_runs_data().get("runs", []))
    except Exception:
        pass

    try:
        from frontend.benchmark_data import get_benchmarks_data

        pillar_counts["benchmark"] = len(get_benchmarks_data().get("runs", []))
    except Exception:
        pass

    tier_labels = [t for t in _TIER_ORDER if scan_tiers.get(t)]
    return {
        "scan_tier_labels": tier_labels,
        "scan_tier_counts": [scan_tiers[t] for t in tier_labels],
        "safety_pass_labels": [p["label"] for p in safety_pass],
        "safety_pass_values": [p["value"] for p in safety_pass],
        "pillar_count_labels": ["Scans", "Safety", "Eval", "Benchmarks"],
        "pillar_count_values": [
            pillar_counts["scan"],
            pillar_counts["safety"],
            pillar_counts["eval"],
            pillar_counts["benchmark"],
        ],
        "has_overview_charts": bool(
            scan_tiers
            or safety_pass
            or any(pillar_counts.values())
        ),
    }


def _activity_events(limit: int = 12) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    def add(
        kind: str,
        label: str,
        ts: str | None,
        url: str | None = None,
        meta: str = "",
    ):
        parsed = _parse_ts(ts)
        events.append(
            {
                "kind": kind,
                "label": label,
                "ts": ts or "—",
                "sort": parsed or datetime.min,
                "url": url,
                "meta": meta,
            }
        )

    try:
        from frontend.scan_data import get_scans_data

        for row in get_scans_data().get("scans", [])[:20]:
            slug = row.get("slug") or ""
            add(
                "scan",
                f"Scan · {row.get('model_id', slug or '—')}",
                row.get("scanned_at"),
                url=_detail_path("scan", slug) if slug else None,
                meta=f"risk {row.get('overall_risk_score', '—')} · {row.get('severity_tier', '—')}",
            )
    except Exception:
        pass

    try:
        from frontend.safety_data import get_safety_data

        for row in get_safety_data().get("models", [])[:20]:
            slug = row.get("slug") or ""
            profile = row.get("profile") or "base"
            add(
                "safety",
                f"Safety · {row.get('display_name', slug or '—')}",
                row.get("completed_at"),
                url=_detail_path("safety", slug, profile=profile) if slug else None,
                meta=f"{row.get('pass_rate_display', '—')} pass",
            )
    except Exception:
        pass

    try:
        from frontend.eval_run_data import get_runs_data

        for row in get_runs_data().get("runs", [])[:20]:
            slug = row.get("slug") or ""
            add(
                "eval",
                f"Eval · {row.get('candidate_model', '—')}",
                row.get("timestamp"),
                url=_detail_path("eval", slug) if slug else None,
                meta=f"{row.get('suite', '—')} · overall {row.get('overall', '—')}",
            )
    except Exception:
        pass

    try:
        from frontend.benchmark_data import get_benchmarks_data

        for row in get_benchmarks_data().get("runs", [])[:20]:
            slug = row.get("slug") or ""
            add(
                "benchmark",
                f"Benchmark · {row.get('model', '—')}",
                row.get("timestamp") or row.get("timestamp_raw"),
                url=_detail_path("benchmark", slug) if slug else None,
                meta=f"{row.get('kind_label', '—')} · {row.get('headline_display', '—')}",
            )
    except Exception:
        pass

    events.sort(key=lambda e: e["sort"], reverse=True)
    return events[:limit]


def get_overview_data() -> dict[str, Any]:
    """Cross-pillar overview for the home dashboard."""
    try:
        from frontend.routes import _hub_context

        hub = _hub_context()
    except Exception:
        hub = {}

    rollup_count = 0
    try:
        from frontend.model_rollup import get_models_union

        rollup_count = len(get_models_union())
    except Exception:
        pass

    stale_stats = _collect_stale_and_critical()
    charts = _chart_aggregates()

    inflight = 0
    try:
        inflight = launch_registry.count_inflight()
    except Exception:
        pass

    return {
        **hub,
        **stale_stats,
        **charts,
        "rollup_count": rollup_count,
        "inflight_count": inflight,
        "activity": _activity_events(),
    }
