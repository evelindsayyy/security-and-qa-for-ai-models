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

from frontend import benchmark_data, eval_run_data, safety_data, scan_data
from frontend.model_identity import gateway_slug, hf_repo_id


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


def _add_scan_rows(by_key: dict[str, dict]) -> None:
    for s in scan_data.get_scans_data().get("scans", []):
        key = s["slug"]
        row = _row(by_key, key, s.get("model_id") or hf_repo_id(key))
        row["scan"] = {
            "slug": s["slug"],
            "tier": s["severity_tier"],
            "overall_risk_score": s["overall_risk_score"],
        }


def _add_safety_rows(by_key: dict[str, dict]) -> None:
    for m in safety_data.get_safety_data().get("models", []):
        key = gateway_slug(m["gateway_model_id"])
        row = _row(by_key, key, m.get("display_name") or m["gateway_model_id"])
        row["safety"] = {
            "slug": m["slug"],
            "profile": m["profile"],
            "tier": m["tier"],
            "pass_rate": m["summary_pass_rate"],
        }


def _add_eval_rows(by_key: dict[str, dict]) -> None:
    runs_by_key: dict[str, list[dict]] = {}
    for r in eval_run_data.get_runs_data().get("runs", []):
        runs_by_key.setdefault(gateway_slug(r["candidate_model"]), []).append(r)

    for key, runs in runs_by_key.items():
        row = _row(by_key, key, runs[0]["candidate_model"])
        overalls = [r["overall"] for r in runs if r.get("overall") is not None]
        latencies = [r["mean_latency_ms"] for r in runs if r.get("mean_latency_ms") is not None]
        row["eval"] = {
            "n_runs": len(runs),
            "suites": sorted({r["suite"] for r in runs}),
            "best_overall": max(overalls) if overalls else None,
            "mean_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
            "total_cost_usd": sum(r.get("total_cost_usd") or 0 for r in runs),
        }


def _add_benchmark_rows(by_key: dict[str, dict]) -> None:
    # get_benchmarks_data()["runs"] already normalizes away a provider/ prefix
    # on "model" (frontend/benchmark_data.py::_normalize_model_name).
    kinds_by_key: dict[str, dict[str, dict]] = {}
    for r in benchmark_data.get_benchmarks_data().get("runs", []):
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


def get_models_union() -> list[dict]:
    """One row per model with data in at least one pillar."""
    by_key: dict[str, dict] = {}
    _add_scan_rows(by_key)
    _add_safety_rows(by_key)
    _add_eval_rows(by_key)
    _add_benchmark_rows(by_key)
    return sorted(by_key.values(), key=lambda r: r["slug"])


def get_model_rollup(slug: str) -> dict | None:
    """Full cross-pillar rollup for one model, resolved by slug against
    whichever pillar's identity space it belongs to."""
    for row in get_models_union():
        if row["slug"] == slug:
            return row
    return None
