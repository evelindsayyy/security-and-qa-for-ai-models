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


if __name__ == "__main__":
    unittest.main()
