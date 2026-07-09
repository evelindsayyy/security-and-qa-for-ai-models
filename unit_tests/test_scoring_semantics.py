"""
Golden-value guards for the SEMANTICS of the frozen contract's interpreter code.

The freeze (evaluator/frozen_contract.yaml) pins the DATA — suites, rubrics,
prompts, schema — but NOT the code that reads them (runner._weighted_overall, the
execution checkers, robustness._metrics). A change to that code retroactively
reinterprets every historically frozen result row, which is exactly the
"comparability across runs" risk the freeze exists to prevent.

These tests pin the *behavior* of that code against hand-computed values. You can
refactor freely; but any change that alters a score trips a test here — a signal
that historical results are no longer comparable, so bump a version rather than
silently editing. (Complements the data-hash freeze in test_contract_freeze.py.)

Run from repo root:
  uv run python -m unittest unit_tests.test_scoring_semantics -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_EVALUATOR = Path(__file__).resolve().parent.parent / "evaluator"
sys.path.insert(0, str(_EVALUATOR))

from robustness import _metrics  # noqa: E402
from runner import _weighted_overall  # noqa: E402
from schemas import DimensionScore  # noqa: E402


def _rubric(dims: dict, display_scale: int = 5) -> dict:
    return {"dimensions": dims, "aggregation": {"display_scale": display_scale}}


class WeightedOverallGoldenTest(unittest.TestCase):
    """Pins: overall = round( Σ weightᵢ·(scoreᵢ/maxᵢ) · display_scale, 2 )."""

    def test_mixed_scores_golden(self) -> None:
        rubric = _rubric({
            "a": {"weight": 0.6, "scale": [1, 5]},   # 0.6 * 3/5 = 0.36
            "b": {"weight": 0.4, "scale": [1, 3]},   # 0.4 * 2/3 = 0.26667
        })
        scores = {"a": DimensionScore(3, "x"), "b": DimensionScore(2, "x")}
        # (0.36 + 0.26667) * 5 = 3.1333 -> round 3.13
        self.assertEqual(_weighted_overall(scores, rubric), 3.13)

    def test_all_max_equals_display_scale(self) -> None:
        rubric = _rubric({
            "a": {"weight": 0.7, "scale": [1, 5]},
            "b": {"weight": 0.3, "scale": [1, 3]},
        })
        scores = {"a": DimensionScore(5, "x"), "b": DimensionScore(3, "x")}
        self.assertEqual(_weighted_overall(scores, rubric), 5.0)

    def test_missing_dimension_returns_none(self) -> None:
        rubric = _rubric({"a": {"weight": 1.0, "scale": [1, 5]}})
        self.assertIsNone(_weighted_overall({}, rubric))


class RobustnessMetricsGoldenTest(unittest.TestCase):
    def test_pass_rate_drop_denominator_is_all_pairs(self) -> None:
        # 3 pairs; one original already fails (3.0 < 4.0 threshold). There is one
        # pass->fail transition, taken over ALL 3 pairs -> 1/3, NOT 1/2. This pins
        # the (deliberate) denominator choice flagged in review as ambiguous.
        pairs = [(5.0, 3.0), (3.0, 2.0), (4.5, 5.0)]
        m = _metrics(pairs)
        self.assertEqual(m["n"], 3)
        self.assertAlmostEqual(m["pass_rate_drop"], 1 / 3)
        self.assertAlmostEqual(m["mean_original"], 12.5 / 3)
        self.assertAlmostEqual(m["mean_perturbed"], 10 / 3)
        self.assertAlmostEqual(m["score_drop"], (10 - 12.5) / 3)

    def test_empty_pairs(self) -> None:
        self.assertEqual(_metrics([]), {"n": 0})


if __name__ == "__main__":
    unittest.main()
