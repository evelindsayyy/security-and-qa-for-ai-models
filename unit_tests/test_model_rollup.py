"""
Tests for frontend/model_rollup.py — the cross-pillar union/rollup builder.
Each pillar's get_*_data() is mocked; no disk/DB access.

  uv run python -m unittest unit_tests.test_model_rollup -v
"""

from __future__ import annotations

import unittest
from unittest import mock

from frontend import model_rollup


def _patched(scans=None, safety_models=None, eval_runs=None, benchmark_runs=None):
    model_rollup.clear_models_union_cache()
    return (
        mock.patch.object(
            model_rollup.scan_data, "get_scans_data",
            return_value={"scans": scans or []},
        ),
        mock.patch.object(
            model_rollup.safety_data, "get_safety_data",
            return_value={"models": safety_models or []},
        ),
        mock.patch.object(
            model_rollup.eval_run_data, "get_runs_data",
            return_value={"runs": eval_runs or []},
        ),
        mock.patch.object(
            model_rollup.benchmark_data, "get_benchmarks_data",
            return_value={"runs": benchmark_runs or []},
        ),
    )


class GetModelsUnionTest(unittest.TestCase):
    def test_union_across_pillars_with_no_overlap(self) -> None:
        scans = [{"slug": "BAAI--bge-small", "model_id": "BAAI/bge-small",
                  "severity_tier": "low", "overall_risk_score": 5}]
        safety = [{"slug": "gpt-4-1-mini", "profile": "base", "gateway_model_id": "GPT 4.1 Mini",
                   "display_name": "GPT 4.1 Mini", "tier": "low", "summary_pass_rate": 0.9}]
        patches = _patched(scans=scans, safety_models=safety)
        with patches[0], patches[1], patches[2], patches[3]:
            rows = model_rollup.get_models_union()

        by_slug = {r["slug"]: r for r in rows}
        self.assertEqual(len(rows), 2)
        self.assertIsNotNone(by_slug["BAAI--bge-small"]["scan"])
        self.assertIsNone(by_slug["BAAI--bge-small"]["safety"])
        self.assertIsNotNone(by_slug["gpt-4.1-mini"]["safety"])
        self.assertIsNone(by_slug["gpt-4.1-mini"]["scan"])

    def test_safety_and_eval_merge_into_one_row_by_gateway_slug(self) -> None:
        safety = [{"slug": "gpt-4-1-mini", "profile": "base", "gateway_model_id": "GPT 4.1 Mini",
                   "display_name": "GPT 4.1 Mini", "tier": "low", "summary_pass_rate": 0.9}]
        evals = [
            {"candidate_model": "GPT 4.1 Mini", "suite": "it_support", "overall": 4.5,
             "mean_latency_ms": 800, "total_cost_usd": 0.01},
            {"candidate_model": "GPT 4.1 Mini", "suite": "policy_qa", "overall": 4.0,
             "mean_latency_ms": 900, "total_cost_usd": 0.02},
        ]
        patches = _patched(safety_models=safety, eval_runs=evals)
        with patches[0], patches[1], patches[2], patches[3]:
            rows = model_rollup.get_models_union()

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["slug"], "gpt-4.1-mini")
        self.assertIsNotNone(row["safety"])
        self.assertEqual(row["eval"]["n_runs"], 2)
        self.assertEqual(row["eval"]["best_overall"], 4.5)
        self.assertEqual(sorted(row["eval"]["suites"]), ["it_support", "policy_qa"])
        self.assertEqual(row["eval"]["mean_latency_ms"], 850)
        self.assertAlmostEqual(row["eval"]["total_cost_usd"], 0.03)

    def test_benchmark_rows_grouped_by_kind(self) -> None:
        benchmarks = [
            {"model": "gpt-5-chat", "kind": "mmlu", "headline_value": 0.71,
             "headline_display": "71.0%", "score_class": "score-strong"},
            {"model": "gpt-5-chat", "kind": "truthfulqa", "headline_value": 0.6,
             "headline_display": "60.0%", "score_class": "score-mid"},
        ]
        patches = _patched(benchmark_runs=benchmarks)
        with patches[0], patches[1], patches[2], patches[3]:
            rows = model_rollup.get_models_union()

        self.assertEqual(len(rows), 1)
        kinds = rows[0]["benchmark"]["kinds"]
        self.assertEqual(set(kinds), {"mmlu", "truthfulqa"})
        self.assertEqual(kinds["mmlu"]["headline_value"], 0.71)

    def test_benchmark_rows_missing_model_are_skipped(self) -> None:
        benchmarks = [{"model": "—", "kind": "mmlu", "headline_value": None}]
        patches = _patched(benchmark_runs=benchmarks)
        with patches[0], patches[1], patches[2], patches[3]:
            rows = model_rollup.get_models_union()
        self.assertEqual(rows, [])

    def test_rows_sorted_by_slug(self) -> None:
        scans = [
            {"slug": "zzz-model", "model_id": "zzz/model", "severity_tier": "low", "overall_risk_score": 1},
            {"slug": "aaa-model", "model_id": "aaa/model", "severity_tier": "low", "overall_risk_score": 1},
        ]
        patches = _patched(scans=scans)
        with patches[0], patches[1], patches[2], patches[3]:
            rows = model_rollup.get_models_union()
        self.assertEqual([r["slug"] for r in rows], ["aaa-model", "zzz-model"])


class GetModelRollupTest(unittest.TestCase):
    def test_returns_matching_row(self) -> None:
        safety = [{"slug": "gpt-4-1-mini", "profile": "base", "gateway_model_id": "GPT 4.1 Mini",
                   "display_name": "GPT 4.1 Mini", "tier": "low", "summary_pass_rate": 0.9}]
        patches = _patched(safety_models=safety)
        with patches[0], patches[1], patches[2], patches[3]:
            row = model_rollup.get_model_rollup("gpt-4.1-mini")
        self.assertIsNotNone(row)
        self.assertEqual(row["slug"], "gpt-4.1-mini")

    def test_returns_none_when_unmatched(self) -> None:
        patches = _patched()
        with patches[0], patches[1], patches[2], patches[3]:
            row = model_rollup.get_model_rollup("nope")
        self.assertIsNone(row)


class AggregateScoreTest(unittest.TestCase):
    def test_pillar_subscores_normalize_to_0_100(self) -> None:
        row = {
            "scan": {"overall_risk_score": 20},
            "safety": {"pass_rate": 0.8},
            "eval": {"best_overall": 4.0},
            "benchmark": {"kinds": {"mmlu": {"headline_value": 0.7}}},
        }
        sub = model_rollup.pillar_subscores(row)
        self.assertAlmostEqual(sub["scan"], 80.0)
        self.assertAlmostEqual(sub["safety"], 80.0)
        self.assertAlmostEqual(sub["eval"], 80.0)
        self.assertAlmostEqual(sub["benchmark"], 70.0)

    def test_aggregate_mean_excludes_missing_pillars(self) -> None:
        row = {
            "safety": {"pass_rate": 0.9},
            "eval": {"best_overall": 5.0},
        }
        self.assertAlmostEqual(model_rollup.aggregate_score(row), 95.0)

    def test_aggregate_none_when_no_data(self) -> None:
        self.assertIsNone(model_rollup.aggregate_score({}))

    def test_enrich_row_attaches_aggregate_and_norm(self) -> None:
        row = {
            "slug": "gpt-4.1-mini",
            "display_name": "GPT 4.1 Mini",
            "safety": {"pass_rate": 0.5},
            "benchmark": {"kinds": {"tqa": {"headline_value": 0.6}}},
        }
        enriched = model_rollup.enrich_row(row)
        self.assertAlmostEqual(enriched["aggregate"], 55.0)
        self.assertAlmostEqual(enriched["benchmark"]["norm"], 60.0)
        self.assertIn("inputs_hash", enriched)


class LookupRollupTest(unittest.TestCase):
    def test_lookup_returns_empty_gateway_shell(self) -> None:
        patches = _patched()
        with patches[0], patches[1], patches[2], patches[3]:
            row = model_rollup.lookup_rollup_for_gateway("GPT 4.1 Mini")
        self.assertEqual(row["slug"], "gpt-4.1-mini")
        self.assertIsNone(row["aggregate"])
        self.assertIsNone(row["safety"])

    def test_empty_gateway_rollup_has_inputs_hash(self) -> None:
        row = model_rollup.empty_gateway_rollup("GPT 4.1 Mini")
        self.assertEqual(row["display_name"], "GPT 4.1 Mini")
        self.assertIn("inputs_hash", row)


if __name__ == "__main__":
    unittest.main()
