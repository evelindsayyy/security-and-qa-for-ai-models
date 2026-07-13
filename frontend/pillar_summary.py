"""Gateway-backed AI summaries for individual pillar detail pages."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from frontend import model_summary


def _detail_hash(pillar: str, slug: str, detail: dict[str, Any]) -> str:
    payload = json.dumps(
        {"pillar": pillar, "slug": slug, "detail": _evidence_blob(pillar, detail)},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _evidence_blob(pillar: str, detail: dict[str, Any]) -> str:
    if pillar == "scan":
        return (
            f"Model/repo: {detail.get('model_id')}\n"
            f"Tier: {detail.get('severity_tier')}, risk={detail.get('overall_risk_score')}\n"
            f"Findings: {detail.get('n_findings', 0)}\n"
            f"Scanned: {detail.get('scanned_at')}"
        )
    if pillar == "safety":
        return (
            f"Model: {detail.get('gateway_model_id')}, profile={detail.get('profile')}\n"
            f"Tier: {detail.get('tier')}, pass_rate={detail.get('pass_rate_display')}\n"
            f"Probes resisted: {detail.get('n_passed')}/{detail.get('n_findings')}\n"
            f"Completed: {detail.get('completed_at')}"
        )
    if pillar == "eval":
        dims = detail.get("dim_means") or {}
        dim_bits = ", ".join(f"{k}={v:.2f}" for k, v in dims.items() if v is not None)
        return (
            f"Candidate: {detail.get('candidate_model')}, judge={detail.get('judge_model')}\n"
            f"Suite: {detail.get('suite')}, rubric={detail.get('rubric_version')}\n"
            f"Overall: {detail.get('mean_overall')}/5\n"
            f"Dimensions: {dim_bits or '—'}\n"
            f"Cost: ${detail.get('total_cost_usd')}, latency={detail.get('mean_latency_ms')} ms\n"
            f"Status: {detail.get('ok')}/{detail.get('n')} OK"
        )
    if pillar == "benchmark":
        return (
            f"Benchmark: {detail.get('kind_label')} ({detail.get('kind')})\n"
            f"Model: {detail.get('model')}\n"
            f"Score: {detail.get('headline_display')} ({detail.get('headline_metric')})\n"
            f"n={detail.get('n')}, completed={detail.get('timestamp')}"
        )
    return json.dumps(detail, default=str)[:2000]


def _rules_fallback(pillar: str, detail: dict[str, Any]) -> dict:
    if pillar == "scan":
        text = (
            f"Scan tier {detail.get('severity_tier')} with risk score "
            f"{detail.get('overall_risk_score')} and {detail.get('n_findings', 0)} findings."
        )
    elif pillar == "safety":
        text = (
            f"Safety tier {detail.get('tier')} with {detail.get('pass_rate_display')} pass rate "
            f"({detail.get('n_passed')}/{detail.get('n_findings')} probes resisted)."
        )
    elif pillar == "eval":
        overall = detail.get("mean_overall")
        if overall is None:
            overall = detail.get("overall")
        text = (
            f"Eval overall {overall:.2f}/5 on suite {detail.get('suite')} "
            f"({detail.get('candidate_model')} judged by {detail.get('judge_model')})."
            if overall is not None
            else f"Eval run on {detail.get('suite')} — no overall score yet."
        )
    elif pillar == "benchmark":
        text = (
            f"{detail.get('kind_label')} score {detail.get('headline_display')} "
            f"for {detail.get('model')}."
        )
    else:
        text = "Summary unavailable."
    return {"summary": text, "tradeoffs": [], "source": "rules_v1", "has_data": True}


def get_pillar_summary(pillar: str, slug: str, detail: dict[str, Any]) -> dict:
    """Cached AI summary for one pillar run detail page."""
    inputs_hash = _detail_hash(pillar, slug, detail)
    cached = model_summary._read_cache(slug, kind=f"pillar-{pillar}", inputs_hash=inputs_hash)
    if cached:
        return cached

    pillar_label = {"scan": "file scan", "safety": "red-team safety", "eval": "LLM eval", "benchmark": "benchmark"}[
        pillar
    ]
    prompt = (
        f"Pillar: {pillar_label}\n"
        f"Run slug: {slug}\n\n"
        f"Evidence:\n{_evidence_blob(pillar, detail)}\n\n"
        f"Write 2-3 sentences summarizing this {pillar_label} result for a Duke IT analyst. "
        "Note strengths, risks, and gaps plainly. Optional bullet tradeoffs."
    )
    ai_text = model_summary._call_gateway(prompt)
    if not ai_text:
        return _rules_fallback(pillar, detail)

    result = model_summary._parse_ai_response(ai_text)
    model_summary._write_cache(slug, kind=f"pillar-{pillar}", inputs_hash=inputs_hash, payload=result)
    return result


def attach_pillar_summary(detail: dict[str, Any], *, pillar: str) -> None:
    """Mutate detail dict with ``pillar_summary`` for templates."""
    slug = detail.get("slug") or ""
    if not slug:
        return
    detail["pillar_summary"] = get_pillar_summary(pillar, slug, detail)
