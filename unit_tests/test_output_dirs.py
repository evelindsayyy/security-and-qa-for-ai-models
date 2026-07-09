"""Tests for frontend/output_dirs.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frontend.output_dirs import prepare_output_dir


class PrepareOutputDirTest(unittest.TestCase):
    def test_creates_writable_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "slug"
            self.assertIsNone(prepare_output_dir(target))
            self.assertTrue(target.is_dir())

    def test_returns_message_when_not_writable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "slug"
            target.mkdir()
            with mock.patch.object(Path, "write_text", side_effect=PermissionError("denied")), \
                 mock.patch("frontend.output_dirs._docker_repair_permissions", return_value=False):
                msg = prepare_output_dir(target)
            self.assertIsNotNone(msg)
            self.assertIn("cannot write", msg)

    def test_error_message_uses_repo_relative_mount(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            target = repo / "scanner" / "output" / "TinyLlama--slug"
            target.mkdir(parents=True)
            with mock.patch.object(Path, "write_text", side_effect=PermissionError("denied")), \
                 mock.patch("frontend.output_dirs._docker_repair_permissions", return_value=False), \
                 mock.patch("frontend.output_dirs.REPO_ROOT", repo):
                msg = prepare_output_dir(target, repo_root=repo)
            self.assertIsNotNone(msg)
            self.assertIn('$PWD/scanner/output', msg)
            self.assertIn("/out/TinyLlama--slug", msg)

    def test_repair_and_retry_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "scanner" / "output" / "slug"
            target.mkdir(parents=True)
            calls = {"n": 0}
            orig_write = Path.write_text

            def patched_write(self, *args, **kwargs):
                if self.name == ".write_probe" and calls["n"] == 0:
                    calls["n"] += 1
                    raise PermissionError("denied")
                return orig_write(self, *args, **kwargs)

            with mock.patch.object(Path, "write_text", patched_write), \
                 mock.patch("frontend.output_dirs._docker_repair_permissions", return_value=True):
                msg = prepare_output_dir(target)
            self.assertIsNone(msg)
            self.assertTrue(target.is_dir())


if __name__ == "__main__":
    unittest.main()
