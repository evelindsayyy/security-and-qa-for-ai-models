"""
Tests for benchmarks/benchmark_progress.py and launch status polling.

  uv run python -m unittest unit_tests.test_benchmark_progress -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))

from benchmark_progress import init_progress, load_progress, tick, write_progress_stub  # noqa: E402


class BenchmarkProgressTest(unittest.TestCase):
    def test_write_and_tick(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.progress.json"
            write_progress_stub(
                path,
                benchmark_key="mmlu",
                benchmark_label="MMLU",
                model="gpt-5-mini",
                total=10,
                unit="questions",
            )
            with mock.patch.dict("os.environ", {"BENCHMARK_PROGRESS_PATH": str(path)}):
                init_progress(total=10, unit="questions")
                tick(message="Question 1/10")
                tick(message="Question 2/10")
            data = load_progress(path)
            self.assertEqual(data["progress"], 2)
            self.assertEqual(data["total"], 10)
            self.assertEqual(data["message"], "Question 2/10")


class BenchmarkLaunchStatusTest(unittest.TestCase):
    def test_get_status_reads_progress_while_running(self) -> None:
        from frontend import benchmark_launch as bl

        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            slug = "20260101T120000Z_consistency_gpt-5-mini"
            prog_path = results / f"{slug}.progress.json"
            prog_path.write_text(
                json.dumps(
                    {
                        "benchmark": "consistency",
                        "benchmark_label": "Consistency",
                        "model": "gpt-5-mini",
                        "progress": 3,
                        "total": 10,
                        "unit": "topics",
                        "message": "Topic 3/10",
                    }
                ),
                encoding="utf-8",
            )
            proc = mock.Mock()
            proc.poll.return_value = None
            with mock.patch.object(bl, "RESULTS_DIR", results), mock.patch.object(
                bl, "_RUNNING", {slug: proc}
            ), mock.patch.object(bl, "_output_path", return_value=None):
                status = bl.get_status(slug)
            self.assertEqual(status["status"], "running")
            self.assertEqual(status["progress"], 3)
            self.assertEqual(status["total"], 10)
            self.assertEqual(status["unit"], "topics")
            self.assertEqual(status["message"], "Topic 3/10")

    def test_get_status_reports_failed_after_restart_with_dead_lock(self) -> None:
        """Regression: a crashed run with no surviving _RUNNING entry (e.g.
        the frontend process restarted, or the entry was simply never there)
        and progress that never reached total must report "failed", not
        "running" forever — the UI has no other way to tell the difference
        between a live run and a permanently stuck one."""
        from frontend import benchmark_launch as bl

        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            slug = "20260101T120000Z_consistency_gpt-5-mini"
            prog_path = results / f"{slug}.progress.json"
            prog_path.write_text(
                json.dumps(
                    {
                        "benchmark": "consistency",
                        "benchmark_label": "Consistency",
                        "model": "gpt-5-mini",
                        "progress": 0,
                        "total": 5,
                        "unit": "topics",
                        "message": "Starting…",
                    }
                ),
                encoding="utf-8",
            )
            (results / f"{slug}.log").write_text("crashed on import\n", encoding="utf-8")
            # No lock file written at all -> run_lock.is_active() is False,
            # matching a process that has already exited and released it.
            with mock.patch.object(bl, "RESULTS_DIR", results), mock.patch.object(
                bl, "_RUNNING", {}
            ), mock.patch.object(bl, "_output_path", return_value=None):
                status = bl.get_status(slug)
            self.assertEqual(status["status"], "failed")
            self.assertIn("log", status)


if __name__ == "__main__":
    unittest.main()
