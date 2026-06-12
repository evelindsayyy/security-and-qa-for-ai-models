"""
Tests for evaluator/db/load_results.py — pure transforms only, no database.

Run from repo root:
  uv run python -m unittest unit_tests.test_db_loader -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_DB_DIR = Path(__file__).resolve().parent.parent / "evaluator" / "db"
sys.path.insert(0, str(_DB_DIR))

from load_results import (  # noqa: E402
    result_rows,
    run_row,
    split_suite_version,
    suite_row,
)


def _jsonl_row(qid="it-support-001", overall=4.5, failed=False):
    return {
        "evaluation_run_id": "9e8d7c6b-0000-0000-0000-000000000001",
        "timestamp": "2026-06-12T15:00:00Z",
        "question_id": qid,
        "suite": "it_support",
        "schema_version": "1.0.0",
        "adaptation": {
            "candidate_model": "gpt-5-chat",
            "task_suite_version": "it_support_v1",
            "rubric_version": "it_support_v1",
            "judge_model": "Llama 4 Maverick",
            "judge_prompt_version": "reference_based_v2",
            "temperature": 0.2,
            "max_tokens": 500,
        },
        "candidate_response": "" if failed else "an answer",
        "scores": {} if failed else {"accuracy": {"score": 5, "rationale": "ok"}},
        "overall": None if failed else overall,
        "operational": {
            "latency_ms": 1000,
            "prompt_tokens": 200,
            "completion_tokens": 100,
            "estimated_cost_usd": 0.001,
        },
        "candidate_failed": failed,
        "judge_failed": False,
        "error": "empty response" if failed else None,
    }


class SplitSuiteVersionTest(unittest.TestCase):
    def test_v1(self) -> None:
        self.assertEqual(split_suite_version("it_support_v1"), ("it_support", "v1"))

    def test_minor_version(self) -> None:
        self.assertEqual(split_suite_version("policy_qa_v1.1"), ("policy_qa", "v1.1"))

    def test_no_version_marker(self) -> None:
        self.assertEqual(split_suite_version("adhoc"), ("adhoc", "v?"))


class SuiteRowTest(unittest.TestCase):
    def test_fields_from_adaptation(self) -> None:
        s = suite_row([_jsonl_row()])
        self.assertEqual(s["suite_key"], "it_support")
        self.assertEqual(s["version"], "v1")
        self.assertEqual(s["rubric_version"], "it_support_v1")


class RunRowTest(unittest.TestCase):
    def test_aggregates_and_identity(self) -> None:
        rows = [_jsonl_row(overall=4.0), _jsonl_row(qid="q2", overall=5.0)]
        r = run_row(rows, "file.jsonl")
        self.assertEqual(r["id"], rows[0]["evaluation_run_id"])  # JSONL uuid is the PK
        self.assertEqual(r["gateway_model_id"], "gpt-5-chat")
        self.assertAlmostEqual(r["aggregate_score"], 4.5)
        self.assertEqual(r["tokens_in_total"], 400)
        self.assertEqual(r["tokens_out_total"], 200)
        self.assertAlmostEqual(float(r["cost_usd_total"]), 0.002)
        self.assertEqual(r["source_file"], "file.jsonl")

    def test_all_failed_run_has_null_score(self) -> None:
        r = run_row([_jsonl_row(failed=True)], "f.jsonl")
        self.assertIsNone(r["aggregate_score"])


class ResultRowsTest(unittest.TestCase):
    def test_one_row_per_question_with_detail(self) -> None:
        out = result_rows([_jsonl_row(), _jsonl_row(qid="q2", failed=True)])
        self.assertEqual(len(out), 2)
        ok, fail = out
        self.assertEqual(ok["task_id"], "it-support-001")
        self.assertEqual(ok["metric"], "judge_score")
        self.assertEqual(ok["score"], 4.5)
        self.assertIn("accuracy", ok["detail"]["scores"])
        # failed question is queryable, not dropped
        self.assertTrue(fail["candidate_failed"])
        self.assertIsNone(fail["score"])
        self.assertEqual(fail["detail"]["error"], "empty response")


if __name__ == "__main__":
    unittest.main()
