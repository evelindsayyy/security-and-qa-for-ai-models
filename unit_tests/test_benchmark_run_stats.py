"""
Tests for benchmarks/benchmark_run_stats.py

  uv run python -m unittest unit_tests.test_benchmark_run_stats -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.benchmark_run_stats import (
    RunStatsCollector,
    attach_run_stats,
    load_stats_sidecar,
    merge_wall_time,
    run_with_stats,
    write_stats_sidecar,
)


class RunStatsCollectorTest(unittest.TestCase):
    def test_records_latency_and_tokens(self) -> None:
        c = RunStatsCollector()
        c.record_success(100.0, {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
        c.record_success(200.0, {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30})
        c.record_failure()
        out = c.to_dict()
        self.assertEqual(out["api_calls"], 2)
        self.assertEqual(out["api_calls_failed"], 1)
        self.assertEqual(out["tokens"]["total"], 45)
        self.assertEqual(out["latency_ms"]["mean"], 150.0)
        self.assertEqual(out["latency_ms"]["p50"], 100.0)

    def test_empty_tokens_are_none(self) -> None:
        c = RunStatsCollector()
        c.record_success(10.0, None)
        tokens = c.to_dict()["tokens"]
        self.assertIsNone(tokens["total"])

    def test_merge_wall_time(self) -> None:
        block: dict = {}
        merge_wall_time(block, 12.345)
        self.assertEqual(block["run_stats"]["wall_time_sec"], 12.35)


class RunWithStatsTest(unittest.TestCase):
    def test_context_manager_attaches_to_summary(self) -> None:
        with run_with_stats() as stats:
            stats.record_success(42.0, {"total_tokens": 7})
            summary: dict = {}
            attach_run_stats(summary)
        self.assertEqual(summary["run_stats"]["api_calls"], 1)
        self.assertEqual(summary["run_stats"]["tokens"]["total"], 7)

    def test_write_stats_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.stats.json"
            with run_with_stats() as stats:
                stats.record_success(1.0, None)
                write_stats_sidecar(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["api_calls"], 1)

    def test_load_stats_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stem.jsonl"
            sidecar = Path(tmp) / "stem.stats.json"
            sidecar.write_text('{"api_calls": 3}', encoding="utf-8")
            self.assertEqual(load_stats_sidecar(path)["api_calls"], 3)


if __name__ == "__main__":
    unittest.main()
