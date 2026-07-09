"""
cost_perf.py
============

Cost-vs-performance layer v2 for the Efficacy "report card".

A model that scores 4.8/5 but costs $0.04 and takes 4 seconds per response is
not interchangeable with one that scores 4.2/5 at $0.002 and 0.9 seconds. The
dashboard's job (HELM principle) is to make that tradeoff *visible and
configurable*, never to hide it under one "best model" number.

This module is the math for that. It is deliberately pure: stdlib + its own
dataclasses, no `schemas` import, no file IO, no network. Callers
(`aggregate.py`, the frontend comparison table) do the row reading and hand us
already-aggregated per-model numbers. That keeps the formula trivially
testable and reusable on either side.

Two metrics, two purposes:

  - **quality-per-dollar** — `quality_overall / cost_per_response`. The headline
    efficiency number for a single model, in plain units ("quality points per
    dollar"). Undefined (None) for $0 backends: self-hosted DCC bills GPU-hours,
    not per-token, so a per-token ratio would be a lie. We flag that, we don't
    fake it.

  - **weighted utility** — `U = w_Q·Q̂ − w_C·Ĉ − w_L·L̂`, where Q̂/Ĉ/L̂ are
    normalized in [0,1]. Quality is normalized against its rubric scale; cost
    and latency are min-max normalized *within the compared cohort* (so the
    weights are comparable across the three axes). Every `CostPerfScore` carries
    the normalized components AND the weights used, so the ranking is auditable.
    Changing the weights (Budget vs Quality-first) can change the ranking — that
    is the feature, not a bug.

v2 adds the **Pareto frontier** (the quality-vs-cost efficient set — models no
other model beats on both axes) and a **weight-slider UI** (the frontend
recomputes utility live from the normalized components carried on each score).
Still deferred: modeling GPU-hour cost for self-hosted (DCC) backends.

CLI demo (prints a small cohort table):
    uv run python evaluator/cost_perf.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Weights — the transparent, configurable part of the tradeoff
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CostPerfWeights:
    """Relative importance of the three axes in the utility score.

    Frozen so a preset can't be mutated out from under another caller. The
    weights are shown on the dashboard next to the utility column — that is
    what keeps the score honest (no hidden weighting).
    """
    w_quality: float = 1.0
    w_cost: float = 1.0
    w_latency: float = 0.5


# Three presets covering the obvious stakeholder stances. The slider UI in a
# later week will let a user dial in arbitrary weights; these are the anchors.
BALANCED = CostPerfWeights(w_quality=1.0, w_cost=1.0, w_latency=0.5)
BUDGET = CostPerfWeights(w_quality=0.5, w_cost=2.0, w_latency=1.0)
QUALITY_FIRST = CostPerfWeights(w_quality=2.0, w_cost=0.1, w_latency=0.05)

_PRESETS: dict[str, CostPerfWeights] = {
    "balanced": BALANCED,
    "budget": BUDGET,
    "quality_first": QUALITY_FIRST,
}


def preset(name: str) -> CostPerfWeights:
    """Look up a preset by name. Raises KeyError on an unknown name so the
    caller fails loudly rather than silently scoring with a wrong weighting."""
    return _PRESETS[name]


# ---------------------------------------------------------------------------
# Inputs and outputs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelCost:
    """One model's already-aggregated numbers for a single run/suite.

    `quality_overall` is the rubric-scale mean (e.g. 4.8 on a 1-5 scale);
    `quality_scale_max` is that scale's max (5.0) so we can normalize. Cost is
    per single response in USD; `latency_ms` is a representative latency (mean
    or p50 — the caller decides which statistic). The caller computes these
    from the result rows.
    """
    model: str
    quality_overall: float
    quality_scale_max: float
    cost_per_response_usd: float
    latency_ms: float
    inference_backend: str = "gateway"


@dataclass(frozen=True)
class CostPerfScore:
    """One model's cost-vs-performance result, with every component exposed.

    The point of carrying the normalized parts AND the weights is auditability:
    a reader can reconstruct `utility` by hand and see exactly why a model
    ranked where it did.
    """
    model: str
    quality_norm: float                  # Q̂ in [0,1] (vs rubric scale)
    cost_norm: float                     # Ĉ in [0,1] (0 = cheapest in cohort)
    latency_norm: float                  # L̂ in [0,1] (0 = fastest in cohort)
    utility: float                       # wQ·Q̂ − wC·Ĉ − wL·L̂
    quality_per_dollar: Optional[float]  # None for $0 backends
    cost_per_response_usd: float
    latency_ms: float
    weights: CostPerfWeights
    on_frontier: bool = True             # on the quality-vs-cost Pareto frontier
    notes: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Pure metrics
# ---------------------------------------------------------------------------

def normalize_quality(overall: float, scale_max: float) -> float:
    """Map a rubric-scale score to [0,1] by dividing by the scale max, clamped.

    A bad scale_max (<= 0) returns 0.0 rather than raising — the caller should
    never pass one, but a metric helper crashing the dashboard is worse than a
    degenerate 0.
    """
    if scale_max <= 0:
        return 0.0
    return _clamp(overall / scale_max, 0.0, 1.0)


def quality_per_dollar(overall: float, cost_per_response_usd: float) -> Optional[float]:
    """Quality points bought per dollar, or None when cost is not positive.

    $0 / negative cost -> None: a self-hosted DCC model bills GPU-hours, not
    per-token, so dividing by zero would invent an infinitely-efficient model.
    """
    if cost_per_response_usd <= 0:
        return None
    return overall / cost_per_response_usd


def pareto_frontier(models: list[ModelCost]) -> set[str]:
    """Model names on the quality-vs-cost **efficient frontier**: those NOT
    dominated by any other model in the cohort.

    A dominates B when A is at least as good on BOTH axes (quality >=, cost <=)
    and strictly better on at least one — i.e. B is strictly worse on one axis and
    no better on the other. Higher quality and lower cost are better; models tied
    on both axes both stay on the frontier. This is the 2-D tradeoff the dashboard
    plots; latency is reported alongside but not part of the frontier definition.
    """
    frontier: set[str] = set()
    for m in models:
        dominated = any(
            n is not m
            and n.quality_overall >= m.quality_overall
            and n.cost_per_response_usd <= m.cost_per_response_usd
            and (n.quality_overall > m.quality_overall
                 or n.cost_per_response_usd < m.cost_per_response_usd)
            for n in models
        )
        if not dominated:
            frontier.add(m.model)
    return frontier


def score_cohort(
    models: list[ModelCost],
    weights: CostPerfWeights,
) -> list[CostPerfScore]:
    """Score a cohort of models against each other under one set of weights.

    Cost and latency are min-max normalized within the cohort, so utility is a
    *relative* ranking among the models being compared (documented limitation:
    a model's utility only means something next to the others in the same call).
    Quality is normalized against its own rubric scale, which is absolute.

    Returns scores in the same order as `models`. An empty cohort returns [].
    """
    if not models:
        return []

    costs = [m.cost_per_response_usd for m in models]
    latencies = [m.latency_ms for m in models]
    cost_lo, cost_hi = min(costs), max(costs)
    lat_lo, lat_hi = min(latencies), max(latencies)
    frontier = pareto_frontier(models)

    scores: list[CostPerfScore] = []
    for m in models:
        q_norm = normalize_quality(m.quality_overall, m.quality_scale_max)
        c_norm = _min_max(m.cost_per_response_usd, cost_lo, cost_hi)
        l_norm = _min_max(m.latency_ms, lat_lo, lat_hi)

        utility = (
            weights.w_quality * q_norm
            - weights.w_cost * c_norm
            - weights.w_latency * l_norm
        )

        qpd = quality_per_dollar(m.quality_overall, m.cost_per_response_usd)
        notes: tuple[str, ...] = ()
        if m.cost_per_response_usd <= 0:
            notes = (
                f"$0 at the gateway ({m.inference_backend}): self-hosted "
                "GPU-hour cost is not modeled in v1, so quality-per-$ is N/A.",
            )

        scores.append(CostPerfScore(
            model=m.model,
            quality_norm=q_norm,
            cost_norm=c_norm,
            latency_norm=l_norm,
            utility=utility,
            quality_per_dollar=qpd,
            cost_per_response_usd=m.cost_per_response_usd,
            latency_ms=m.latency_ms,
            weights=weights,
            on_frontier=m.model in frontier,
            notes=notes,
        ))
    return scores


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _min_max(x: float, lo: float, hi: float) -> float:
    """Min-max normalize to [0,1]. No spread (hi == lo) -> 0.0, so a single-model
    or all-equal cohort doesn't divide by zero and contributes no cost/latency
    penalty."""
    if hi == lo:
        return 0.0
    return (x - lo) / (hi - lo)


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    demo = [
        ModelCost("gpt-5-chat", 4.79, 5.0, 0.0180, 3600),
        ModelCost("gpt-4.1-mini", 4.26, 5.0, 0.0021, 1400),
        ModelCost("llama-4-scout", 3.85, 5.0, 0.0009, 1100),
        ModelCost("qwen2.5-7b (dcc)", 3.69, 5.0, 0.0, 2200, inference_backend="dcc"),
    ]
    for label, w in (("BALANCED", BALANCED), ("BUDGET", BUDGET),
                     ("QUALITY_FIRST", QUALITY_FIRST)):
        print(f"\n=== {label}  "
              f"(wQ={w.w_quality}, wC={w.w_cost}, wL={w.w_latency}) ===")
        ranked = sorted(score_cohort(demo, w), key=lambda s: s.utility, reverse=True)
        for s in ranked:
            qpd = "   N/A" if s.quality_per_dollar is None else f"{s.quality_per_dollar:6.0f}"
            print(f"  {s.model:20s}  U={s.utility:+.3f}  "
                  f"Q̂={s.quality_norm:.2f} Ĉ={s.cost_norm:.2f} L̂={s.latency_norm:.2f}  "
                  f"q/$={qpd}")
