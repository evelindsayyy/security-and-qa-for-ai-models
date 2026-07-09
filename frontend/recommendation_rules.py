"""
Use-case recommendation — rules v1.

Turns one ``frontend.model_rollup.get_model_rollup()`` payload into a
plain-language summary plus explicit tradeoffs, for the model detail page
and the compare route. Evidence-backed only — every claim traces back to a
field already surfaced elsewhere on the label (scan tier, safety tier/pass
rate, eval scores/latency/cost, benchmark headline metrics). This does not
replace OIT sign-off; it is a starting point for an analyst, not a verdict.

Rules v1 (deliberately simple; refine as fall-term suites expand):

- **Security** comes from the safety composite tier (garak + promptfoo +
  Duke policy probes) — the dominant signal for a gateway chat model. Scan
  tier (HF artifact scanning) only applies to models with a Hugging Face
  repo; it is folded in as a second security line when present.
- **Efficacy** comes from the best per-suite overall score across Duke
  judge suites (0-5 scale). Benchmark headline metrics are listed as
  supporting evidence, not blended into one number — a benchmark accuracy
  and a rubric-judged 0-5 score are not on the same scale.
- **Cost/latency** is called out only when eval data exists, since that is
  the only pillar that records it today.
- With no data in any pillar, the recommendation says so plainly rather
  than guessing.
"""

from __future__ import annotations

_SAFETY_TIER_LANGUAGE = {
    "critical": "flagged by automated red-teaming as high risk — do not deploy without a manual safety review",
    "high": "flagged by automated red-teaming as high risk — do not deploy without a manual safety review",
    "medium": "passed most automated safety probes, but some categories failed — suitable with monitoring",
    "low": "passed the large majority of automated safety probes",
}

_EVAL_SCORE_LANGUAGE = (
    (4.5, "very strong performance on Duke task suites"),
    (3.5, "solid performance on Duke task suites"),
    (2.5, "mixed performance on Duke task suites — check per-suite detail"),
    (0.0, "weak performance on Duke task suites"),
)


def _eval_language(best_overall: float) -> str:
    for threshold, text in _EVAL_SCORE_LANGUAGE:
        if best_overall >= threshold:
            return text
    return _EVAL_SCORE_LANGUAGE[-1][1]


def build_recommendation(rollup: dict) -> dict:
    """Rules v1 recommendation for one model_rollup row. See module docstring."""
    scan = rollup.get("scan")
    safety = rollup.get("safety")
    eval_ = rollup.get("eval")
    benchmark = rollup.get("benchmark")

    tradeoffs: list[str] = []
    summary_parts: list[str] = []

    if safety:
        tier = safety.get("tier", "unknown")
        text = _SAFETY_TIER_LANGUAGE.get(tier, f"safety tier: {tier}")
        pass_rate = safety.get("pass_rate")
        pass_rate_text = f" ({pass_rate * 100:.0f}% probe pass rate)" if pass_rate is not None else ""
        tradeoffs.append(f"Security (safety): {text}{pass_rate_text}.")
        summary_parts.append(text)
    if scan:
        tier = scan.get("tier", "unknown")
        tradeoffs.append(
            f"Security (artifact scan): {tier} risk tier, score {scan.get('overall_risk_score', 0)}."
        )

    if eval_ and eval_.get("best_overall") is not None:
        best = eval_["best_overall"]
        text = _eval_language(best)
        suites = ", ".join(eval_.get("suites") or [])
        detail = f"{text} (best overall {best:.1f}/5 across {suites})." if suites else f"{text}."
        tradeoffs.append(f"Efficacy: {detail}")
        summary_parts.append(text)
        if eval_.get("mean_latency_ms") is not None or eval_.get("total_cost_usd") is not None:
            latency = eval_.get("mean_latency_ms")
            cost = eval_.get("total_cost_usd")
            latency_text = f"~{latency:,} ms mean latency" if latency is not None else None
            cost_text = f"~${cost:.4f} total eval cost" if cost is not None else None
            tradeoffs.append(
                "Cost/latency: " + ", ".join(t for t in (latency_text, cost_text) if t) + "."
            )

    if benchmark and benchmark.get("kinds"):
        kind_bits = [
            f"{kind} {info['headline_display']}"
            for kind, info in benchmark["kinds"].items()
            if info.get("headline_display")
        ]
        if kind_bits:
            tradeoffs.append("Benchmarks: " + ", ".join(kind_bits) + ".")

    has_data = bool(scan or safety or eval_ or benchmark)
    if not has_data:
        summary = "Not enough evidence yet — no scan, safety, eval, or benchmark data for this model."
    else:
        summary = " ".join(summary_parts) if summary_parts else "Partial evidence only — see tradeoffs below."

    return {
        "summary": summary,
        "tradeoffs": tradeoffs,
        "has_data": has_data,
    }
