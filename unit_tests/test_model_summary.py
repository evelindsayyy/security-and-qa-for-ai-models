"""
Tests for frontend/model_summary.py — cache + rules fallback, no live gateway.

  uv run python -m unittest unit_tests.test_model_summary -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frontend import model_summary


def _rollup(**kwargs) -> dict:
    base = {
        "slug": "gpt-4.1-mini",
        "display_name": "GPT 4.1 Mini",
        "inputs_hash": "abc123",
        "scan": None,
        "safety": {"tier": "low", "pass_rate": 0.9},
        "eval": {"best_overall": 4.0, "suites": ["it_support"], "total_cost_usd": 0.01},
        "benchmark": None,
        "subscores": {"safety": 90.0, "eval": 80.0},
        "aggregate": 85.0,
    }
    base.update(kwargs)
    return base


class ModelSummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.tmp.name)
        self._patch_cache = mock.patch.object(model_summary, "_CACHE_DIR", self.cache_dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_cache_hit_skips_gateway(self) -> None:
        rollup = _rollup()
        cached = {
            "inputs_hash": "abc123",
            "summary": "Cached text.",
            "tradeoffs": ["fast"],
            "source": "ai",
            "has_data": True,
        }
        path = self.cache_dir / "gpt-4.1-mini.recommendation.json"
        path.write_text(json.dumps(cached), encoding="utf-8")

        with self._patch_cache, mock.patch.object(model_summary, "_call_gateway") as gw:
            result = model_summary.get_recommendation_summary(rollup)
        gw.assert_not_called()
        self.assertEqual(result["summary"], "Cached text.")
        self.assertEqual(result["source"], "ai")

    def test_fallback_when_gateway_unconfigured(self) -> None:
        rollup = _rollup()
        with self._patch_cache, mock.patch.object(model_summary, "_gateway_configured", return_value=False):
            result = model_summary.get_recommendation_summary(rollup)
        self.assertEqual(result["source"], "rules_v1")
        self.assertTrue(result["has_data"])

    def test_gateway_failure_falls_back_to_rules(self) -> None:
        rollup = _rollup()
        with (
            self._patch_cache,
            mock.patch.object(model_summary, "_gateway_configured", return_value=True),
            mock.patch.object(model_summary, "_call_gateway", return_value=None),
        ):
            result = model_summary.get_recommendation_summary(rollup)
        self.assertEqual(result["source"], "rules_v1")

    def test_ai_response_cached_on_success(self) -> None:
        rollup = _rollup()
        with (
            self._patch_cache,
            mock.patch.object(model_summary, "_gateway_configured", return_value=True),
            mock.patch.object(model_summary, "_call_gateway", return_value="Strong safety.\n- fast\n- cheap"),
        ):
            result = model_summary.get_recommendation_summary(rollup)
        self.assertEqual(result["source"], "ai")
        path = self.cache_dir / "gpt-4.1-mini.recommendation.json"
        self.assertTrue(path.is_file())
        saved = json.loads(path.read_text())
        self.assertEqual(saved["inputs_hash"], "abc123")

    def test_empty_rollup_uses_rules_without_gateway(self) -> None:
        rollup = _rollup(
            safety=None,
            eval=None,
            subscores={},
            aggregate=None,
        )
        with self._patch_cache, mock.patch.object(model_summary, "_call_gateway") as gw:
            result = model_summary.get_recommendation_summary(rollup)
        gw.assert_not_called()
        self.assertEqual(result["source"], "rules_v1")


if __name__ == "__main__":
    unittest.main()
