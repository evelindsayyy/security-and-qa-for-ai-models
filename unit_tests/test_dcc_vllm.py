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


if __name__ == "__main__":
    unittest.main()
