"""
Tests for the robustness layer (evaluator/robustness.py).

All deterministic and offline. Covers:
  - the `typo` perturbation generator (mechanical, seeded, reproducible), and
  - `robustness_report`, the pure post-processing that pairs original vs
    perturbed result rows and computes score_drop / robustness_ratio /
    pass_rate_drop per metrics.yaml's robustness bucket.

Run from repo root:
  uv run python -m unittest unit_tests.test_robustness -v
"""

from __future__ import annotations

import unittest

from evaluator import robustness as rb


class TypoGeneratorTest(unittest.TestCase):
    Q = "How do I reset my Duke NetID password?"

    def test_deterministic_for_same_seed(self) -> None:
        self.assertEqual(rb.typo(self.Q, seed=1), rb.typo(self.Q, seed=1))

    def test_lowercases_and_drops_terminal_punctuation(self) -> None:
        out = rb.typo(self.Q, seed=1)
        self.assertEqual(out, out.lower())
        self.assertFalse(out.endswith("?"))

    def test_abbreviates_common_words(self) -> None:
        # "password" -> "pwd" (matches the metrics.yaml example)
        self.assertIn("pwd", rb.typo(self.Q, seed=1))

    def test_changes_the_text(self) -> None:
        self.assertNotEqual(rb.typo(self.Q, seed=1), self.Q)

    def test_empty_is_safe(self) -> None:
        self.assertEqual(rb.typo("", seed=1), "")
        self.assertEqual(rb.typo(None, seed=1), "")


class RobustnessReportTest(unittest.TestCase):
    # base q1: original 4.5, typo 3.5, informal 4.0
    # base q2: original 5.0, typo 3.0, informal 5.0
    ID_META = {
        "q1-o": {"base_id": "q1", "perturbation": "original"},
        "q1-t": {"base_id": "q1", "perturbation": "typo"},
        "q1-i": {"base_id": "q1", "perturbation": "informal"},
        "q2-o": {"base_id": "q2", "perturbation": "original"},
        "q2-t": {"base_id": "q2", "perturbation": "typo"},
        "q2-i": {"base_id": "q2", "perturbation": "informal"},
    }
    ROWS = [
        {"question_id": "q1-o", "overall": 4.5},
        {"question_id": "q1-t", "overall": 3.5},
        {"question_id": "q1-i", "overall": 4.0},
        {"question_id": "q2-o", "overall": 5.0},
        {"question_id": "q2-t", "overall": 3.0},
        {"question_id": "q2-i", "overall": 5.0},
    ]

    def _report(self):
        return rb.robustness_report(self.ROWS, self.ID_META)

    def test_typo_score_drop_and_ratio(self) -> None:
        typo = self._report()["by_perturbation"]["typo"]
        self.assertEqual(typo["n"], 2)
        self.assertAlmostEqual(typo["mean_original"], 4.75)
        self.assertAlmostEqual(typo["mean_perturbed"], 3.25)
        self.assertAlmostEqual(typo["score_drop"], -1.5)
        self.assertAlmostEqual(typo["robustness_ratio"], 3.25 / 4.75)

    def test_typo_pass_rate_drop(self) -> None:
        # both originals passed (>=4) and both typo variants failed (<4) -> 1.0
        self.assertAlmostEqual(self._report()["by_perturbation"]["typo"]["pass_rate_drop"], 1.0)

    def test_informal_barely_drops(self) -> None:
        inf = self._report()["by_perturbation"]["informal"]
        self.assertAlmostEqual(inf["score_drop"], -0.25)
        self.assertAlmostEqual(inf["pass_rate_drop"], 0.0)  # both stay >=4

    def test_overall_aggregates_all_perturbations(self) -> None:
        ov = self._report()["overall"]
        # 4 pairs total (2 typo + 2 informal)
        self.assertEqual(ov["n"], 4)
        self.assertLess(ov["score_drop"], 0)

    def test_missing_pairs_are_skipped(self) -> None:
        # a perturbed row with no matching original contributes nothing
        rows = [{"question_id": "q1-t", "overall": 3.0}]  # no q1-o
        rep = rb.robustness_report(rows, self.ID_META)
        self.assertEqual(rep["by_perturbation"].get("typo", {}).get("n", 0), 0)

    def test_none_overall_ignored(self) -> None:
        rows = self.ROWS + [{"question_id": "q1-o", "overall": None}]
        # still computes (None row ignored, real q1-o already present)
        rep = rb.robustness_report(rows, self.ID_META)
        self.assertEqual(rep["by_perturbation"]["typo"]["n"], 2)


class RealRobustnessSuiteTest(unittest.TestCase):
    def test_suite_loads_with_all_perturbations(self) -> None:
        meta = rb.suite_id_meta("robustness_v1")
        self.assertEqual(len(meta), 20)  # 5 bases x 4 phrasings
        bases = {m["base_id"] for m in meta.values()}
        self.assertEqual(len(bases), 5)
        # every base has original + all three perturbation types
        by_base = {b: set() for b in bases}
        for m in meta.values():
            by_base[m["base_id"]].add(m["perturbation"])
        for b, kinds in by_base.items():
            self.assertEqual(kinds, {"original", "typo", "informal", "ambiguous"}, b)


if __name__ == "__main__":
    unittest.main()
