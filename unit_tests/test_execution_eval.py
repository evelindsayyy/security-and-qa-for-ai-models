"""
Tests for execution-based SQL scoring (evaluator/execution_eval.py).

All deterministic and offline — in-memory SQLite only, no model calls, no
network. Covers the executor (correct rows, errors don't crash, the ATTACH
guard), the order-insensitive result match, and end-to-end file scoring.

Run from repo root:
  uv run python -m unittest unit_tests.test_execution_eval -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evaluator import execution_eval as ex

_SETUP = ("CREATE TABLE courses (id INTEGER, code TEXT, active INTEGER); "
          "INSERT INTO courses VALUES (1,'CS101',1),(2,'CS201',0),(3,'STA199',1);")


class StripSqlTest(unittest.TestCase):
    def test_strips_code_fences(self) -> None:
        self.assertEqual(
            ex.strip_sql("```sql\nSELECT 1;\n```"), "SELECT 1;")

    def test_plain_passthrough(self) -> None:
        self.assertEqual(ex.strip_sql("  SELECT 1; "), "SELECT 1;")

    def test_empty(self) -> None:
        self.assertEqual(ex.strip_sql(""), "")
        self.assertEqual(ex.strip_sql(None), "")


class RunSqlTest(unittest.TestCase):
    def test_correct_query_returns_rows(self) -> None:
        rows, err = ex.run_sql("SELECT COUNT(*) FROM courses WHERE active=1", _SETUP)
        self.assertIsNone(err)
        self.assertEqual(rows, [(2,)])

    def test_malformed_sql_errors_without_crashing(self) -> None:
        rows, err = ex.run_sql("SELECT FROM nope", _SETUP)
        self.assertIsNone(rows)
        self.assertIsNotNone(err)

    def test_attach_is_rejected(self) -> None:
        rows, err = ex.run_sql("ATTACH DATABASE '/etc/passwd' AS x", _SETUP)
        self.assertIsNone(rows)
        self.assertIn("forbidden", err)

    def test_empty_sql(self) -> None:
        rows, err = ex.run_sql("   ", _SETUP)
        self.assertIsNone(rows)
        self.assertEqual(err, "empty SQL")

    def test_fenced_sql_runs(self) -> None:
        rows, err = ex.run_sql("```sql\nSELECT COUNT(*) FROM courses;\n```", _SETUP)
        self.assertIsNone(err)
        self.assertEqual(rows, [(3,)])


class PassedTest(unittest.TestCase):
    def test_exact_match(self) -> None:
        self.assertTrue(ex.passed([(3,)], [[3]]))

    def test_order_insensitive(self) -> None:
        # candidate returns rows in a different order than expected
        self.assertTrue(ex.passed([("Cara",), ("Ana",)], [["Ana"], ["Cara"]]))

    def test_mismatch(self) -> None:
        self.assertFalse(ex.passed([(4,)], [[3]]))

    def test_none_is_fail(self) -> None:
        self.assertFalse(ex.passed(None, [[3]]))


class LoadSuiteTest(unittest.TestCase):
    def test_real_sql_suite_skips_metadata(self) -> None:
        suite = ex.load_suite("sql_duke_v1")
        self.assertEqual(len(suite), 5)            # 5 questions, metadata skipped
        self.assertIn("sql-001", suite)
        self.assertIn("setup", suite["sql-001"])
        self.assertIn("expected", suite["sql-001"])


class ScoreResultsFileTest(unittest.TestCase):
    def test_executes_and_scores_pass_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "demo_v1.jsonl").write_text(
                json.dumps({"_metadata": "skip"}) + "\n"
                + json.dumps({"id": "q1",
                              "setup": "CREATE TABLE t(n INTEGER); INSERT INTO t VALUES (1),(2),(3);",
                              "expected": [[3]]}) + "\n"
                + json.dumps({"id": "q2",
                              "setup": "CREATE TABLE t(n INTEGER); INSERT INTO t VALUES (1),(2);",
                              "expected": [[2]]}) + "\n",
                encoding="utf-8")
            results = tmp / "run.jsonl"
            results.write_text(
                json.dumps({"question_id": "q1",
                            "candidate_response": "SELECT COUNT(*) FROM t",  # 3 -> PASS
                            "overall": 5.0,
                            "adaptation": {"task_suite_version": "demo_v1",
                                           "candidate_model": "stub"}}) + "\n"
                + json.dumps({"question_id": "q2",
                              "candidate_response": "SELECT SUM(n) FROM t",  # 3 != 2 -> fail
                              "overall": 2.0,
                              "adaptation": {"task_suite_version": "demo_v1",
                                             "candidate_model": "stub"}}) + "\n",
                encoding="utf-8")

            with mock.patch.object(ex, "TASKS_DIR", tmp):
                out = ex.score_results_file(results)

        self.assertEqual(out["n"], 2)
        self.assertEqual(out["passed"], 1)
        self.assertEqual(out["pass_rate"], 0.5)
        by_q = {r["question_id"]: r for r in out["rows"]}
        self.assertTrue(by_q["q1"]["passed"])
        self.assertFalse(by_q["q2"]["passed"])
        self.assertEqual(by_q["q1"]["judge_overall"], 5.0)   # judge carried along

    def test_skips_rows_not_in_suite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "demo_v1.jsonl").write_text(
                json.dumps({"id": "q1", "setup": "CREATE TABLE t(n INTEGER);",
                            "expected": [[0]]}) + "\n", encoding="utf-8")
            results = tmp / "run.jsonl"
            results.write_text(
                json.dumps({"question_id": "q-unknown",
                            "candidate_response": "SELECT 1",
                            "adaptation": {"task_suite_version": "demo_v1"}}) + "\n",
                encoding="utf-8")
            with mock.patch.object(ex, "TASKS_DIR", tmp):
                out = ex.score_results_file(results)
        self.assertEqual(out["n"], 0)


class CheckerRegistryTest(unittest.TestCase):
    def test_sql_checker_registered(self) -> None:
        self.assertIn("sql", ex.CHECKERS)

    def test_check_type_defaults_to_sql(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "s_v1.jsonl").write_text(
                json.dumps({"_metadata": "no check field"}) + "\n"
                + json.dumps({"id": "q1", "setup": "CREATE TABLE t(n)", "expected": [[0]]}) + "\n",
                encoding="utf-8")
            with mock.patch.object(ex, "TASKS_DIR", tmp):
                self.assertEqual(ex.suite_check_type("s_v1"), "sql")

    def test_check_type_read_from_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "s_v1.jsonl").write_text(
                json.dumps({"check": "json"}) + "\n"
                + json.dumps({"id": "q1", "expected": [[0]]}) + "\n",
                encoding="utf-8")
            with mock.patch.object(ex, "TASKS_DIR", tmp):
                self.assertEqual(ex.suite_check_type("s_v1"), "json")

    def test_unknown_check_type_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "bogus_v1.jsonl").write_text(
                json.dumps({"check": "bogus"}) + "\n"
                + json.dumps({"id": "q1", "expected": [[0]]}) + "\n",
                encoding="utf-8")
            results = tmp / "run.jsonl"
            results.write_text(
                json.dumps({"question_id": "q1", "candidate_response": "x",
                            "adaptation": {"task_suite_version": "bogus_v1"}}) + "\n",
                encoding="utf-8")
            with mock.patch.object(ex, "TASKS_DIR", tmp), self.assertRaises(ValueError):
                ex.score_results_file(results)


if __name__ == "__main__":
    unittest.main()
