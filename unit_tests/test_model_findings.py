"""Tests for model detail pillar findings helper."""

from __future__ import annotations

import unittest
from unittest import mock

from frontend.model_findings import get_model_findings


class TestModelFindings(unittest.TestCase):
    def test_empty_rollup_returns_empty_lists(self):
        out = get_model_findings({})
        self.assertEqual(out, {"scan": [], "safety": [], "benchmark": []})

    def test_scan_findings_slice_top_three(self):
        rollup = {"scan": {"slug": "meta-llama"}}
        fake_detail = {
            "findings": [
                {"title": f"Finding {i}", "severity": "high", "source": "modelscan"}
                for i in range(5)
            ]
        }
        with mock.patch("frontend.scan_data.get_scan_detail", return_value=fake_detail):
            out = get_model_findings(rollup)
        self.assertEqual(len(out["scan"]), 3)
        self.assertEqual(out["scan"][0]["title"], "Finding 0")
        self.assertEqual(out["scan"][0]["detail_url"], "/scans/meta-llama")

    def test_safety_prefers_failed_probes(self):
        rollup = {"safety": {"slug": "gpt-4.1", "profile": "base"}}
        fake_detail = {
            "findings": [
                {"title": "ok", "severity": "low", "passed": True},
                {"title": "bad", "severity": "high", "passed": False},
            ]
        }
        with mock.patch("frontend.safety_data.get_safety_detail", return_value=fake_detail):
            out = get_model_findings(rollup)
        self.assertEqual(out["safety"][0]["title"], "bad")
        self.assertEqual(out["safety"][0]["label"], "fail")


if __name__ == "__main__":
    unittest.main()
