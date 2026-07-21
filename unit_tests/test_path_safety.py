"""
Tests for frontend/path_safety.py — slug traversal guards.

  uv run python -m unittest unit_tests.test_path_safety -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from frontend.path_safety import is_safe_slug, resolves_inside


class IsSafeSlugTest(unittest.TestCase):
    def test_valid_stems(self) -> None:
        for slug in (
            "gpt2",
            "20990101T000000Z_it_support_v1_x",
            "BAAI--bge-small-en-v1.5",
            "gpt-5.5",
        ):
            with self.subTest(slug=slug):
                self.assertTrue(is_safe_slug(slug))

    def test_rejects_traversal_and_separators(self) -> None:
        for slug in ("..", "../etc", "foo/bar", "foo\\bar", ".", "..."):
            with self.subTest(slug=slug):
                self.assertFalse(is_safe_slug(slug))

    def test_rejects_empty(self) -> None:
        self.assertFalse(is_safe_slug(""))
        self.assertFalse(is_safe_slug("   "))

    def test_rejects_trailing_newline(self) -> None:
        """`$` (unlike `\\Z`) matches just before a trailing newline, so a
        naive regex would accept "good\\n" as a safe slug."""
        for slug in ("good\n", "gpt-5.5\n", "..\n"):
            with self.subTest(slug=slug):
                self.assertFalse(is_safe_slug(slug))


class ResolvesInsideTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_child_path_is_inside(self) -> None:
        child = self.base / "gpt2" / "scan_result.json"
        child.parent.mkdir(parents=True)
        child.write_text("{}", encoding="utf-8")
        self.assertTrue(resolves_inside(self.base, child))

    def test_escape_via_dotdot_is_outside(self) -> None:
        outside = self.base / ".." / "outside.txt"
        self.assertFalse(resolves_inside(self.base, outside))
