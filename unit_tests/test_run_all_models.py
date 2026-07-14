"""
Tests for the batch eval runner's pure planning logic
(scripts/run_all_models._pick_judge + _plan). No subprocesses, no gateway.

Run from repo root:
  uv run python -m unittest unit_tests.test_run_all_models -v
"""
from __future__ import annotations

import unittest

from frontend.eval_launch import JUDGE_MODELS, model_family
from scripts.run_all_models import _pick_judge, _plan


class PickJudgeTest(unittest.TestCase):
    def test_openai_candidate_gets_non_openai_judge(self) -> None:
        judge = _pick_judge("GPT 4.1 Mini", JUDGE_MODELS)
        self.assertIsNotNone(judge)
        self.assertNotEqual(model_family(judge), model_family("GPT 4.1 Mini"))

    def test_meta_candidate_gets_non_meta_judge(self) -> None:
        judge = _pick_judge("Llama 4 Scout", JUDGE_MODELS)
        self.assertIsNotNone(judge)
        self.assertNotEqual(model_family(judge), "meta")

    def test_none_when_no_cross_family_judge(self) -> None:
        # Only same-family judges available -> no valid pick.
        self.assertIsNone(_pick_judge("GPT 4.1 Mini", ("gpt-5-chat", "gpt-oss-120b")))


class PlanTest(unittest.TestCase):
    def test_one_job_per_model_suite_pair(self) -> None:
        jobs = _plan(["GPT 4.1 Mini", "Llama 4 Scout"],
                     ["it_support_v1", "policy_qa_v1.1"], JUDGE_MODELS)
        self.assertEqual(len(jobs), 4)
        self.assertEqual({j["suite"] for j in jobs}, {"it_support_v1", "policy_qa_v1.1"})

    def test_every_job_has_cross_family_judge(self) -> None:
        jobs = _plan(["GPT 4.1 Mini", "Llama 4 Scout", "Qwen/Qwen2.5-7B-Instruct"],
                     ["it_support_v1"], JUDGE_MODELS)
        for j in jobs:
            self.assertIsNotNone(j["judge"])
            self.assertNotEqual(model_family(j["judge"]), model_family(j["candidate"]))


if __name__ == "__main__":
    unittest.main()
