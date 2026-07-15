"""
Cross-pillar model rollup — backs ``GET /api/models`` and ``GET
/api/models/<slug>``, plus the ``/models`` risk columns, ``/compare``
route, and recommendation block.

Scanning lives in HF-repo-id space; safety/eval/benchmark live in gateway-id
space. There is no mapping table between the two (a shared `models` Postgres
table is deferred), so this is a **union**:
one row per model with data in at least one pillar, not an inner join. A
model's row simply has ``null`` for whichever pillars have no data for it.
"""

from __future__ import annotations

import hashlib
import json
import time

from frontend import benchmark_data, eval_run_data, safety_data, scan_data
from frontend.oss_gateway_hf import gateway_slug_for_hf_repo
from frontend.model_identity import gateway_slug, hf_repo_id

_UNION_CACHE: list[dict] | None = None
_UNION_CACHE_AT: float = 0.0
_UNION_CACHE_TTL_SEC = 45.0


def _row(by_key: dict[str, dict], key: str, display_name: str) -> dict:
    row = by_key.get(key)
    if row is None:
        row = {
            "slug": key,
            "display_name": display_name,
            "scan": None,
            "safety": None,
            "eval": None,
            "benchmark": None,
        }
        by_key[key] = row
    return row


def benchmark_score(row: dict) -> float | None:
    """Mean headline_value across benchmark kinds (0–1 scale)."""
    benchmark = row.get("benchmark")
    if not benchmark or not benchmark.get("kinds"):
        return None
    values = [
        info["headline_value"]
        for info in benchmark["kinds"].values()
        if info.get("headline_value") is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def pillar_subscores(row: dict) -> dict[str, float | None]:
    """Normalize each pillar to 0–100 for aggregate ranking."""
    scan = row.get("scan")
    safety = row.get("safety")
    eval_ = row.get("eval")
    bench = benchmark_score(row)
    return {
        "scan": (
            100 - float(scan["overall_risk_score"])
            if scan and scan.get("overall_risk_score") is not None
            else None
        ),
        "safety": (
            float(safety["pass_rate"]) * 100
            if safety and safety.get("pass_rate") is not None
            else None
        ),
        "eval": (
            float(eval_.get("avg_overall", eval_.get("best_overall"))) / 5 * 100
            if eval_
            and (
                eval_.get("avg_overall") is not None
                or eval_.get("best_overall") is not None
            )
            else None
        ),
        "benchmark": bench * 100 if bench is not None else None,
    }


def aggregate_score(row: dict) -> float | None:
    """Mean of available pillar sub-scores (missing pillars excluded)."""
    available = [v for v in pillar_subscores(row).values() if v is not None]
    if not available:
        return None
    return sum(available) / len(available)


def rollup_inputs_hash(row: dict) -> str:
    """Stable hash of pillar evidence — used to invalidate AI summary cache."""
    payload = {
        "scan": row.get("scan"),
        "safety": row.get("safety"),
        "eval": row.get("eval"),
        "benchmark": row.get("benchmark"),
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def enrich_row(row: dict) -> dict:
    """Attach subscores, aggregate, benchmark norm, and inputs hash."""
    out = dict(row)
    subscores = pillar_subscores(out)
    out["subscores"] = subscores
    out["aggregate"] = aggregate_score(out)
    bench = benchmark_score(out)
    if out.get("benchmark"):
        out["benchmark"] = dict(out["benchmark"])
        out["benchmark"]["norm"] = bench * 100 if bench is not None else None
    out["inputs_hash"] = rollup_inputs_hash(out)
    return out


def empty_gateway_rollup(gateway_id: str) -> dict:
    """Zero-data rollup for a live gateway model with no pillar runs yet."""
    return enrich_row({
        "slug": gateway_slug(gateway_id),
        "display_name": gateway_id,
        "scan": None,
        "safety": None,
        "eval": None,
        "benchmark": None,
    })


def clear_models_union_cache() -> None:
    """Reset in-process union cache (for tests)."""
    global _UNION_CACHE, _UNION_CACHE_AT
    _UNION_CACHE = None
    _UNION_CACHE_AT = 0.0


def lookup_rollup_for_gateway(gateway_id: str, *, by_slug: dict[str, dict] | None = None) -> dict:
    """Rollup for a gateway catalog id — merges run data or returns empty shell."""
    slug = gateway_slug(gateway_id)
    if by_slug is not None:
        existing = by_slug.get(slug)
    else:
        existing = get_model_rollup(slug)
    if existing is not None:
        return existing
    return empty_gateway_rollup(gateway_id)


def rollups_for_gateway_ids(gateway_ids: list[str]) -> dict[str, dict]:
    """Batch rollup lookup — builds the union once."""
    by_slug = {row["slug"]: row for row in get_models_union()}
    return {gid: lookup_rollup_for_gateway(gid, by_slug=by_slug) for gid in gateway_ids}


def _add_scan_rows(by_key: dict[str, dict], *, scans: list[dict] | None = None) -> None:
    if scans is None:
        scans = scan_data.get_scans_data().get("scans", [])
    for s in scans:
        key = s["slug"]
        model_id = s.get("model_id") or hf_repo_id(key)
        scan_summary = {
            "slug": s["slug"],
            "tier": s["severity_tier"],
            "overall_risk_score": s["overall_risk_score"],
        }
        row = _row(by_key, key, model_id)
        row["scan"] = scan_summary
        gw_slug = gateway_slug_for_hf_repo(model_id)
        if gw_slug and gw_slug != key:
            grow = _row(by_key, gw_slug, model_id)
            grow["scan"] = scan_summary


def _add_safety_rows(by_key: dict[str, dict], *, models: list[dict] | None = None) -> None:
    if models is None:
        models = safety_data.get_safety_data().get("models", [])
    for m in models:
        key = gateway_slug(m["gateway_model_id"])
        row = _row(by_key, key, m.get("display_name") or m["gateway_model_id"])
        row["safety"] = {
            "slug": m["slug"],
            "profile": m["profile"],
            "tier": m["tier"],
            "pass_rate": m["summary_pass_rate"],
        }


def _add_eval_rows(by_key: dict[str, dict], *, runs: list[dict] | None = None) -> None:
    if runs is None:
        runs = eval_run_data.get_runs_data().get("runs", [])
    runs_by_key: dict[str, list[dict]] = {}
    for r in runs:
        runs_by_key.setdefault(gateway_slug(r["candidate_model"]), []).append(r)

    for key, runs in runs_by_key.items():
        row = _row(by_key, key, runs[0]["candidate_model"])
        overalls = [r["overall"] for r in runs if r.get("overall") is not None]
        latencies = [r["mean_latency_ms"] for r in runs if r.get("mean_latency_ms") is not None]
        avg_overall = round(sum(overalls) / len(overalls), 2) if overalls else None
        row["eval"] = {
            "n_runs": len(runs),
            "suites": sorted({r["suite"] for r in runs}),
            "avg_overall": avg_overall,
            # Alias kept for older callers/templates during transition.
            "best_overall": avg_overall,
            "mean_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
            "total_cost_usd": sum(r.get("total_cost_usd") or 0 for r in runs),
        }


def _add_benchmark_rows(by_key: dict[str, dict], *, runs: list[dict] | None = None) -> None:
    if runs is None:
        runs = benchmark_data.get_benchmarks_data().get("runs", [])
    kinds_by_key: dict[str, dict[str, dict]] = {}
    for r in runs:
        model = r.get("model")
        if not model or model == "—":
            continue
        key = gateway_slug(model)
        kinds_by_key.setdefault(key, {})[r["kind"]] = {
            "headline_value": r.get("headline_value"),
            "headline_display": r.get("headline_display"),
            "score_class": r.get("score_class"),
        }

    for key, kinds in kinds_by_key.items():
        row = _row(by_key, key, key)
        row["benchmark"] = {"kinds": kinds}


def get_models_union(*, payloads: dict | None = None) -> list[dict]:
    """One row per model with data in at least one pillar."""
    global _UNION_CACHE, _UNION_CACHE_AT
    now = time.monotonic()
    if payloads is None and _UNION_CACHE is not None and (now - _UNION_CACHE_AT) < _UNION_CACHE_TTL_SEC:
        return _UNION_CACHE

    by_key: dict[str, dict] = {}
    if payloads is not None:
        _add_scan_rows(by_key, scans=(payloads.get("scans") or {}).get("scans", []))
        from frontend.scan_links import apply_scan_links

        apply_scan_links(by_key)
        _add_safety_rows(by_key, models=(payloads.get("safety") or {}).get("models", []))
        _add_eval_rows(by_key, runs=(payloads.get("eval") or {}).get("runs", []))
        _add_benchmark_rows(by_key, runs=(payloads.get("benchmarks") or {}).get("runs", []))
    else:
        _add_scan_rows(by_key)
        from frontend.scan_links import apply_scan_links

        apply_scan_links(by_key)
        _add_safety_rows(by_key)
        _add_eval_rows(by_key)
        _add_benchmark_rows(by_key)
    rows = [enrich_row(r) for r in sorted(by_key.values(), key=lambda r: r["slug"])]
    if payloads is None:
        _UNION_CACHE = rows
        _UNION_CACHE_AT = now
    return rows


def get_model_rollup(slug: str) -> dict | None:
    """Full cross-pillar rollup for one model, resolved by slug."""
    by_slug = {row["slug"]: row for row in get_models_union()}
    return by_slug.get(slug)
