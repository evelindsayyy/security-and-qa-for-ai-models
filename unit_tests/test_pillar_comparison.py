"""
Tests for pillar comparison matrices and catalog batch rollup.

  uv run python -m unittest unit_tests.test_pillar_comparison -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frontend import eval_run_data, safety_data, scan_data
from frontend import model_rollup


class SafetyComparisonTest(unittest.TestCase):
    def test_builds_suite_by_model_matrix(self) -> None:
        models = [
            {
                "gateway_model_id": "GPT 4.1 Mini",
                "slug": "gpt-4-1-mini",
                "profile": "base",
                "suite_rates": {
                    "promptfoo_duke_policy_v1": 0.9,
                    "promptfoo_duke_redteam_v1": 0.8,
                    "garak_subset_v1": None,
                },
            },
            {
                "gateway_model_id": "Llama 3.3",
                "slug": "llama-3-3",
                "profile": "base",
                "suite_rates": {
                    "promptfoo_duke_policy_v1": 0.7,
                    "promptfoo_duke_redteam_v1": None,
                    "garak_subset_v1": 0.6,
                },
            },
        ]
        section = safety_data._build_safety_comparison_section(models)
        self.assertTrue(section["has_comparison"])
        self.assertEqual(section["comparison_models"][0], "GPT 4.1 Mini")
        policy_row = next(r for r in section["comparison_rows"] if r["key"] == "promptfoo_duke_policy_v1")
        self.assertIn("GPT 4.1 Mini", policy_row["cells"])
        self.assertEqual(policy_row["cells"]["GPT 4.1 Mini"]["display"], "90.0%")

    def test_reference_scores_use_preferred_models(self) -> None:
        models = [
            {
                "gateway_model_id": "GPT 4.1 Mini",
                "slug": "gpt-4-1-mini",
                "profile": "base",
                "suite_rates": {"promptfoo_duke_policy_v1": 0.9},
            },
        ]
        ref = safety_data._build_safety_reference_scores(models)
        self.assertIn("GPT 4.1 Mini", ref["reference_models"])
        self.assertIn("Llama 3.3", ref["reference_models"])


class EvalComparisonTest(unittest.TestCase):
    def test_builds_suite_by_model_overall_matrix(self) -> None:
        runs = [
            {
                "candidate_model": "GPT 4.1 Mini",
                "suite": "it_support_v1",
                "overall": 4.2,
                "slug": "run-a",
            },
            {
                "candidate_model": "Llama 3.3",
                "suite": "it_support_v1",
                "overall": 3.8,
                "slug": "run-b",
            },
        ]
        section = eval_run_data._build_eval_comparison_section(runs)
        self.assertTrue(section["has_comparison"])
        row = next(r for r in section["comparison_rows"] if r["key"] == "it_support_v1")
        self.assertEqual(row["cells"]["GPT 4.1 Mini"]["display"], "4.20")


class ScanComparisonTest(unittest.TestCase):
    def test_tool_status_and_matrix(self) -> None:
        data = {
            "model_id": "meta-llama/Llama-3.2-1B",
            "tool_results": {
                "modelscan": {"total_issues": 0},
                "fickling": {"severity": "LIKELY_UNSAFE"},
                "modelaudit": {"actionable_issue_count": 1},
                "dependencies": {"vuln_count": 0},
                "secrets": {"secret_count": 0},
            },
        }
        status = scan_data._tool_status_from_data(data)
        self.assertEqual(status["modelscan"]["display"], "0")
        self.assertEqual(status["fickling"]["display"], "LIKELY_UNSAFE")

        scans = [
            {
                "slug": "meta-llama--Llama-3.2-1B",
                "model_id": "meta-llama/Llama-3.2-1B",
                "tool_status": status,
            }
        ]
        section = scan_data._build_scan_comparison_section(scans)
        self.assertTrue(section["has_comparison"])
        self.assertIn("meta-llama/Llama-3.2-1B", section["comparison_models"])


class CatalogBatchRollupTest(unittest.TestCase):
    def setUp(self) -> None:
        model_rollup.clear_models_union_cache()

    def test_rollups_for_gateway_ids_calls_union_once(self) -> None:
        union = [
            {
                "slug": "gpt-4.1-mini",
                "display_name": "GPT 4.1 Mini",
                "aggregate": 80.0,
            }
        ]
        with mock.patch.object(model_rollup, "get_models_union", return_value=union) as union_mock:
            result = model_rollup.rollups_for_gateway_ids(["GPT 4.1 Mini", "nope-model"])
        union_mock.assert_called_once()
        self.assertEqual(result["GPT 4.1 Mini"]["slug"], "gpt-4.1-mini")
        self.assertEqual(result["nope-model"]["aggregate"], None)


class SafetyDataFilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_merged(self, slug: str, payload: dict, profile: str = "base") -> None:
        d = self.out / slug / profile
        d.mkdir(parents=True)
        (d / "merged_safety_result.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_get_safety_data_includes_comparison(self) -> None:
        self._write_merged(
            "gpt-4-1-mini",
            {
                "gateway_model_id": "GPT 4.1 Mini",
                "summary_pass_rate": 0.9,
                "findings": [],
                "runs": [
                    {"probe_suite": "promptfoo_duke_policy_v1", "summary_pass_rate": 0.9},
                ],
            },
        )
        from frontend import safety_db_data

        with mock.patch.object(safety_data, "OUTPUT_DIR", self.out), \
             mock.patch.object(safety_db_data, "available", return_value=False):
            data = safety_data.get_safety_data()
        self.assertIn("has_comparison", data)
        self.assertNotIn("category_heatmap", data)


if __name__ == "__main__":
    unittest.main()
