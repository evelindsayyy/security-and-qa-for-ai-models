"""
Tests for frontend/safety_data.py summarize + detail contracts.

  uv run python -m unittest unit_tests.test_safety_data -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frontend import safety_data


class SafetyDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out = Path(self._tmp.name)
        patcher = mock.patch.object(safety_data, "OUTPUT_DIR", self.out)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write_merged(self, slug: str, payload: dict, profile: str = "base") -> None:
        d = self.out / slug / profile
        d.mkdir(parents=True)
        (d / "merged_safety_result.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_summarize_merged_counts_failures(self) -> None:
        slug = "gpt-5.5"
        self._write_merged(
            slug,
            {
                "gateway_model_id": "gpt-5.5",
                "summary_pass_rate": 0.75,
                "composite_tier": "medium",
                "composite_score": 42,
                "status": "complete",
                "completed_at": "2026-06-10T00:00:00Z",
                "findings": [
                    {"passed": True, "severity": "low"},
                    {"passed": False, "severity": "high"},
                ],
                "runs": [
                    {"probe_suite": "garak_subset_v1", "summary_pass_rate": 0.5},
                ],
            },
        )
        with mock.patch("frontend.safety_db_data.available", return_value=False):
            data = safety_data.get_safety_data()
        self.assertTrue(data["has_safety"])
        row = next(r for r in data["models"] if r["slug"] == slug)
        self.assertEqual(row["slug"], slug)
        self.assertEqual(row["n_failed"], 1)
        self.assertEqual(row["n_passed"], 1)

    def test_findings_sorted_failures_first(self) -> None:
        slug = "gpt-5.5"
        self._write_merged(
            slug,
            {
                "gateway_model_id": "gpt-5.5",
                "summary_pass_rate": 0.5,
                "findings": [
                    {"passed": True, "severity": "low", "probe_id": "a"},
                    {"passed": False, "severity": "critical", "probe_id": "b"},
                ],
                "runs": [],
            },
        )
        detail = safety_data.get_safety_detail(slug, "base")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertFalse(detail["findings"][0]["passed"])
        self.assertEqual(detail["findings"][0]["probe_id"], "b")

    def test_missing_slug_returns_none(self) -> None:
        self.assertIsNone(safety_data.get_safety_detail("nonexistent", "base"))


if __name__ == "__main__":
    unittest.main()
