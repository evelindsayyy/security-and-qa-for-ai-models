"""
Tests for api.ingest — orchestrator calls pillar loaders; dry-run needs no DSN.

Run from repo root:
  uv run python -m unittest unit_tests.test_api_ingest -v
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from unittest import mock

from api import ingest as api_ingest


@dataclass
class FakeIngestResult:
    count: int
    label: str = "item(s)"


def _patch_run(module: str, count: int):
    return mock.patch(
        module,
        return_value=FakeIngestResult(count=count),
    )


class OrchestratorTest(unittest.TestCase):
    def test_default_runs_all_pillars_dry_run(self) -> None:
        with _patch_run("scanner.db.load_scans.run_ingest", 2) as scan_run, \
             _patch_run("safety.db.load_safety.run_ingest", 1) as safety_run, \
             _patch_run("evaluator.db.load_results.run_ingest", 3) as eval_run, \
             _patch_run("benchmarks.db.load_benchmarks.run_ingest", 0) as bm_run, \
             _patch_run("personality.db.load_personality.run_ingest", 0) as pers_run:
            rc = api_ingest.main([])

        self.assertEqual(rc, 0)
        scan_run.assert_called_once()
        safety_run.assert_called_once()
        eval_run.assert_called_once()
        bm_run.assert_called_once()
        pers_run.assert_called_once()
        for runner in (scan_run, safety_run, eval_run, bm_run, pers_run):
            self.assertFalse(runner.call_args.kwargs["apply"])

    def test_scan_only_calls_one_pillar(self) -> None:
        with _patch_run("scanner.db.load_scans.run_ingest", 1) as scan_run, \
             _patch_run("safety.db.load_safety.run_ingest", 0) as safety_run, \
             _patch_run("evaluator.db.load_results.run_ingest", 0) as eval_run, \
             _patch_run("benchmarks.db.load_benchmarks.run_ingest", 0) as bm_run, \
             _patch_run("personality.db.load_personality.run_ingest", 0) as pers_run:
            rc = api_ingest.main(["--scan"])

        self.assertEqual(rc, 0)
        scan_run.assert_called_once()
        safety_run.assert_not_called()
        eval_run.assert_not_called()
        bm_run.assert_not_called()
        pers_run.assert_not_called()

    def test_strict_exits_nonzero_when_pillar_empty(self) -> None:
        with _patch_run("scanner.db.load_scans.run_ingest", 0), \
             _patch_run("safety.db.load_safety.run_ingest", 1), \
             _patch_run("evaluator.db.load_results.run_ingest", 1), \
             _patch_run("benchmarks.db.load_benchmarks.run_ingest", 1), \
             _patch_run("personality.db.load_personality.run_ingest", 1):
            rc = api_ingest.main(["--strict"])

        self.assertEqual(rc, 1)

    def test_apply_passes_dsn(self) -> None:
        with _patch_run("scanner.db.load_scans.run_ingest", 1) as scan_run, \
             _patch_run("safety.db.load_safety.run_ingest", 1), \
             _patch_run("evaluator.db.load_results.run_ingest", 1), \
             _patch_run("benchmarks.db.load_benchmarks.run_ingest", 1), \
             _patch_run("personality.db.load_personality.run_ingest", 1):
            rc = api_ingest.main(["--apply", "--dsn", "postgres://local/test"])

        self.assertEqual(rc, 0)
        self.assertTrue(scan_run.call_args.kwargs["apply"])
        self.assertEqual(scan_run.call_args.kwargs["dsn"], "postgres://local/test")

    def test_bootstrap_command_runs_all_pillars(self) -> None:
        with _patch_run("scanner.db.load_scans.run_ingest", 1) as scan_run, \
             _patch_run("safety.db.load_safety.run_ingest", 2) as safety_run, \
             _patch_run("evaluator.db.load_results.run_ingest", 3) as eval_run, \
             _patch_run("benchmarks.db.load_benchmarks.run_ingest", 4) as bm_run, \
             _patch_run("personality.db.load_personality.run_ingest", 5) as pers_run:
            rc = api_ingest.main(["bootstrap", "--apply", "--dsn", "postgres://local/test"])

        self.assertEqual(rc, 0)
        scan_run.assert_called_once()
        safety_run.assert_called_once()
        eval_run.assert_called_once()
        bm_run.assert_called_once()
        pers_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
