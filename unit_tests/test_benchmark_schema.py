"""Assert benchmark_schema.sql defines the expected benchmark_runs table."""

from __future__ import annotations

import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SCHEMA = _REPO / "benchmarks" / "db" / "benchmark_schema.sql"

_REQUIRED_COLUMNS = (
    "output_slug",
    "source_filename",
    "gateway_model_id",
    "benchmark_key",
    "headline_metric",
    "headline_value",
    "n_items",
    "metrics",
    "items",
    "run_params",
    "completed_at",
)


class BenchmarkSchemaTest(unittest.TestCase):
    def test_defines_benchmark_runs_table(self) -> None:
        sql = _SCHEMA.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS public.benchmark_runs", sql)
        self.assertIn("UNIQUE (output_slug)", sql)
        for col in _REQUIRED_COLUMNS:
            with self.subTest(column=col):
                self.assertIn(col, sql)


if __name__ == "__main__":
    unittest.main()
