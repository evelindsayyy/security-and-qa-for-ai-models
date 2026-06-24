import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

try:  # benchmarks deps (pandas/litellm) aren't always installed in every env
    import pandas as pd
    from tqa_test import TruthfulQATestRunner

    _HAS_TQA = True
except Exception:  # noqa: BLE001
    _HAS_TQA = False


@unittest.skipUnless(_HAS_TQA, "benchmarks deps (pandas) not installed")
class TestTqaCoverage(unittest.TestCase):
    def _evaluate(self, rows):
        df = pd.DataFrame(rows)
        # evaluate_answers doesn't touch self, so we avoid loading the CSV.
        return TruthfulQATestRunner.evaluate_answers(None, df, "model")

    def test_full_coverage(self) -> None:
        m = self._evaluate(
            {"model": ["A", "B"], "correct_letter": ["A", "C"]}
        )
        self.assertEqual(m["attempted"], 2)
        self.assertEqual(m["scored"], 2)
        self.assertEqual(m["failed"], 0)
        self.assertEqual(m["correct"], 1)
        self.assertEqual(m["coverage"], 1.0)
        self.assertAlmostEqual(m["accuracy"], 0.5)

    def test_partial_coverage_counts_unanswered(self) -> None:
        # Third question was attempted (has a correct_letter) but got no answer.
        m = self._evaluate(
            {"model": ["A", "B", ""], "correct_letter": ["A", "C", "A"]}
        )
        self.assertEqual(m["attempted"], 3)
        self.assertEqual(m["scored"], 2)
        self.assertEqual(m["failed"], 1)
        self.assertAlmostEqual(m["coverage"], round(2 / 3, 4))
        # Accuracy is over scored questions only, not attempted.
        self.assertAlmostEqual(m["accuracy"], 0.5)

    def test_untested_rows_excluded(self) -> None:
        # NaN correct_letter = never tested; must not inflate the denominator.
        m = self._evaluate(
            {"model": ["A", "C"], "correct_letter": ["A", float("nan")]}
        )
        self.assertEqual(m["attempted"], 1)
        self.assertEqual(m["scored"], 1)
        self.assertEqual(m["correct"], 1)


if __name__ == "__main__":
    unittest.main()
