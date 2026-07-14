"""
Tests for frontend/launch_registry.py — the shared in-flight-combo liveness
check used by every pillar's ``start_run()``.

  uv run python -m unittest unit_tests.test_launch_registry -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frontend.launch_registry import check_inflight_combo, count_inflight, list_inflight_jobs


class _FakeProc:
    def __init__(self, alive: bool) -> None:
        self._alive = alive

    def poll(self):
        return None if self._alive else 0


class CheckInflightComboTest(unittest.TestCase):
    def test_returns_key_when_process_alive(self) -> None:
        running = {"job-1": _FakeProc(alive=True)}
        inflight = {("a", "b"): "job-1"}
        self.assertEqual(check_inflight_combo(running, inflight, ("a", "b")), "job-1")

    def test_returns_none_when_combo_not_tracked(self) -> None:
        self.assertIsNone(check_inflight_combo({}, {}, ("a", "b")))

    def test_returns_none_when_process_has_exited(self) -> None:
        running = {"job-1": _FakeProc(alive=False)}
        inflight = {("a", "b"): "job-1"}
        self.assertIsNone(check_inflight_combo(running, inflight, ("a", "b")))

    def test_returns_none_when_process_missing_from_registry(self) -> None:
        inflight = {("a", "b"): "job-1"}
        self.assertIsNone(check_inflight_combo({}, inflight, ("a", "b")))


class ListInflightJobsTest(unittest.TestCase):
    def test_aggregates_pillar_slugs(self) -> None:
        with (
            mock.patch(
                "frontend.scan_launch.inflight_scan_slugs",
                return_value={"org__model"},
            ),
            mock.patch(
                "frontend.safety_launch.inflight_safety_keys",
                return_value={"org__model/chatbot"},
            ),
            mock.patch(
                "frontend.eval_launch.inflight_eval_slugs",
                return_value={"suite_model_ts"},
            ),
            mock.patch(
                "frontend.benchmark_launch.inflight_benchmark_slugs",
                return_value={"mmlu_model_ts"},
            ),
        ):
            jobs = list_inflight_jobs()
            self.assertEqual(len(jobs), 4)
            self.assertEqual(count_inflight(), 4)
        pillars = {j["pillar"] for j in jobs}
        self.assertEqual(pillars, {"scan", "safety", "eval", "benchmark"})
        urls = {j["url"] for j in jobs}
        self.assertIn("/scans/org__model?status=running", urls)
        self.assertIn("/safety/org__model/chatbot?status=running", urls)
        self.assertIn("/eval-run/suite_model_ts?status=running", urls)
        self.assertIn("/benchmarks/mmlu_model_ts?status=running", urls)


class FrontendOrphanLockTest(unittest.TestCase):
    def test_frontend_lock_stays_active_with_fresh_log_after_pid_dies(self) -> None:
        from dbutils import run_lock

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            lock = out / "run.lock"
            log = out / "scan_run.log"
            log.write_text("still running\n", encoding="utf-8")
            lock.write_text(
                json.dumps(
                    {
                        "pid": 99999999,
                        "started_at": "2020-01-01T00:00:00Z",
                        "source": run_lock.FRONTEND_SOURCE,
                        "command": "scan",
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(run_lock.is_active(lock))

    def test_eval_jsonl_alone_is_not_completion(self) -> None:
        from dbutils import run_lock

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            lock = out / "run.run.lock"
            log = out / "run.log"
            jsonl = out / "run.jsonl"
            log.write_text("evaluating\n", encoding="utf-8")
            jsonl.write_text('{"overall": 4.0}\n', encoding="utf-8")
            lock.write_text(
                json.dumps(
                    {
                        "pid": 99999999,
                        "started_at": "2020-01-01T00:00:00Z",
                        "source": run_lock.FRONTEND_SOURCE,
                        "command": "eval",
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(run_lock.is_active(lock))


if __name__ == "__main__":
    unittest.main()
