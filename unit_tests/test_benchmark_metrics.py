import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from benchmark_metrics import (  # noqa: E402
    compute_coverage,
    coverage_extras,
    coverage_warning,
    has_usable_text,
    slugify_model,
    summarize_binary_accuracy,
)


class TestHasUsableText(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertFalse(has_usable_text(""))
        self.assertFalse(has_usable_text(None))
        self.assertFalse(has_usable_text("   "))

    def test_non_empty(self) -> None:
        self.assertTrue(has_usable_text("A"))


class TestComputeCoverage(unittest.TestCase):
    def test_full(self) -> None:
        cov = compute_coverage(attempted=10, scored=10)
        self.assertEqual(cov["failed"], 0)
        self.assertEqual(cov["coverage"], 1.0)

    def test_partial(self) -> None:
        cov = compute_coverage(attempted=50, scored=38)
        self.assertEqual(cov["failed"], 12)
        self.assertAlmostEqual(cov["coverage"], 0.76)


class TestSummarizeBinaryAccuracy(unittest.TestCase):
    def test_accuracy_over_scored_only(self) -> None:
        s = summarize_binary_accuracy(attempted=50, correct=33, scored=38)
        self.assertAlmostEqual(s["accuracy"], round(33 / 38, 4))
        self.assertEqual(s["attempted"], 50)
        self.assertEqual(s["scored"], 38)
        self.assertEqual(s["failed"], 12)
        self.assertEqual(s["total_evaluated"], 38)


class TestCoverageWarning(unittest.TestCase):
    def test_none_when_complete(self) -> None:
        self.assertIsNone(coverage_warning({"failed": 0}))

    def test_message_when_partial(self) -> None:
        msg = coverage_warning({
            "attempted": 50,
            "scored": 38,
            "failed": 12,
            "coverage": 0.76,
        })
        self.assertIsNotNone(msg)
        self.assertIn("38/50", msg)


class TestSlugifyModel(unittest.TestCase):
    def test_replaces_slash(self) -> None:
        self.assertEqual(slugify_model("Qwen/Qwen3-0.6B"), "Qwen_Qwen3-0.6B")

    def test_replaces_provider_pin_colon(self) -> None:
        # ':' is illegal in Windows filenames — must be sanitized.
        self.assertEqual(
            slugify_model("WeiboAI/VibeThinker-3B:novita"),
            "WeiboAI_VibeThinker-3B_novita",
        )
        self.assertNotIn(":", slugify_model("org/model:novita"))

    def test_blank_falls_back(self) -> None:
        self.assertEqual(slugify_model("   "), "model")


class TestCoverageExtras(unittest.TestCase):
    def test_empty_when_complete(self) -> None:
        self.assertEqual(coverage_extras({"failed": 0, "attempted": 10}), {})

    def test_includes_fields_when_partial(self) -> None:
        self.assertEqual(
            coverage_extras({"attempted": 50, "scored": 38, "failed": 12, "coverage": 0.76}),
            {"attempted": 50, "scored": 38, "failed": 12, "coverage": 0.76},
        )


if __name__ == "__main__":
    unittest.main()
