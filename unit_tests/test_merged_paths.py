"""Tests for safety/merged_paths.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from safety.merged_paths import iter_merged_result_paths, merged_result_path


class MergedPathsTests(unittest.TestCase):
    def test_profile_scoped_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "gpt-4.1-mini" / "healthcare" / "merged_safety_result.json"
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")

            self.assertEqual(
                merged_result_path(root, "gpt-4.1-mini", "healthcare"),
                path,
            )
            rows = list(iter_merged_result_paths(root))
            self.assertEqual(rows, [(path, "gpt-4.1-mini", "healthcare")])

    def test_legacy_flat_layout_as_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "gpt-4.1-mini" / "merged_safety_result.json"
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")

            self.assertEqual(merged_result_path(root, "gpt-4.1-mini", "base"), path)
            rows = list(iter_merged_result_paths(root))
            self.assertEqual(rows, [(path, "gpt-4.1-mini", "base")])

    def test_profile_scoped_wins_over_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scoped = root / "gpt-4.1-mini" / "base" / "merged_safety_result.json"
            legacy = root / "gpt-4.1-mini" / "merged_safety_result.json"
            scoped.parent.mkdir(parents=True)
            legacy.parent.mkdir(parents=True, exist_ok=True)
            scoped.write_text("{}", encoding="utf-8")
            legacy.write_text("{}", encoding="utf-8")

            self.assertEqual(merged_result_path(root, "gpt-4.1-mini", "base"), scoped)
            rows = list(iter_merged_result_paths(root))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], scoped)


if __name__ == "__main__":
    unittest.main()
