"""
Validates the SQL judge rubric (evaluator/tasks/rubrics/sql_duke_v1.yaml) is
well-formed and pipeline-valid — it resolves through the REAL resolve_rubric()
and the REAL _weighted_overall() aggregation. Offline; no model calls.

This is the durable half of the judge-vs-execution deliverable: the rubric that
lets the SQL suite be graded by the actual judge pipeline (the live reproduction
run is separate). See sql_duke_v1.yaml's header for the why.

Run from repo root:
  uv run python -m unittest unit_tests.test_sql_judge_rubric -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_EVALUATOR = Path(__file__).resolve().parent.parent / "evaluator"
sys.path.insert(0, str(_EVALUATOR))

import judge  # noqa: E402
import runner  # noqa: E402
from schemas import DimensionScore  # noqa: E402

RUBRIC_PATH = _EVALUATOR / "tasks" / "rubrics" / "sql_duke_v1.yaml"


class SqlJudgeRubricTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rubric, _raw = judge.resolve_rubric(RUBRIC_PATH)

    def test_resolves_with_expected_identity(self) -> None:
        self.assertEqual(self.rubric["rubric_version"], "sql_duke_v1")
        self.assertEqual(self.rubric["task_type"], "text_to_sql")

    def test_has_correctness_and_clarity_dimensions(self) -> None:
        dims = self.rubric["dimensions"]
        self.assertIn("correctness", dims)
        self.assertIn("query_clarity", dims)

    def test_weights_sum_to_one(self) -> None:
        dims = self.rubric["dimensions"]
        total = sum(d["weight"] for d in dims.values())
        self.assertAlmostEqual(total, 1.0)

    def test_correctness_dominates(self) -> None:
        dims = self.rubric["dimensions"]
        self.assertGreater(dims["correctness"]["weight"],
                           dims["query_clarity"]["weight"])

    def test_aggregation_computes_a_display_score(self) -> None:
        # Feed sample per-dimension scores through the real runner aggregation
        # and confirm it yields a number on the 0-5 display scale.
        scores = {
            "correctness": DimensionScore(score=5, rationale="traces to expected"),
            "query_clarity": DimensionScore(score=3, rationale="clean"),
        }
        overall = runner._weighted_overall(scores, self.rubric)
        # 0.80*(5/5) + 0.20*(3/3) = 1.0 -> 5.0 on the display scale
        self.assertAlmostEqual(overall, 5.0)

    def test_missing_dimension_yields_none(self) -> None:
        # If the judge fails to score a dimension, the overall is None (the
        # runner contract: incomplete scores don't get a fabricated overall).
        partial = {"correctness": DimensionScore(score=4, rationale="ok")}
        self.assertIsNone(runner._weighted_overall(partial, self.rubric))


if __name__ == "__main__":
    unittest.main()
