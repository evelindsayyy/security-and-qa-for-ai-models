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
            with mock.patch.object(Path, "write_text", side_effect=PermissionError("denied")):
                msg = prepare_output_dir(target)
            self.assertIsNotNone(msg)
            self.assertIn("cannot write", msg)


if __name__ == "__main__":
    unittest.main()
