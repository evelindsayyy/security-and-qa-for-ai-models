"""
Tests for benchmarks/run_benchmark.py slug + stem helpers.

  uv run python -m unittest unit_tests.test_run_benchmark -v
"""

from __future__ import annotations

import re
import unittest

from benchmarks import run_benchmark as rb


class SafeSlugTest(unittest.TestCase):
    def test_sanitizes_spaces_and_special_chars(self) -> None:
        self.assertEqual(rb._safe_slug("GPT 4.1 Mini"), "GPT-4.1-Mini")

    def test_empty_falls_back(self) -> None:
        self.assertEqual(rb._safe_slug("   "), "model")


class PredictStemTest(unittest.TestCase):
    def test_stem_format(self) -> None:
        stem = rb.predict_stem("truthfulqa", "GPT 4.1 Mini")
        self.assertRegex(stem, r"^\d{8}T\d{6}Z_truthfulqa_GPT-4.1-Mini$")
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9._-]+", stem))


class BenchmarkKeysTest(unittest.TestCase):
    def test_unknown_benchmark_raises_on_run(self) -> None:
        with self.assertRaises(SystemExit):
            rb.run("not-a-real-benchmark", "gpt-5-chat")


if __name__ == "__main__":
    unittest.main()
