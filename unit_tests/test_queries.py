"""
Tests for the efficacy read repository (evaluator/db/queries.py) — no database.

The repository's fetch_* functions take a DB-API connection, so a fake
connection (same trick as test_db_loader) exercises the real SQL-dispatch and
reconstruction logic offline. We also check the connection layer's no-DSN
short-circuit and that the dashboard actually routes through the repository.

Run from repo root:
  uv run python -m unittest unit_tests.test_queries -v
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from evaluator.db import queries  # noqa: E402

_DT = datetime(2026, 6, 12, 15, 0, 0, tzinfo=timezone.utc)
_ADAPT = {"task_suite_version": "it_support_v1"}


class _FakeCursor:
    """Returns canned rows by matching the SQL to a 'mode'. The real query
    text decides which dataset comes back, so the dispatch logic is tested."""

    def __init__(self, data: dict):
        self.data = data
        self._mode = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql: str, params=None):
        self.params = params
        # _RUNS_SQL also SELECTs the source_file column, so match the WHERE
        # clause specifically — not the bare word — to pick the detail query.
        if "WHERE r.source_file" in sql:    # _DETAIL_RUN_SQL
            self._mode = "detail_run"
        elif "WHERE eval_run_id" in sql:    # _DETAIL_RESULTS_SQL
            self._mode = "detail_results"
        elif "FROM public.eval_runs" in sql:  # _RUNS_SQL
            self._mode = "runs"
        elif "FROM public.eval_results" in sql:  # _RESULTS_SQL
            self._mode = "results"
        else:
            self._mode = None

    def fetchall(self):
        return list(self.data.get(self._mode, []))

    def fetchone(self):
        rows = self.data.get(self._mode, [])
        return rows[0] if rows else None


class _FakeConn:
    def __init__(self, data: dict):
        self._cur = _FakeCursor(data)

    def cursor(self):
        return self._cur

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _run_row(rid="rid1", source_file="f1.jsonl", model="gpt-5-chat"):
    return (rid, source_file, model, "Llama 4 Maverick", _DT, _ADAPT)


def _result_row(rid="rid1", task_id="q1", metric="judge_score"):
    detail = {"scores": {"accuracy": {"score": 5.0, "rationale": "ok"}},
              "dim_order": ["accuracy"], "candidate_response": "a"}
    return (rid, task_id, metric, 4.5, 1000, 200, 100, 0.001, False, False, detail)


class FetchRunsTest(unittest.TestCase):
    def test_groups_results_and_filters_non_judge_metrics(self) -> None:
        data = {
            "runs": [_run_row()],
            "results": [
                _result_row(task_id="q1", metric="judge_score"),
                _result_row(task_id="q2", metric="rouge_l"),  # filtered out
            ],
        }
        recs = queries.fetch_runs(_FakeConn(data))
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["run"]["gateway_model_id"], "gpt-5-chat")
        self.assertEqual([r["task_id"] for r in recs[0]["results"]], ["q1"])

    def test_skips_run_with_no_judge_results(self) -> None:
        data = {
            "runs": [_run_row(rid="a", source_file="a.jsonl"),
                     _run_row(rid="b", source_file="b.jsonl")],
            "results": [_result_row(rid="a", task_id="q1")],  # none for b
        }
        recs = queries.fetch_runs(_FakeConn(data))
        self.assertEqual([r["run"]["id"] for r in recs], ["a"])

    def test_skips_run_without_source_file(self) -> None:
        data = {
            "runs": [_run_row(rid="a", source_file=None)],
            "results": [_result_row(rid="a")],
        }
        self.assertEqual(queries.fetch_runs(_FakeConn(data)), [])


class FetchRunTest(unittest.TestCase):
    def test_returns_record_for_known_source_file(self) -> None:
        data = {
            "detail_run": [_run_row(source_file="f1.jsonl")],
            "detail_results": [(  # detail shape: 9 columns (no run_id/metric)
                "q1", 4.5, 1000, 200, 100, 0.001, False, False,
                {"scores": {"accuracy": {"score": 5.0, "rationale": "ok"}}},
            )],
        }
        rec = queries.fetch_run(_FakeConn(data), "f1.jsonl")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["run"]["source_file"], "f1.jsonl")
        self.assertEqual(len(rec["results"]), 1)
        self.assertEqual(rec["results"][0]["task_id"], "q1")

    def test_missing_run_returns_none(self) -> None:
        rec = queries.fetch_run(_FakeConn({"detail_run": []}), "nope.jsonl")
        self.assertIsNone(rec)


class FetchRunsForModelTest(unittest.TestCase):
    def test_filters_by_exact_model(self) -> None:
        data = {
            "runs": [_run_row(rid="a", source_file="a.jsonl", model="gpt-5-chat"),
                     _run_row(rid="b", source_file="b.jsonl", model="Llama 3.3")],
            "results": [_result_row(rid="a"), _result_row(rid="b", task_id="q1")],
        }
        recs = queries.fetch_runs_for_model(_FakeConn(data), "gpt-5-chat")
        self.assertEqual([r["run"]["id"] for r in recs], ["a"])


class ConnectionLayerTest(unittest.TestCase):
    def test_available_is_false_without_dsn_and_no_psycopg_import(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EFFICACY_DB_DSN", None)
            queries._avail_cache.update(checked_at=0.0, ok=False)
            self.assertFalse(queries.available())


class DashboardRoutesThroughRepositoryTest(unittest.TestCase):
    """get_runs_data_db must obtain its rows from queries.fetch_runs."""

    def test_get_runs_data_db_uses_fetch_runs(self) -> None:
        from frontend import eval_db_data

        record = {"run": {"id": "rid1", "source_file": "zzz_repo_test.jsonl",
                          "gateway_model_id": "gpt-5-chat",
                          "judge_model": "Llama 4 Maverick",
                          "started_at": _DT, "adaptation": _ADAPT},
                  "results": [{"task_id": "q1", "score": 4.5, "latency_ms": 1000,
                               "tokens_in": 200, "tokens_out": 100,
                               "cost_usd": 0.001, "candidate_failed": False,
                               "judge_failed": False,
                               "detail": {"scores": {"accuracy": {
                                   "score": 5.0, "rationale": "ok"}},
                                   "dim_order": ["accuracy"],
                                   "candidate_response": "a"}}]}

        class _NullCtx:
            def __enter__(self): return None
            def __exit__(self, *a): return False

        with mock.patch.object(eval_db_data.queries, "connect",
                               return_value=_NullCtx()), \
             mock.patch.object(eval_db_data.queries, "fetch_runs",
                               return_value=[record]) as fetch:
            data = eval_db_data.get_runs_data_db()

        fetch.assert_called_once()
        slugs = {r["slug"] for r in data["runs"]}
        self.assertIn("zzz_repo_test", slugs)


if __name__ == "__main__":
    unittest.main()
