"""
Unit tests for the --load-db post-run sync (runner._maybe_load_db).

The contract: syncing results into Postgres is a best-effort PROJECTION.
The JSONL file is the source of truth and the run has already succeeded by
the time the sync runs, so a sync problem must NEVER raise — it logs to
stderr and returns. These tests pin that no-raise behavior across the
failure modes (no DSN, unparseable file, DB layer throwing) without ever
touching a real database.

Run from repo root:
  uv run python -m unittest unit_tests.test_runner_load_db -v
"""

from __future__ import annotations

import io
import contextlib
import sys
import unittest
from pathlib import Path
from unittest import mock

_EVALUATOR = Path(__file__).resolve().parent.parent / "evaluator"
sys.path.insert(0, str(_EVALUATOR))

import runner  # noqa: E402


def _capture_stderr(fn, *args, **kwargs) -> str:
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        fn(*args, **kwargs)
    return err.getvalue()


class TestMaybeLoadDbNoRaise(unittest.TestCase):
    def setUp(self):
        # Ensure no ambient DSN leaks in from the environment.
        self._patches = [
            mock.patch.dict("os.environ", {}, clear=False),
        ]
        for p in self._patches:
            p.start()
        for k in ("EFFICACY_DB_DSN", "DATABASE_URL"):
            runner.os.environ.pop(k, None)

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_no_dsn_warns_and_returns(self):
        msg = _capture_stderr(runner._maybe_load_db, Path("/tmp/x.jsonl"), None)
        self.assertIn("no DSN", msg)

    def test_unparseable_file_warns_and_returns(self):
        # DSN present (so we get past the DSN guard), but load_file returns
        # None -> warn, no raise. Patch the lazily-imported symbol.
        fake_mod = mock.MagicMock()
        fake_mod.load_file.return_value = None
        with mock.patch.dict("sys.modules", {"db.load_results": fake_mod}):
            msg = _capture_stderr(
                runner._maybe_load_db, Path("/tmp/x.jsonl"), "host=fake dbname=fake"
            )
        self.assertIn("could not parse", msg)
        fake_mod.apply_to_db.assert_not_called()

    def test_db_layer_exception_is_swallowed(self):
        fake_mod = mock.MagicMock()
        fake_mod.load_file.return_value = ({}, {}, [])
        fake_mod.apply_to_db.side_effect = RuntimeError("connection refused")
        with mock.patch.dict("sys.modules", {"db.load_results": fake_mod}):
            msg = _capture_stderr(
                runner._maybe_load_db, Path("/tmp/x.jsonl"), "host=fake dbname=fake"
            )
        # The run survives; the warning tells the user how to recover.
        self.assertIn("--load-db failed", msg)
        self.assertIn("load_results.py --apply", msg)

    def test_success_path_calls_apply_and_logs(self):
        fake_mod = mock.MagicMock()
        parsed = ({"suite": 1}, {"run": 1}, [{"r": 1}])
        fake_mod.load_file.return_value = parsed
        out = io.StringIO()
        with mock.patch.dict("sys.modules", {"db.load_results": fake_mod}), \
                contextlib.redirect_stdout(out):
            runner._maybe_load_db(Path("/tmp/run.jsonl"), "host=fake dbname=fake")
        fake_mod.apply_to_db.assert_called_once_with("host=fake dbname=fake", [parsed])
        self.assertIn("synced run.jsonl", out.getvalue())


if __name__ == "__main__":
    unittest.main()
