"""Tests for frontend.run_paths — pure visibility/owner path scoping."""

from __future__ import annotations

import unittest
from pathlib import Path

from frontend.run_paths import inflight_scope_key, scoped_dir


class ScopedDirTest(unittest.TestCase):
    def test_public_is_unchanged_base_path(self) -> None:
        base = Path("scanner/output/gpt2")
        self.assertEqual(scoped_dir(base, visibility="public", owner_user_id=None), base)
        self.assertEqual(scoped_dir(base, visibility="public", owner_user_id="u1"), base)

    def test_private_is_a_sibling_of_the_slug_dir_not_nested_inside_it(self) -> None:
        # Nesting private inside the slug dir would put it in the blast
        # radius of a public rerun's wipe-and-recreate of that slug dir.
        base = Path("scanner/output/gpt2")
        scoped = scoped_dir(base, visibility="private", owner_user_id="u1")
        self.assertEqual(scoped, Path("scanner/output/.private/u1/gpt2"))
        self.assertFalse(str(scoped).startswith(str(base) + "/"))

    def test_private_without_owner_raises(self) -> None:
        base = Path("scanner/output/gpt2")
        with self.assertRaises(ValueError):
            scoped_dir(base, visibility="private", owner_user_id=None)

    def test_two_owners_produce_distinct_paths(self) -> None:
        base = Path("scanner/output/gpt2")
        a = scoped_dir(base, visibility="private", owner_user_id="u1")
        b = scoped_dir(base, visibility="private", owner_user_id="u2")
        self.assertNotEqual(a, b)

    def test_safety_profile_scoped_base_nests_private_inside_the_slug_dir(self) -> None:
        # Safety's wipe-on-restart is scoped to <slug>/<profile>/ (not the
        # whole <slug>/ tree), so "private" only needs to be a sibling of
        # the profile dirs here, not of the slug dirs — this stays outside
        # the blast radius of a re-run's wipe either way.
        base = Path("safety/output/gpt-4.1-mini/base")
        scoped = scoped_dir(base, visibility="private", owner_user_id="u1")
        self.assertEqual(scoped, Path("safety/output/gpt-4.1-mini/.private/u1/base"))

    def test_safety_garak_slug_scoped_base_resolves_as_sibling_of_all_slugs(self) -> None:
        # Garak's wipe-on-restart IS scoped to the whole <slug>/ tree (no
        # profile level), so its private data must be a sibling of every
        # slug directory, not nested inside one — same shape as scanner.
        base = Path("safety/garak/output/gpt-4.1-mini")
        scoped = scoped_dir(base, visibility="private", owner_user_id="u1")
        self.assertEqual(scoped, Path("safety/garak/output/.private/u1/gpt-4.1-mini"))


class InflightScopeKeyTest(unittest.TestCase):
    def test_public_ignores_owner(self) -> None:
        self.assertEqual(inflight_scope_key("public", "u1"), ("public", None))
        self.assertEqual(inflight_scope_key("public", None), ("public", None))

    def test_private_includes_owner(self) -> None:
        self.assertEqual(inflight_scope_key("private", "u1"), ("private", "u1"))

    def test_different_owners_yield_different_keys(self) -> None:
        self.assertNotEqual(inflight_scope_key("private", "u1"), inflight_scope_key("private", "u2"))


if __name__ == "__main__":
    unittest.main()
