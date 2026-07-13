"""Overview stale/critical cards link to the pillar with the most hits."""

from __future__ import annotations

import unittest
from unittest import mock

from frontend import overview


class DominantPillarTest(unittest.TestCase):
    def test_picks_highest_count(self) -> None:
        self.assertEqual(
            overview._dominant_pillar(
                {"scan": 1, "safety": 4, "eval": 2, "benchmark": 0},
                overview._STALE_PILLAR_ORDER,
            ),
            "safety",
        )

    def test_tie_prefers_earlier_in_order(self) -> None:
        self.assertEqual(
            overview._dominant_pillar(
                {"scan": 3, "safety": 3, "eval": 3, "benchmark": 3},
                overview._STALE_PILLAR_ORDER,
            ),
            "scan",
        )

    def test_zero_returns_none(self) -> None:
        self.assertIsNone(
            overview._dominant_pillar(
                {"scan": 0, "safety": 0, "eval": 0, "benchmark": 0},
                overview._STALE_PILLAR_ORDER,
            )
        )


class CollectStaleCriticalHrefTest(unittest.TestCase):
    def test_hrefs_point_at_dominant_pillars(self) -> None:
        with mock.patch(
            "frontend.scan_data.get_scans_data",
            return_value={
                "scans": [
                    {"staleness": {"stale": True}, "severity_tier": "critical"},
                    {"staleness": {"stale": False}, "severity_tier": "low"},
                ]
            },
        ), mock.patch(
            "frontend.safety_data.get_safety_data",
            return_value={
                "models": [
                    {"staleness": {"stale": True}, "tier": "medium"},
                    {"staleness": {"stale": True}, "tier": "critical"},
                    {"staleness": {"stale": True}, "tier": "critical"},
                ]
            },
        ), mock.patch(
            "frontend.eval_run_data.get_runs_data",
            return_value={"runs": [{"staleness": {"stale": True}}]},
        ), mock.patch(
            "frontend.benchmark_data.get_benchmarks_data",
            return_value={"runs": []},
        ):
            stats = overview._collect_stale_and_critical()
        self.assertEqual(stats["stale_count"], 5)  # 1 scan + 3 safety + 1 eval
        self.assertEqual(stats["critical_count"], 3)  # 1 scan + 2 safety
        self.assertIn("/safety", stats["stale_href"])
        self.assertIn("/safety", stats["critical_href"])


if __name__ == "__main__":
    unittest.main()
