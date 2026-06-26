"""
Tests for cost-vs-performance enrichment on the comparison page
(frontend/eval_run_data.attach_cost_perf).

Pure: feeds synthetic comparison-row dicts (the shape _aggregate_file /
eval_db_data produce) straight into the enricher. No files, no DB, no models.

Run from repo root:
  uv run python -m unittest unit_tests.test_eval_run_cost_perf -v
"""

from __future__ import annotations

import unittest

from frontend import eval_run_data as erd
from evaluator import cost_perf as cp


def _runs() -> list[dict]:
    # Same suite: A is best+cheapest+fastest, B is worst+priciest+slowest,
    # C is self-hosted ($0). D is a different suite with no overall (skipped).
    return [
        {"candidate_model": "A", "suite": "it_support_v1", "n": 4,
         "overall": 4.5, "total_cost_usd": 0.008, "mean_latency_ms": 1400,
         "inference_backend": "gateway"},
        {"candidate_model": "B", "suite": "it_support_v1", "n": 4,
         "overall": 4.0, "total_cost_usd": 0.040, "mean_latency_ms": 3000,
         "inference_backend": "gateway"},
        {"candidate_model": "C", "suite": "it_support_v1", "n": 4,
         "overall": 3.7, "total_cost_usd": 0.0, "mean_latency_ms": 2200,
         "inference_backend": "dcc"},
        {"candidate_model": "D", "suite": "sql_duke_v1", "n": 3,
         "overall": None, "total_cost_usd": 0.0, "mean_latency_ms": 0},
    ]


class AttachCostPerfTest(unittest.TestCase):
    def _by_model(self, weights=cp.BALANCED) -> dict[str, dict]:
        data = erd.attach_cost_perf({"runs": _runs()}, weights)
        return {r["candidate_model"]: r for r in data["runs"]}

    def test_gateway_runs_get_quality_per_dollar(self) -> None:
        a = self._by_model()["A"]["cost_perf"]
        # cost/response = 0.008 / 4 = 0.002 -> 4.5 / 0.002 = 2250 pts/$
        self.assertAlmostEqual(a["cost_per_response_usd"], 0.002)
        self.assertAlmostEqual(a["quality_per_dollar"], 2250.0)

    def test_zero_cost_run_has_none_qpd_and_a_note(self) -> None:
        c = self._by_model()["C"]["cost_perf"]
        self.assertIsNone(c["quality_per_dollar"])
        self.assertTrue(c["note"])

    def test_run_without_overall_is_skipped(self) -> None:
        self.assertIsNone(self._by_model()["D"]["cost_perf"])

    def test_best_model_has_highest_utility(self) -> None:
        by = self._by_model()
        self.assertGreater(by["A"]["cost_perf"]["utility"],
                           by["B"]["cost_perf"]["utility"])

    def test_components_present_for_audit(self) -> None:
        a = self._by_model()["A"]["cost_perf"]
        for key in ("quality_norm", "cost_norm", "latency_norm", "utility"):
            self.assertIn(key, a)

    def test_weights_recorded_on_page(self) -> None:
        data = erd.attach_cost_perf({"runs": _runs()})
        w = data["cost_perf_weights"]
        self.assertEqual(w["preset"], "balanced")
        self.assertEqual(w["w_quality"], 1.0)

    def test_preset_name_follows_weights(self) -> None:
        data = erd.attach_cost_perf({"runs": _runs()}, cp.BUDGET)
        self.assertEqual(data["cost_perf_weights"]["preset"], "budget")

    def test_per_suite_isolation(self) -> None:
        # D is the only run in sql_duke_v1 and has no overall; enriching the
        # it_support cohort must not crash on or touch it.
        by = self._by_model()
        self.assertIsNone(by["D"]["cost_perf"])
        self.assertIsNotNone(by["A"]["cost_perf"])

    def test_empty_payload_is_safe(self) -> None:
        out = erd.attach_cost_perf({"runs": []})
        self.assertEqual(out["runs"], [])
        self.assertIn("cost_perf_weights", out)


if __name__ == "__main__":
    unittest.main()
