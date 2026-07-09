"""Tests for dbutils/fs_safe.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dbutils import fs_safe


class FsSafeTest(unittest.TestCase):
    def test_is_file_true_for_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.txt"
            path.write_text("x", encoding="utf-8")
            self.assertTrue(fs_safe.is_file(path))

    def test_is_file_false_for_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(fs_safe.is_file(Path(tmp) / "missing"))

    def test_is_file_false_on_permission_error(self) -> None:
        with mock.patch.object(Path, "is_file", side_effect=PermissionError("denied")):
            self.assertFalse(fs_safe.is_file(Path("/bad/path")))

    def test_is_dir_false_on_permission_error(self) -> None:
        with mock.patch.object(Path, "is_dir", side_effect=PermissionError("denied")):
            self.assertFalse(fs_safe.is_dir(Path("/bad/path")))

    def test_iterdir_skips_unreadable_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = root / "good"
            bad = root / "bad"
            good.mkdir()
            bad.mkdir()
            (good / "scan_result.json").write_text("{}", encoding="utf-8")

            orig_stat = Path.stat

            def patched_stat(self, *args, **kwargs):
                if self.name == "bad":
                    raise PermissionError("denied")
                return orig_stat(self, *args, **kwargs)

            with mock.patch.object(Path, "stat", patched_stat):
                names = {p.name for p in fs_safe.iterdir(root)}
            self.assertEqual(names, {"good"})

    def test_glob_skips_unreadable_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = root / "good.json"
            bad = root / "bad.json"
            good.write_text("{}", encoding="utf-8")
            bad.write_text("{}", encoding="utf-8")

            orig_stat = Path.stat

            def patched_stat(self, *args, **kwargs):
                if self.name == "bad.json":
                    raise PermissionError("denied")
                return orig_stat(self, *args, **kwargs)

            with mock.patch.object(Path, "stat", patched_stat):
                names = {p.name for p in fs_safe.glob(root, "*.json")}
            self.assertEqual(names, {"good.json"})

    def test_iterdir_empty_on_permission_error_at_root(self) -> None:
        with mock.patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
            self.assertEqual(list(fs_safe.iterdir(Path("/bad"))), [])


if __name__ == "__main__":
    unittest.main()
