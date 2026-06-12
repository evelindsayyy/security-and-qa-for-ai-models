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
    def test_no_dsn_means_unavailable_without_importing_psycopg(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EFFICACY_DB_DSN", None)
            # reset the TTL cache so this test is deterministic
            eval_db_data._avail_cache.update(checked_at=0.0, ok=False)
            self.assertFalse(eval_db_data.available())

    def test_dispatcher_serves_files_when_db_unavailable(self) -> None:
        with mock.patch.object(eval_db_data, "available", return_value=False):
            data = eval_run_data.get_runs_data()
        self.assertIn("has_runs", data)  # file-path contract served

    def test_detail_dispatcher_falls_back_when_slug_not_in_db(self) -> None:
        sentinel = {"slug": "from-files"}
        with mock.patch.object(eval_db_data, "available", return_value=True), \
             mock.patch.object(eval_db_data, "get_run_detail_db",
                               return_value=None), \
             mock.patch.object(eval_run_data, "_get_run_detail_files",
                               return_value=sentinel):
            detail = eval_run_data.get_run_detail("some-slug")
        self.assertIs(detail, sentinel)

    def test_dispatcher_survives_db_exceptions(self) -> None:
        with mock.patch.object(eval_db_data, "available",
                               side_effect=RuntimeError("db exploded")):
            data = eval_run_data.get_runs_data()
        self.assertIn("has_runs", data)  # silent fallback, never a 500


if __name__ == "__main__":
    unittest.main()
