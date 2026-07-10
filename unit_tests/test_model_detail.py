"""
Tests for the per-model report-card page (frontend/eval_run_data
get_model_detail + model_slug) and the custom-suite exclusion from the
comparison table. No database, no API calls — get_runs_data is stubbed.

Run from repo root:
  uv run python -m unittest unit_tests.test_model_detail -v
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import eval_run_data as erd


def _run(model="gpt-5-chat", suite="it_support_v1", judge="Llama 4 Maverick",
         overall=4.9, fname="f.jsonl"):
    return {
        "filename": fname, "slug": fname[:-6], "timestamp": "t",
        "suite": suite, "candidate_model": model, "judge_model": judge,
        "n": 12, "ok": 12, "cand_fail": 0, "judge_fail": 0,
        "dims": ["accuracy", "tone"],
        "dim_means": {"accuracy": 5.0, "tone": 3.0},
        "overall": overall, "mean_latency_ms": 1000, "p95_latency_ms": 1200,
        "total_cost_usd": 0.01, "note": "",
    }


class ModelSlugTest(unittest.TestCase):
    def test_spaces_and_specials_become_dashes(self) -> None:
        self.assertEqual(erd.model_slug("GPT 4.1 Mini"), "GPT-4.1-Mini")
        self.assertEqual(erd.model_slug("gpt-5-chat"), "gpt-5-chat")


class GetModelDetailTest(unittest.TestCase):
    def _stub(self, runs):
        # get_runs_data already deduped/postprocessed; add model_slug like
        # _postprocess_runs does.
        for r in runs:
            r["model_slug"] = erd.model_slug(r["candidate_model"])
        return mock.patch.object(erd, "get_runs_data", return_value={"runs": runs})

    def test_groups_one_models_runs_across_suites(self) -> None:
        runs = [
            _run(model="gpt-5-chat", suite="it_support_v1", overall=4.9),
            _run(model="gpt-5-chat", suite="policy_qa_v1.1", overall=4.3),
            _run(model="GPT 4.1 Mini", suite="it_support_v1", overall=4.2),
        ]
        with self._stub(runs):
            detail = erd.get_model_detail("gpt-5-chat")
        self.assertEqual(detail["model"], "gpt-5-chat")
        self.assertEqual(detail["n_runs"], 2)
        self.assertEqual(detail["suites"], ["it_support_v1", "policy_qa_v1.1"])
        self.assertEqual(detail["best_overall"], 4.9)

    def test_slug_with_spaces_matches(self) -> None:
        runs = [_run(model="GPT 4.1 Mini", overall=4.2)]
        with self._stub(runs):
            detail = erd.get_model_detail("GPT-4.1-Mini")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["model"], "GPT 4.1 Mini")

    def test_unknown_model_returns_none(self) -> None:
        with self._stub([_run()]):
            self.assertIsNone(erd.get_model_detail("no-such-model"))

    def test_unsafe_slug_returns_none(self) -> None:
        self.assertIsNone(erd.get_model_detail("../../etc"))


class CustomExclusionTest(unittest.TestCase):
    def test_custom_runs_excluded_from_comparison(self) -> None:
        runs = [
            _run(suite="it_support_v1", fname="a.jsonl"),
            _run(suite="custom_20260615T000000Z", fname="b.jsonl"),
        ]
        out = erd._postprocess_runs(runs)
        suites = {r["suite"] for r in out["runs"]}
        self.assertIn("it_support_v1", suites)
        self.assertNotIn("custom_20260615T000000Z", suites)


if __name__ == "__main__":
    unittest.main()
