"""
Validates the Week-7 judge rubrics (email_drafting_v1, plain_language_v1) are
well-formed and pipeline-valid: they resolve through the REAL judge.resolve_rubric
(mixing shared-library dims with inline task-specific dims) and aggregate through
the REAL runner._weighted_overall. Also sanity-checks the two suites' shape.
Offline; no model calls.

Run from repo root:
  uv run python -m unittest unit_tests.test_w7_judge_rubrics -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_EVALUATOR = Path(__file__).resolve().parent.parent / "evaluator"
sys.path.insert(0, str(_EVALUATOR))

import judge  # noqa: E402
import runner  # noqa: E402
from schemas import DimensionScore  # noqa: E402

RUBRICS = _EVALUATOR / "tasks" / "rubrics"
TASKS = _EVALUATOR / "tasks"


class W7JudgeRubricsTest(unittest.TestCase):
    def _resolve(self, name: str) -> dict:
        return judge.resolve_rubric(RUBRICS / f"{name}.yaml")[0]

    def test_email_resolves_with_expected_dims(self) -> None:
        r = self._resolve("email_drafting_v1")
        self.assertEqual(r["rubric_version"], "email_drafting_v1")
        dims = r["dimensions"]
        for d in ("completeness", "clarity", "tone", "structure"):
            self.assertIn(d, dims)
        # the shared dim got its anchors inlined from _shared_dimensions.yaml
        self.assertIn("anchors", dims["completeness"])
        self.assertAlmostEqual(sum(d["weight"] for d in dims.values()), 1.0)

    def test_plain_resolves_with_expected_dims(self) -> None:
        r = self._resolve("plain_language_v1")
        self.assertEqual(r["rubric_version"], "plain_language_v1")
        dims = r["dimensions"]
        for d in ("faithfulness", "simplicity", "completeness", "tone"):
            self.assertIn(d, dims)
        self.assertIn("anchors", dims["faithfulness"])  # shared inlined
        self.assertAlmostEqual(sum(d["weight"] for d in dims.values()), 1.0)

    def test_email_aggregates_to_display_scale(self) -> None:
        r = self._resolve("email_drafting_v1")
        scores = {
            "completeness": DimensionScore(5, "x"), "clarity": DimensionScore(5, "x"),
            "tone": DimensionScore(3, "x"), "structure": DimensionScore(3, "x"),
        }
        self.assertAlmostEqual(runner._weighted_overall(scores, r), 5.0)

    def test_plain_aggregates_to_display_scale(self) -> None:
        r = self._resolve("plain_language_v1")
        scores = {
            "faithfulness": DimensionScore(5, "x"), "simplicity": DimensionScore(5, "x"),
            "completeness": DimensionScore(5, "x"), "tone": DimensionScore(3, "x"),
        }
        self.assertAlmostEqual(runner._weighted_overall(scores, r), 5.0)

    def test_tutoring_resolves_with_expected_dims(self) -> None:
        r = self._resolve("tutoring_v1")
        self.assertEqual(r["rubric_version"], "tutoring_v1")
        dims = r["dimensions"]
        for d in ("correctness", "pedagogy", "completeness", "tone"):
            self.assertIn(d, dims)
        self.assertIn("anchors", dims["tone"])  # shared dim inlined
        # pedagogy carries the most weight (teaching, not answer-dumping)
        self.assertEqual(max(dims, key=lambda k: dims[k]["weight"]), "pedagogy")
        self.assertAlmostEqual(sum(d["weight"] for d in dims.values()), 1.0)

    def test_tutoring_aggregates_to_display_scale(self) -> None:
        r = self._resolve("tutoring_v1")
        scores = {
            "correctness": DimensionScore(5, "x"), "pedagogy": DimensionScore(5, "x"),
            "completeness": DimensionScore(5, "x"), "tone": DimensionScore(3, "x"),
        }
        self.assertAlmostEqual(runner._weighted_overall(scores, r), 5.0)

    def test_missing_dimension_yields_none(self) -> None:
        r = self._resolve("email_drafting_v1")
        partial = {"completeness": DimensionScore(4, "x")}
        self.assertIsNone(runner._weighted_overall(partial, r))

    def test_suites_have_question_and_reference(self) -> None:
        for name in ("email_drafting_v1", "plain_language_v1", "tutoring_v1"):
            rows = [json.loads(line) for line in
                    (TASKS / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
                    if line.strip()]
            tasks = [r for r in rows if "id" in r]
            self.assertEqual(len(tasks), 5)
            for t in tasks:
                self.assertIn("question", t)
                self.assertTrue(t.get("reference"), f"{name}:{t['id']} missing reference")


if __name__ == "__main__":
    unittest.main()
