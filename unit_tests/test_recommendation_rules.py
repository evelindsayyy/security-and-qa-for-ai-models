"""
Tests for frontend/recommendation_rules.py — pure function, synthetic
rollup dicts in, expected tradeoffs out. No mocks, no Flask.

  uv run python -m unittest unit_tests.test_recommendation_rules -v
"""

from __future__ import annotations

import unittest

from frontend.recommendation_rules import build_recommendation


class BuildRecommendationTest(unittest.TestCase):
    def test_no_data_is_explicit_about_it(self) -> None:
        rec = build_recommendation({"scan": None, "safety": None, "eval": None, "benchmark": None})
        self.assertFalse(rec["has_data"])
        self.assertIn("Not enough evidence", rec["summary"])
        self.assertEqual(rec["tradeoffs"], [])

    def test_critical_safety_tier_flags_review(self) -> None:
        rec = build_recommendation({
            "scan": None,
            "safety": {"tier": "critical", "pass_rate": 0.3},
            "eval": None,
            "benchmark": None,
        })
        self.assertTrue(rec["has_data"])
        self.assertTrue(any("manual safety review" in t for t in rec["tradeoffs"]))
        self.assertIn("30%", " ".join(rec["tradeoffs"]))

    def test_strong_eval_score_reflected_in_summary(self) -> None:
        rec = build_recommendation({
            "scan": None,
            "safety": {"tier": "low", "pass_rate": 0.95},
            "eval": {"best_overall": 4.8, "suites": ["it_support_v1"],
                     "mean_latency_ms": 900, "total_cost_usd": 0.02},
            "benchmark": None,
        })
        self.assertIn("very strong", rec["summary"])
        self.assertTrue(any("Cost/latency" in t for t in rec["tradeoffs"]))
        self.assertTrue(any("900" in t for t in rec["tradeoffs"]))

    def test_benchmark_kinds_listed(self) -> None:
        rec = build_recommendation({
            "scan": None, "safety": None, "eval": None,
            "benchmark": {"kinds": {"mmlu": {"headline_display": "71.0%"}}},
        })
        self.assertTrue(any("mmlu 71.0%" in t for t in rec["tradeoffs"]))

    def test_scan_tier_included_when_present(self) -> None:
        rec = build_recommendation({
            "scan": {"tier": "high", "overall_risk_score": 80},
            "safety": None, "eval": None, "benchmark": None,
        })
        self.assertTrue(any("artifact scan" in t and "high" in t for t in rec["tradeoffs"]))


if __name__ == "__main__":
    unittest.main()
