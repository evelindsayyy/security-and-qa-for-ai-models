"""
Tests for the cost-vs-performance layer (evaluator/cost_perf.py).

All deterministic and offline — pure arithmetic over already-aggregated
per-model numbers. No model calls, no file IO, no schema dependency.

What the layer must guarantee (HELM honesty):
  - it never collapses to one hidden number — every CostPerfScore carries its
    normalized components AND the weights used, so the tradeoff is inspectable;
  - quality-per-dollar is the headline efficiency metric, and it is undefined
    (None) for $0 backends (self-hosted DCC bills GPU-hours, not per-token);
  - the weighted utility is a *configurable* tradeoff: changing the weights
    can change the ranking (Budget vs Quality-first), by design.

Run from repo root:
  uv run python -m unittest unit_tests.test_cost_perf -v
"""

from __future__ import annotations

import unittest

from evaluator import cost_perf as cp


# A small, deliberately-contrasting cohort reused across tests:
#   - strong-pricey: best quality, slowest, most expensive
#   - cheap-decent:  slightly lower quality, cheapest, fastest
#   - dcc-local:     mid quality, $0 (self-hosted), mid latency
def _cohort() -> list[cp.ModelCost]:
    return [
        cp.ModelCost(
            model="strong-pricey",
            quality_overall=4.8, quality_scale_max=5.0,
            cost_per_response_usd=0.040, latency_ms=4000,
        ),
        cp.ModelCost(
            model="cheap-decent",
            quality_overall=4.2, quality_scale_max=5.0,
            cost_per_response_usd=0.002, latency_ms=900,
        ),
        cp.ModelCost(
            model="dcc-local",
            quality_overall=3.7, quality_scale_max=5.0,
            cost_per_response_usd=0.0, latency_ms=2200,
            inference_backend="dcc",
        ),
    ]


class NormalizeQualityTest(unittest.TestCase):
    def test_scale_max_maps_to_one(self) -> None:
        self.assertAlmostEqual(cp.normalize_quality(5.0, 5.0), 1.0)

    def test_proportional(self) -> None:
        self.assertAlmostEqual(cp.normalize_quality(4.0, 5.0), 0.8)

    def test_clamps_above_and_below(self) -> None:
        self.assertEqual(cp.normalize_quality(6.0, 5.0), 1.0)
        self.assertEqual(cp.normalize_quality(-1.0, 5.0), 0.0)

    def test_bad_scale_max_does_not_crash(self) -> None:
        # A zero/negative scale_max must not raise ZeroDivisionError.
        self.assertEqual(cp.normalize_quality(3.0, 0.0), 0.0)


class QualityPerDollarTest(unittest.TestCase):
    def test_basic_ratio(self) -> None:
        # 4.8 quality points per $0.0024 response = 2000 points/$.
        self.assertAlmostEqual(cp.quality_per_dollar(4.8, 0.0024), 2000.0)

    def test_zero_cost_is_undefined(self) -> None:
        # $0 backends (DCC) -> None, not inf and not a crash.
        self.assertIsNone(cp.quality_per_dollar(3.7, 0.0))

    def test_negative_cost_is_undefined(self) -> None:
        self.assertIsNone(cp.quality_per_dollar(3.7, -0.01))


class ScoreCohortTest(unittest.TestCase):
    def test_returns_one_score_per_model_in_order(self) -> None:
        scores = cp.score_cohort(_cohort(), cp.BALANCED)
        self.assertEqual([s.model for s in scores],
                         ["strong-pricey", "cheap-decent", "dcc-local"])

    def test_components_are_exposed_and_bounded(self) -> None:
        # HELM honesty: every score exposes its normalized parts in [0,1]
        # and the weights it used — never just a single opaque utility.
        for s in cp.score_cohort(_cohort(), cp.BALANCED):
            for v in (s.quality_norm, s.cost_norm, s.latency_norm):
                self.assertGreaterEqual(v, 0.0)
                self.assertLessEqual(v, 1.0)
            self.assertEqual(s.weights, cp.BALANCED)

    def test_cost_norm_cheapest_is_zero_priciest_is_one(self) -> None:
        by = {s.model: s for s in cp.score_cohort(_cohort(), cp.BALANCED)}
        self.assertEqual(by["dcc-local"].cost_norm, 0.0)      # $0 = cheapest
        self.assertEqual(by["strong-pricey"].cost_norm, 1.0)  # $0.04 = priciest

    def test_zero_cost_backend_flagged_and_qpd_none(self) -> None:
        by = {s.model: s for s in cp.score_cohort(_cohort(), cp.BALANCED)}
        dcc = by["dcc-local"]
        self.assertIsNone(dcc.quality_per_dollar)
        self.assertTrue(any("gpu" in n.lower() or "$0" in n for n in dcc.notes))

    def test_gateway_models_have_quality_per_dollar(self) -> None:
        by = {s.model: s for s in cp.score_cohort(_cohort(), cp.BALANCED)}
        self.assertAlmostEqual(by["cheap-decent"].quality_per_dollar,
                               4.2 / 0.002)

    def test_weights_change_the_ranking(self) -> None:
        # Budget weighting (cost dominates) should rank the cheap model top;
        # Quality-first should rank the strongest model top. Same inputs,
        # different transparent weights -> different order. That's the point.
        cohort = _cohort()
        budget_top = max(cp.score_cohort(cohort, cp.BUDGET),
                         key=lambda s: s.utility).model
        quality_top = max(cp.score_cohort(cohort, cp.QUALITY_FIRST),
                          key=lambda s: s.utility).model
        self.assertEqual(budget_top, "cheap-decent")
        self.assertEqual(quality_top, "strong-pricey")

    def test_utility_formula_matches_components(self) -> None:
        # U = wQ*Qn - wC*Cn - wL*Ln, computed from the exposed components.
        w = cp.BALANCED
        for s in cp.score_cohort(_cohort(), w):
            expected = (w.w_quality * s.quality_norm
                        - w.w_cost * s.cost_norm
                        - w.w_latency * s.latency_norm)
            self.assertAlmostEqual(s.utility, expected)

    def test_single_model_cohort_does_not_divide_by_zero(self) -> None:
        # One model -> no spread to normalize against; cost/latency norms
        # collapse to 0 rather than raising, and utility is just wQ*Qn.
        one = [cp.ModelCost(model="solo", quality_overall=4.0,
                            quality_scale_max=5.0,
                            cost_per_response_usd=0.01, latency_ms=1500)]
        (s,) = cp.score_cohort(one, cp.BALANCED)
        self.assertEqual(s.cost_norm, 0.0)
        self.assertEqual(s.latency_norm, 0.0)
        self.assertAlmostEqual(s.utility, cp.BALANCED.w_quality * 0.8)

    def test_empty_cohort_returns_empty(self) -> None:
        self.assertEqual(cp.score_cohort([], cp.BALANCED), [])


class PresetsTest(unittest.TestCase):
    def test_presets_exist_and_are_frozen(self) -> None:
        for w in (cp.BALANCED, cp.BUDGET, cp.QUALITY_FIRST):
            self.assertIsInstance(w, cp.CostPerfWeights)
            with self.assertRaises(Exception):
                w.w_quality = 99.0  # frozen dataclass -> immutable

    def test_preset_registry_lookup(self) -> None:
        self.assertIs(cp.preset("balanced"), cp.BALANCED)
        self.assertIs(cp.preset("budget"), cp.BUDGET)
        self.assertIs(cp.preset("quality_first"), cp.QUALITY_FIRST)

    def test_unknown_preset_raises(self) -> None:
        with self.assertRaises(KeyError):
            cp.preset("nonsense")


if __name__ == "__main__":
    unittest.main()
