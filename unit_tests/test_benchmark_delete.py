"""
Tests for benchmark result deletion from the frontend.

  uv run python -m unittest unit_tests.test_benchmark_delete -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from frontend.benchmark_data import _artifact_paths, delete_benchmark  # noqa: E402


class DeleteBenchmarkTest(unittest.TestCase):
    def test_rejects_unsafe_slug(self) -> None:
        self.assertIsNotNone(delete_benchmark("../etc/passwd"))

    def test_deletes_all_artifact_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            slug = "20260101T120000Z_mmlu_test-model"
            for suffix in (".json", ".stats.json", ".log"):
                (results / f"{slug}{suffix}").write_text("{}", encoding="utf-8")
            with mock.patch("frontend.benchmark_data.PRIMARY_DIR", results), mock.patch(
                "frontend.benchmark_data._candidate_dirs", return_value=[results]
            ), mock.patch("frontend.benchmark_launch.is_run_in_progress", return_value=False), mock.patch(
                "frontend.benchmark_db_data.available", return_value=False
            ):
                self.assertIsNone(delete_benchmark(slug))
                self.assertEqual(_artifact_paths(slug), [])

    def test_blocks_delete_while_running(self) -> None:
        with mock.patch("frontend.benchmark_launch.is_run_in_progress", return_value=True):
            err = delete_benchmark("20260101T120000Z_mmlu_test")
        self.assertIn("in progress", err or "")

    def test_not_found_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            with mock.patch("frontend.benchmark_data._candidate_dirs", return_value=[results]), mock.patch(
                "frontend.benchmark_launch.is_run_in_progress", return_value=False
            ), mock.patch("frontend.benchmark_db_data.available", return_value=False):
                self.assertIsNotNone(delete_benchmark("20260101T120000Z_mmlu_missing"))


if __name__ == "__main__":
    unittest.main()
