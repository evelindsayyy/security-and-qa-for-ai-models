"""
Tests for scanner/paths.py slug helpers.

  uv run python -m unittest unit_tests.test_scanner_paths -v
"""

from __future__ import annotations

import unittest

from scanner.paths import safe_dir_name, slug_to_model_id


class PathsTest(unittest.TestCase):
    def test_safe_dir_name_replaces_slash(self) -> None:
        self.assertEqual(safe_dir_name("BAAI/bge-small-en-v1.5"), "BAAI--bge-small-en-v1.5")

    def test_slug_round_trip(self) -> None:
        slug = safe_dir_name("org/my-model")
        self.assertEqual(slug_to_model_id(slug), "org/my-model")

    def test_simple_model_unchanged(self) -> None:
        self.assertEqual(safe_dir_name("gpt2"), "gpt2")
        self.assertEqual(slug_to_model_id("gpt2"), "gpt2")


if __name__ == "__main__":
    unittest.main()
