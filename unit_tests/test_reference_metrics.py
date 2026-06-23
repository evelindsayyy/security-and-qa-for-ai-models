"""
Tests for the ROUGE-L reference metric (evaluator/reference_metrics.py).

All deterministic and offline — pure-Python LCS, no model download, no network.
BERTScore (which pulls a model) is intentionally not exercised here.

Run from repo root:
  uv run python -m unittest unit_tests.test_reference_metrics -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evaluator import reference_metrics as rm


class TokenizeTest(unittest.TestCase):
    def test_lowercases_and_splits_on_words(self) -> None:
        self.assertEqual(rm.tokenize("Hello, World!  VPN-down"),
                         ["hello", "world", "vpn", "down"])

    def test_empty_and_none(self) -> None:
        self.assertEqual(rm.tokenize(""), [])
        self.assertEqual(rm.tokenize(None), [])


class LcsTest(unittest.TestCase):
    def test_subsequence_not_substring(self) -> None:
        # "a c" is a subsequence of "a b c" (gap allowed) -> length 2
        self.assertEqual(rm.lcs_length(["a", "b", "c"], ["a", "c"]), 2)

    def test_order_matters(self) -> None:
        # reversed sequence shares only a length-1 subsequence
        self.assertEqual(rm.lcs_length(["a", "b", "c"], ["c", "b", "a"]), 1)

    def test_empty(self) -> None:
        self.assertEqual(rm.lcs_length([], ["a"]), 0)
        self.assertEqual(rm.lcs_length(["a"], []), 0)


class RougeLTest(unittest.TestCase):
    def test_identical_is_one(self) -> None:
        m = rm.rouge_l("the cat sat on the mat", "the cat sat on the mat")
        self.assertEqual(m["f1"], 1.0)
        self.assertEqual(m["precision"], 1.0)
        self.assertEqual(m["recall"], 1.0)

    def test_disjoint_is_zero(self) -> None:
        self.assertEqual(rm.rouge_l("x y z", "a b c")["f1"], 0.0)

    def test_partial_overlap_known_value(self) -> None:
        # candidate 3 tokens, reference 2 tokens, LCS 2
        # precision = 2/3, recall = 2/2 = 1, f1 = 2*(2/3*1)/(2/3+1) = 0.8
        m = rm.rouge_l("the cat sat", "the cat")
        self.assertEqual(m["lcs"], 2)
        self.assertAlmostEqual(m["precision"], 0.6667, places=3)
        self.assertEqual(m["recall"], 1.0)
        self.assertEqual(m["f1"], 0.8)

    def test_order_penalised(self) -> None:
        # same words, reversed -> LCS 1 of 3 each -> p=r=1/3, f1=1/3
        m = rm.rouge_l("alpha beta gamma", "gamma beta alpha")
        self.assertEqual(m["lcs"], 1)
        self.assertAlmostEqual(m["f1"], 0.3333, places=3)

    def test_empty_candidate_is_zero(self) -> None:
        m = rm.rouge_l("", "the cat sat")
        self.assertEqual(m["f1"], 0.0)
        self.assertEqual(m["cand_len"], 0)


class LoadReferencesTest(unittest.TestCase):
    def test_real_summarization_suite_skips_metadata(self) -> None:
        refs = rm.load_references("summarization_v1")
        self.assertEqual(len(refs), 6)              # 6 docs, metadata line skipped
        self.assertIn("summ-001", refs)
        self.assertIn("VPN", refs["summ-001"])      # the actual reference text


class ScoreResultsFileTest(unittest.TestCase):
    def test_joins_candidates_to_references_and_means(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # a tiny fake suite + a results file referencing it
            (tmp / "demo_v1.jsonl").write_text(
                json.dumps({"_metadata": "skip me"}) + "\n"
                + json.dumps({"id": "q1", "reference": "the cat sat on the mat"}) + "\n"
                + json.dumps({"id": "q2", "reference": "duke vpn maintenance saturday"}) + "\n",
                encoding="utf-8")
            results = tmp / "run.jsonl"
            results.write_text(
                json.dumps({"question_id": "q1",
                            "candidate_response": "the cat sat on the mat",  # identical -> 1.0
                            "overall": 5.0,
                            "adaptation": {"task_suite_version": "demo_v1",
                                           "candidate_model": "stub"}}) + "\n"
                + json.dumps({"question_id": "q2",
                              "candidate_response": "completely unrelated words here",  # -> 0.0
                              "overall": 2.0,
                              "adaptation": {"task_suite_version": "demo_v1",
                                             "candidate_model": "stub"}}) + "\n",
                encoding="utf-8")

            with mock.patch.object(rm, "TASKS_DIR", tmp):
                out = rm.score_results_file(results)

        self.assertEqual(out["n"], 2)
        self.assertEqual(out["candidate_model"], "stub")
        by_q = {r["question_id"]: r for r in out["rows"]}
        self.assertEqual(by_q["q1"]["rouge_l_f1"], 1.0)
        self.assertEqual(by_q["q2"]["rouge_l_f1"], 0.0)
        self.assertEqual(by_q["q1"]["judge_overall"], 5.0)   # judge score carried along
        self.assertEqual(out["mean_rouge_l_f1"], 0.5)         # (1.0 + 0.0) / 2

    def test_skips_rows_not_in_suite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "demo_v1.jsonl").write_text(
                json.dumps({"id": "q1", "reference": "hello world"}) + "\n",
                encoding="utf-8")
            results = tmp / "run.jsonl"
            results.write_text(
                json.dumps({"question_id": "q-unknown",
                            "candidate_response": "anything",
                            "adaptation": {"task_suite_version": "demo_v1"}}) + "\n",
                encoding="utf-8")
            with mock.patch.object(rm, "TASKS_DIR", tmp):
                out = rm.score_results_file(results)
        self.assertEqual(out["n"], 0)
        self.assertEqual(out["mean_rouge_l_f1"], 0.0)


if __name__ == "__main__":
    unittest.main()
