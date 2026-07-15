"""Unit tests for scripts.dcc.vllm state helpers."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from scripts.dcc import vllm as vllm_mod


class VllmStateTest(unittest.TestCase):
    def test_write_and_read_state(self) -> None:
        with mock.patch.object(vllm_mod, "STATE_FILE", Path("/tmp/test-vllm-session.env")):
            vllm_mod.STATE_FILE.unlink(missing_ok=True)
            vllm_mod._write_state({"JOB_ID": "123", "PORT": "8000", "MODEL": "m"})
            data = vllm_mod._read_state()
            self.assertEqual(data["JOB_ID"], "123")
            self.assertEqual(data["PORT"], "8000")
            vllm_mod.STATE_FILE.unlink(missing_ok=True)

    def test_per_run_state_file(self) -> None:
        # A per-run path (as the orchestrator uses) round-trips independently of
        # the single-session default, and its parent dir is created on write.
        sf = Path("/tmp/test-vllm-jobs/run-xyz.env")
        sf.unlink(missing_ok=True)
        vllm_mod._write_state({"JOB_ID": "77", "PORT": "8001"}, sf)
        self.assertTrue(sf.is_file())
        data = vllm_mod._read_state(sf)
        self.assertEqual(data["JOB_ID"], "77")
        self.assertEqual(data["PORT"], "8001")
        sf.unlink(missing_ok=True)

    def test_resolve_state_file_prefers_session_arg(self) -> None:
        import argparse

        args = argparse.Namespace(session_file="/tmp/x/run.env")
        self.assertEqual(vllm_mod._resolve_state_file(args), Path("/tmp/x/run.env"))
        # falls back to the single-session default when unset
        args_none = argparse.Namespace(session_file=None)
        self.assertEqual(vllm_mod._resolve_state_file(args_none), vllm_mod.STATE_FILE)


class VllmWaitTest(unittest.TestCase):
    """cmd_wait must detect readiness from real squeue output.

    Regression: SQUEUE_FORMAT uses %T, so the state column is the LONG form
    ("RUNNING"), but the readiness guard used to compare against the short "R"
    and so never fired the /health check — the wait timed out on a healthy
    server. These tests feed the long form (what squeue actually prints) and a
    200 /health, and assert the wait succeeds.
    """

    def _args(self, sf: Path) -> "argparse.Namespace":
        import argparse
        return argparse.Namespace(
            session_file=str(sf), max_attempts=3, sleep_seconds=0,
        )

    def _run_wait(self, sf: Path, state_word: str, health_status: int) -> int:
        vllm_mod._write_state({"JOB_ID": "999", "PORT": "8000"}, sf)
        squeue_line = f"             999    {state_word}    dcc-gpu-01    dcc-gpu-01"
        fake_squeue = mock.Mock(stdout=squeue_line)
        health = mock.MagicMock()
        health.status = health_status
        health.__enter__.return_value = health
        with mock.patch.object(vllm_mod.subprocess, "run", return_value=fake_squeue), \
             mock.patch.object(vllm_mod.time, "sleep", return_value=None), \
             mock.patch.object(vllm_mod.urllib.request, "urlopen", return_value=health):
            return vllm_mod.cmd_wait(self._args(sf))

    def test_ready_on_long_form_running(self) -> None:
        # squeue's %T long form + a 200 /health -> ready (this is the bug case).
        sf = Path("/tmp/test-vllm-jobs/wait-long.env")
        sf.unlink(missing_ok=True)
        rc = self._run_wait(sf, "RUNNING", 200)
        self.assertEqual(rc, 0)
        self.assertEqual(vllm_mod._read_state(sf)["HOST"], "dcc-gpu-01")
        sf.unlink(missing_ok=True)

    def test_ready_on_short_form_running(self) -> None:
        # Still works if a future squeue format emits the short "R".
        sf = Path("/tmp/test-vllm-jobs/wait-short.env")
        sf.unlink(missing_ok=True)
        self.assertEqual(self._run_wait(sf, "R", 200), 0)
        sf.unlink(missing_ok=True)

    def test_times_out_when_health_never_200(self) -> None:
        # Running but /health keeps 503 -> exhausts attempts and returns 1.
        sf = Path("/tmp/test-vllm-jobs/wait-timeout.env")
        sf.unlink(missing_ok=True)
        self.assertEqual(self._run_wait(sf, "RUNNING", 503), 1)
        sf.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
