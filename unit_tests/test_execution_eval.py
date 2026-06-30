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


class CheckJsonTest(unittest.TestCase):
    """Structured-output checker: parse candidate JSON, compare to expected.
    Object key order doesn't matter (dict equality); array order does."""

    def _run(self, response, expected):
        return ex._check_json(response, {"expected": expected})

    def test_exact_object_match(self) -> None:
        ok, err = self._run('{"code": "CS 201", "credits": 3}',
                            {"code": "CS 201", "credits": 3})
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_object_key_order_insensitive(self) -> None:
        ok, _ = self._run('{"credits": 3, "code": "CS 201"}',
                          {"code": "CS 201", "credits": 3})
        self.assertTrue(ok)

    def test_fenced_json_parses(self) -> None:
        ok, _ = self._run('```json\n{"a": 1}\n```', {"a": 1})
        self.assertTrue(ok)

    def test_int_float_equivalence(self) -> None:
        ok, _ = self._run('{"x": 1.0}', {"x": 1})
        self.assertTrue(ok)

    def test_nested_match(self) -> None:
        ok, _ = self._run('{"a": {"b": [1, 2]}}', {"a": {"b": [1, 2]}})
        self.assertTrue(ok)

    def test_array_order_matters(self) -> None:
        ok, _ = self._run('[2, 1]', [1, 2])
        self.assertFalse(ok)

    def test_value_mismatch_fails(self) -> None:
        ok, _ = self._run('{"credits": 4}', {"credits": 3})
        self.assertFalse(ok)

    def test_invalid_json_fails_cleanly(self) -> None:
        ok, err = self._run("not json at all", {"a": 1})
        self.assertFalse(ok)
        self.assertIn("JSON", err)

    def test_empty_response_fails(self) -> None:
        ok, err = self._run("", {"a": 1})
        self.assertFalse(ok)
        self.assertTrue(err)


class CheckNumericTest(unittest.TestCase):
    """Numeric checker: extract a number from the response, tolerance-compare."""

    def _run(self, response, expected, **task):
        return ex._check_numeric(response, {"expected": expected, **task})

    def test_plain_integer(self) -> None:
        ok, err = self._run("42", 42)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_number_in_a_sentence(self) -> None:
        self.assertTrue(self._run("The answer is 42.", 42)[0])

    def test_int_float_equivalence(self) -> None:
        self.assertTrue(self._run("42.0", 42)[0])

    def test_commas_and_currency_stripped(self) -> None:
        self.assertTrue(self._run("$1,234.56", 1234.56)[0])

    def test_negative_and_scientific(self) -> None:
        self.assertTrue(self._run("-5", -5)[0])
        self.assertTrue(self._run("1.2e3", 1200)[0])

    def test_within_tolerance_passes(self) -> None:
        self.assertTrue(self._run("3.1416", 3.14, tolerance=0.01)[0])

    def test_outside_tolerance_fails(self) -> None:
        self.assertFalse(self._run("3.20", 3.14, tolerance=0.01)[0])

    def test_default_is_near_exact(self) -> None:
        # no tolerance given -> off-by-a-bit fails
        self.assertFalse(self._run("5.01", 5)[0])

    def test_no_number_fails_cleanly(self) -> None:
        ok, err = self._run("I don't know", 42)
        self.assertFalse(ok)
        self.assertIn("number", err)


class CheckerRegistryTest(unittest.TestCase):
    def test_sql_checker_registered(self) -> None:
        self.assertIn("sql", ex.CHECKERS)

    def test_json_and_numeric_checkers_registered(self) -> None:
        self.assertIn("json", ex.CHECKERS)
        self.assertIn("numeric", ex.CHECKERS)

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
