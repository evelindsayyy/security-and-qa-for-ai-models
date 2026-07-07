"""
Tests for pillar rerun-param helpers.

  uv run python -m unittest unit_tests.test_rerun_params -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frontend import eval_run_data, safety_data, scan_data


class SafetyRerunParamsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self._patch_out = mock.patch.object(safety_data, "OUTPUT_DIR", self.out)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_merged(self, slug: str, payload: dict, profile: str = "base") -> None:
        d = self.out / slug / profile
        d.mkdir(parents=True)
        (d / "merged_safety_result.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_returns_prefill_from_detail(self) -> None:
        self._write_merged(
            "gpt-4-1-mini",
            {"gateway_model_id": "GPT 4.1 Mini", "summary_pass_rate": 0.9, "findings": [], "runs": []},
        )
        from frontend import safety_db_data

        with (
            self._patch_out,
            mock.patch.object(safety_db_data, "available", return_value=False),
        ):
            params = safety_data.get_safety_rerun_params("gpt-4-1-mini", "base")
        self.assertEqual(params["gateway_model"], "GPT 4.1 Mini")
        self.assertEqual(params["redteam_profile"], "base")
        self.assertTrue(params["run_policy"])

    def test_returns_none_when_missing(self) -> None:
        from frontend import safety_db_data

        with (
            self._patch_out,
            mock.patch.object(safety_db_data, "available", return_value=False),
        ):
            self.assertIsNone(safety_data.get_safety_rerun_params("nope"))


class EvalRerunParamsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.results = Path(self.tmp.name)
        self._patch_results = mock.patch.object(eval_run_data, "RESULTS_DIR", self.results)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _jsonl_row(self) -> dict:
        return {
            "evaluation_run_id": "9e8d7c6b-0000-0000-0000-000000000001",
            "timestamp": "2026-06-12T15:00:00Z",
            "question_id": "it-support-001",
            "suite": "it_support",
            "schema_version": "1.0.0",
            "adaptation": {
                "candidate_model": "GPT 4.1 Mini",
                "candidate_model_version": "Gateway 2026-06",
                "system_prompt_version": "it_support_v1",
                "user_prompt_template_version": "raw_question_v1",
                "temperature": 0.2,
                "max_tokens": 500,
                "task_suite_version": "it_support_v1",
                "rubric_version": "it_support_v1",
                "judge_model": "gpt-5-chat",
                "judge_prompt_version": "reference_based_v2",
            },
            "candidate_response": "an answer",
            "scores": {"accuracy": {"score": 5.0, "rationale": "ok"}},
            "overall": 4.5,
            "operational": {
                "latency_ms": 1000,
                "prompt_tokens": 200,
                "completion_tokens": 100,
                "estimated_cost_usd": 0.001,
            },
            "candidate_failed": False,
            "judge_failed": False,
            "error": None,
        }

    def test_returns_prefill_from_detail(self) -> None:
        slug = "20250101_120000_gpt-4-1-mini_it-support"
        (self.results / f"{slug}.jsonl").write_text(
            json.dumps(self._jsonl_row()) + "\n",
            encoding="utf-8",
        )
        from frontend import eval_db_data

        with (
            self._patch_results,
            mock.patch.object(eval_db_data, "available", return_value=False),
        ):
            params = eval_run_data.get_eval_rerun_params(slug)
        self.assertEqual(params["candidate_model"], "GPT 4.1 Mini")
        self.assertEqual(params["judge_model"], "gpt-5-chat")
        self.assertEqual(params["suite"], "it_support_v1")


class ScanRerunParamsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self._patch_out = mock.patch.object(scan_data, "OUTPUT_DIR", self.out)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_returns_hf_repo_from_detail(self) -> None:
        slug = "meta-llama--Llama-3.2-1B"
        d = self.out / slug
        d.mkdir(parents=True)
        (d / "scan_result.json").write_text(
            json.dumps({"model_id": "meta-llama/Llama-3.2-1B", "overall_risk_score": 5}),
            encoding="utf-8",
        )
        from frontend import scan_db_data

        with (
            self._patch_out,
            mock.patch.object(scan_db_data, "available", return_value=False),
        ):
            params = scan_data.get_scan_rerun_params(slug)
        self.assertEqual(params["hf_repo"], "meta-llama/Llama-3.2-1B")


if __name__ == "__main__":
    unittest.main()
