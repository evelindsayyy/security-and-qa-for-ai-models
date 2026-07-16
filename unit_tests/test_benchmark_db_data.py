"""
Tests for the Postgres read path (frontend/benchmark_db_data.py) — no database.

Run from repo root:
  uv run python -m unittest unit_tests.test_benchmark_db_data -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import benchmark_data, benchmark_db_data


def _db_row(**overrides):
    base = {
        "output_slug": "20260608T095540Z_truthfulqa_test",
        "source_filename": "20260608T095540Z_truthfulqa_test.json",
        "gateway_model_id": "GPT 4.1 Mini",
        "benchmark_key": "truthfulqa",
        "headline_metric": "accuracy",
        "headline_value": 0.9,
        "n_items": 10,
        "metrics": {
            "correct": 9,
            "total_evaluated": 10,
            "summary": {"accuracy": 0.9, "correct": 9, "total_evaluated": 10},
        },
        "completed_at": "2026-06-08T09:55:40+00:00",
    }
    base.update(overrides)
    return (
        base["output_slug"],
        base["source_filename"],
        base["gateway_model_id"],
        base["benchmark_key"],
        base["headline_metric"],
        base["headline_value"],
        base["n_items"],
        base["metrics"],
        base["completed_at"],
        base.get("config_json"),
    )


class DbRowMatchesFileRowTest(unittest.TestCase):
    def test_truthfulqa_list_row_keys(self) -> None:
        data = {
            "model": "GPT 4.1 Mini",
            "timestamp": "20260608T095540Z",
            "metrics": {"accuracy": 0.9, "correct": 9, "total_evaluated": 10},
            "responses": [{"question": "q1"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260608T095540Z_truthfulqa_test.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            file_row = benchmark_data._summarize_truthfulqa(path, data)

        db_row = benchmark_db_data._summarize_db_run(_db_row())
        for key in ("slug", "kind", "kind_label", "model", "headline_metric", "n"):
            self.assertEqual(file_row[key], db_row[key], f"mismatch on {key!r}")
        self.assertAlmostEqual(file_row["headline_value"], db_row["headline_value"])


def _detail_db_row(**overrides):
    """12-column row matching ``_DETAIL_SQL`` (list row + items + run_params)."""
    list_row = _db_row(**{k: v for k, v in overrides.items() if k not in ("items", "run_params")})
    items = overrides.get("items", [{"topic": "t1", "f1": 0.8}])
    run_params = overrides.get("run_params", {"sample": 5})
    # list: slug, file, model, key, metric, value, n, metrics, completed_at, config
    return list_row[:8] + (items, run_params) + list_row[8:]


class DetailSqlShapeTest(unittest.TestCase):
    def test_detail_sql_selects_config_json(self) -> None:
        # Must match _build_detail_db's 12-field unpack (was missing and 404'd).
        self.assertIn("config_json", benchmark_db_data._DETAIL_SQL)
        self.assertRegex(
            benchmark_db_data._DETAIL_SQL,
            r"completed_at,\s*config_json",
        )

    def test_build_detail_db_accepts_twelve_column_row(self) -> None:
        row = _detail_db_row(
            output_slug="20260701T234340Z_consistency_GPT-4.1-Mini",
            source_filename="20260701T234340Z_consistency_GPT-4.1-Mini.json",
            gateway_model_id="GPT 4.1 Mini",
            benchmark_key="consistency",
            headline_metric="mean_f1",
            headline_value=0.817,
            n_items=5,
            metrics={"mean_f1_overall": 0.817},
            completed_at="2026-07-01T23:43:40+00:00",
        )
        detail = benchmark_db_data._build_detail_db(row)
        self.assertEqual(detail["slug"], "20260701T234340Z_consistency_GPT-4.1-Mini")
        self.assertEqual(detail["kind"], "consistency")
        self.assertEqual(detail["kind_label"], "Consistency")
        self.assertEqual(detail["model"], "GPT 4.1 Mini")
        self.assertAlmostEqual(detail["headline_value"], 0.817)
        self.assertEqual(detail["run_params"]["sample"], 5)
        self.assertEqual(len(detail["questions"]), 1)
        self.assertEqual(detail["raw_row_count"], 1)
    def test_no_dsn_means_unavailable(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("POSTGRES_DSN", None)
            os.environ.pop("DATABASE_URL", None)
            benchmark_db_data._avail_cache.update(checked_at=0.0, ok=False)
            self.assertFalse(benchmark_db_data.available())

    def test_dispatcher_serves_files_when_db_unavailable(self) -> None:
        with mock.patch.object(benchmark_db_data, "available", return_value=False):
            data = benchmark_data.get_benchmarks_data()
        self.assertIn("has_runs", data)

    def test_detail_falls_back_to_files_when_slug_not_in_db(self) -> None:
        with mock.patch.object(benchmark_db_data, "available", return_value=True), mock.patch.object(
            benchmark_db_data, "get_benchmark_detail_db", return_value=None
        ), mock.patch.object(
            benchmark_data, "_get_benchmark_detail_files", return_value={"slug": "from-files"}
        ):
            detail = benchmark_data.get_benchmark_detail("some-slug")
        self.assertEqual(detail["slug"], "from-files")

    def test_dispatcher_survives_db_exceptions(self) -> None:
        with mock.patch.object(
            benchmark_db_data, "available", side_effect=RuntimeError("db down")
        ):
            data = benchmark_data.get_benchmarks_data()
        self.assertIn("has_runs", data)


if __name__ == "__main__":
    unittest.main()
