"""
Tests for the Postgres read path (frontend/eval_db_data.py) — no database.

The contract under test: the DB path must produce the SAME dicts as the
file path, and the dispatcher must never touch psycopg when EFFICACY_DB_DSN
is unset (file behavior is the unconditional fallback).

Run from repo root:
  uv run python -m unittest unit_tests.test_eval_db_data -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import eval_db_data, eval_run_data


def _jsonl_row(qid="it-support-001", overall=4.5):
    return {
        "evaluation_run_id": "9e8d7c6b-0000-0000-0000-000000000001",
        "timestamp": "2026-06-12T15:00:00Z",
        "question_id": qid,
        "suite": "it_support",
        "schema_version": "1.0.0",
        "adaptation": {
            "candidate_model": "gpt-5-chat",
            "candidate_model_version": "Gateway 2026-06",
            "system_prompt_version": "it_support_v1",
            "user_prompt_template_version": "raw_question_v1",
            "temperature": 0.2,
            "max_tokens": 500,
            "task_suite_version": "it_support_v1",
            "rubric_version": "it_support_v1",
            "judge_model": "Llama 4 Maverick",
            "judge_prompt_version": "reference_based_v2",
        },
        "candidate_response": "an answer",
        "scores": {"accuracy": {"score": 5.0, "rationale": "ok"},
                   "tone": {"score": 3.0, "rationale": "fine"}},
        "overall": overall,
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


def _db_shape(rows, source_file):
    """The same data as the DB read path would fetch it."""
    run = {
        "id": rows[0]["evaluation_run_id"],
        "source_file": source_file,
        "gateway_model_id": rows[0]["adaptation"]["candidate_model"],
        "judge_model": rows[0]["adaptation"]["judge_model"],
        "started_at": datetime(2026, 6, 12, 15, 0, 0, tzinfo=timezone.utc),
        "adaptation": rows[0]["adaptation"],
    }
    results = [{
        "task_id": r["question_id"],
        "score": r["overall"],
        "latency_ms": r["operational"]["latency_ms"],
        "tokens_in": r["operational"]["prompt_tokens"],
        "tokens_out": r["operational"]["completion_tokens"],
        "cost_usd": r["operational"]["estimated_cost_usd"],
        "candidate_failed": r["candidate_failed"],
        "judge_failed": r["judge_failed"],
        "detail": {
            "candidate_response": r["candidate_response"],
            "scores": r["scores"],
            "dim_order": list(r["scores"].keys()),
            "error": r["error"],
            "schema_version": r["schema_version"],
        },
    } for r in rows]
    return run, results


class DbRowMatchesFileRowTest(unittest.TestCase):
    """The comparison-table row built from DB data must equal the one built
    from the equivalent JSONL file."""

    def test_same_keys_and_values(self) -> None:
        rows = [_jsonl_row(), _jsonl_row(qid="it-support-002", overall=4.0)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260612T150000Z_it_support_v1_gpt-5-chat.jsonl"
            path.write_text(
                "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            file_row = eval_run_data._aggregate_file(path)

        run, results = _db_shape(rows, path.name)
        db_row = eval_db_data._aggregate_db_run(run, results)

        self.assertEqual(set(file_row), set(db_row))  # identical contract
        for key in file_row:
            self.assertEqual(file_row[key], db_row[key], f"mismatch on {key!r}")


class AvailabilityTest(unittest.TestCase):
    def test_no_dsn_means_unavailable(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            eval_db_data._avail_cache.update(checked_at=float("-inf"), ok=False)
            self.assertFalse(eval_db_data.available())

    def test_dispatcher_serves_files_when_db_unavailable(self) -> None:
        with mock.patch.object(eval_db_data, "available", return_value=False):
            data = eval_run_data.get_runs_data()
        self.assertIn("has_runs", data)  # file-path contract served

    def test_detail_falls_back_to_files_when_slug_not_in_db(self) -> None:
        # Postgres reachable but row missing (smoke/stub on disk only) → files.
        with mock.patch.object(eval_db_data, "available", return_value=True), \
             mock.patch.object(eval_db_data, "get_run_detail_db",
                               return_value=None), \
             mock.patch.object(eval_run_data, "_get_run_detail_files",
                               return_value={"slug": "from-files"}):
            detail = eval_run_data.get_run_detail("some-slug")
        self.assertEqual(detail, {"slug": "from-files"})

    def test_dispatcher_survives_db_exceptions(self) -> None:
        with mock.patch.object(eval_db_data, "available",
                               side_effect=RuntimeError("db exploded")):
            data = eval_run_data.get_runs_data()
        self.assertIn("has_runs", data)  # silent fallback, never a 500


def _exec_jsonl_row(qid, candidate_response, *, suite="mini_exec_v1"):
    """A results row for an execution suite (overrides suite + response)."""
    row = _jsonl_row(qid=qid, overall=4.0)
    row["suite"] = suite
    row["adaptation"] = {**row["adaptation"],
                         "task_suite_version": suite,
                         "rubric_version": suite}
    row["candidate_response"] = candidate_response
    return row


class ExecutionPassRateOnDbPathTest(unittest.TestCase):
    """The DB path must attach the functional pass-rate for execution suites,
    exactly like the file path — otherwise the Exec column reads — for every
    model whenever the dashboard is served from Postgres."""

    @staticmethod
    def _write_mini_json_suite(tmp) -> Path:
        # A self-contained JSON-check suite (no SQLite, no model calls): the
        # metadata line selects the checker; each task carries an `expected`.
        suite = Path(tmp) / "mini_exec_v1.jsonl"
        suite.write_text("\n".join(json.dumps(r) for r in [
            {"check": "json"},
            {"id": "q1", "expected": {"a": 1}},
            {"id": "q2", "expected": {"a": 2}},
        ]), encoding="utf-8")
        return Path(tmp)

    def test_db_path_emits_pass_rate_matching_file_path(self) -> None:
        import execution_eval  # bare import: eval_run_data put evaluator/ on sys.path

        rows = [
            _exec_jsonl_row("q1", '{"a": 1}'),   # matches expected -> pass
            _exec_jsonl_row("q2", '{"a": 5}'),   # wrong value     -> fail
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tasks_dir = self._write_mini_json_suite(tmp)
            results_path = Path(tmp) / "20260612T150000Z_mini_exec_v1_gpt-5-chat.jsonl"
            results_path.write_text(
                "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            with mock.patch.object(execution_eval, "TASKS_DIR", tasks_dir):
                file_row = eval_run_data._aggregate_file(results_path)
                run, results = _db_shape(rows, results_path.name)
                db_row = eval_db_data._aggregate_db_run(run, results)

        self.assertEqual(file_row["execution_pass_rate"], 0.5)   # 1 of 2 passed
        self.assertEqual(db_row["execution_pass_rate"], 0.5)     # DB path agrees
        self.assertEqual(db_row["execution_passed"], 1)
        self.assertEqual(db_row["execution_n"], 2)
        self.assertEqual(
            db_row["execution_pass_rate"], file_row["execution_pass_rate"])

    def test_judge_only_suite_has_no_pass_rate(self) -> None:
        # it_support_v1 is judge-scored (no `expected` answers) -> Exec shows —.
        rows = [_jsonl_row()]
        run, results = _db_shape(
            rows, "20260612T150000Z_it_support_v1_gpt-5-chat.jsonl")
        db_row = eval_db_data._aggregate_db_run(run, results)
        self.assertNotIn("execution_pass_rate", db_row)


if __name__ == "__main__":
    unittest.main()
