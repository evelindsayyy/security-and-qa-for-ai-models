"""
Unit tests for dbutils.post_run — best-effort auto-ingest after pillar runs.

Run from repo root:
  uv run python -m unittest unit_tests.test_post_run -v
"""

from __future__ import annotations

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from dbutils import post_run


def _capture_stderr(fn, *args, **kwargs) -> str:
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        fn(*args, **kwargs)
    return err.getvalue()


class ShouldAutoSyncTest(unittest.TestCase):
    def test_disabled_when_auto_ingest_zero(self) -> None:
        with mock.patch.dict(os.environ, {"AUTO_INGEST": "0", "POSTGRES_DSN": "x"}):
            self.assertFalse(post_run.should_auto_sync())

    def test_enabled_when_dsn_set(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "AUTO_INGEST"}
        env["POSTGRES_DSN"] = "postgresql://u:p@h/db"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(post_run.should_auto_sync())


class MaybeSyncArtifactTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for key in ("POSTGRES_DSN", "DATABASE_URL", "EFFICACY_DB_DSN", "AUTO_INGEST"):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        self._env.stop()

    def test_skips_when_auto_ingest_disabled(self) -> None:
        with mock.patch.object(post_run, "sync_artifact") as sync:
            post_run.maybe_sync_artifact(Path("/tmp/x.jsonl"), "eval")
        sync.assert_not_called()

    def test_no_dsn_warns_and_returns(self) -> None:
        with mock.patch.object(post_run, "should_auto_sync", return_value=True), \
             mock.patch.object(post_run, "_resolve_dsn", return_value=None), \
             mock.patch.object(Path, "is_file", return_value=True):
            msg = _capture_stderr(post_run.maybe_sync_artifact, Path("/tmp/x.jsonl"), "eval")
        self.assertIn("no DSN", msg)

    def test_unparseable_file_warns(self) -> None:
        with mock.patch.object(post_run, "should_auto_sync", return_value=True), \
             mock.patch.object(post_run, "_resolve_dsn", return_value="postgresql://u:p@h/db"), \
             mock.patch.object(post_run, "psycopg_available", return_value=True), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(post_run, "sync_artifact", side_effect=ValueError("could not parse x.jsonl")):
            msg = _capture_stderr(post_run.maybe_sync_artifact, Path("/tmp/x.jsonl"), "eval")
        self.assertIn("could not parse", msg)

    def test_db_layer_exception_is_swallowed(self) -> None:
        with mock.patch.object(post_run, "should_auto_sync", return_value=True), \
             mock.patch.object(post_run, "_resolve_dsn", return_value="postgresql://u:p@h/db"), \
             mock.patch.object(post_run, "psycopg_available", return_value=True), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(post_run, "sync_artifact", side_effect=RuntimeError("connection refused")):
            msg = _capture_stderr(post_run.maybe_sync_artifact, Path("/tmp/run.jsonl"), "eval")
        self.assertIn("auto-ingest failed", msg)
        self.assertIn("api.ingest", msg)

    def test_skips_when_psycopg_not_installed(self) -> None:
        with mock.patch.object(post_run, "should_auto_sync", return_value=True), \
             mock.patch.object(post_run, "_resolve_dsn", return_value="postgresql://u:p@h/db"), \
             mock.patch.object(post_run, "psycopg_available", return_value=False), \
             mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(post_run, "sync_artifact") as sync:
            msg = _capture_stderr(post_run.maybe_sync_artifact, Path("/tmp/run.jsonl"), "eval")
        sync.assert_not_called()
        self.assertIn("psycopg not installed", msg)

    def test_success_path_logs(self) -> None:
        path = Path("/tmp/run.jsonl")
        with mock.patch.object(post_run, "should_auto_sync", return_value=True), \
             mock.patch.object(post_run, "_resolve_dsn", return_value="postgresql://u:p@h/db"), \
             mock.patch.object(post_run, "psycopg_available", return_value=True), \
             mock.patch.object(post_run, "sync_artifact") as sync, \
             mock.patch.object(Path, "is_file", return_value=True):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                post_run.maybe_sync_artifact(path, "eval")
        sync.assert_called_once_with(path, "eval", dsn="postgresql://u:p@h/db")
        self.assertIn("synced run.jsonl", out.getvalue())


if __name__ == "__main__":
    unittest.main()
