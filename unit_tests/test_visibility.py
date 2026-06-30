"""Visibility filter tests."""

from __future__ import annotations

import unittest

from dbutils.visibility import artifact_visible, visibility_clause


class TestVisibility(unittest.TestCase):
    def test_public_mode_sql(self):
        clause, params = visibility_clause("s", view_mode="public", user_id=None)
        self.assertIn("visibility = 'public'", clause)
        self.assertEqual(params, {})

    def test_private_mode_requires_user(self):
        clause, params = visibility_clause("s", view_mode="private", user_id="uid-1")
        self.assertIn("owner_user_id", clause)
        self.assertEqual(params["uid"], "uid-1")

    def test_artifact_visible_public(self):
        self.assertTrue(
            artifact_visible({"visibility": "public"}, view_mode="public", user_id=None)
        )

    def test_artifact_private_hidden_from_public_view(self):
        self.assertFalse(
            artifact_visible(
                {"visibility": "private", "owner_user_id": "u1"},
                view_mode="public",
                user_id=None,
            )
        )

    def test_private_mode_owner_only(self):
        clause, params = visibility_clause("s", view_mode="private", user_id="uid-1")
        self.assertNotIn("visibility = 'public'", clause)
        self.assertIn("visibility = 'private'", clause)

    def test_artifact_public_hidden_in_private_view(self):
        self.assertFalse(
            artifact_visible(
                {"visibility": "public"},
                view_mode="private",
                user_id="u1",
            )
        )

    def test_artifact_private_visible_to_owner(self):
        self.assertTrue(
            artifact_visible(
                {"visibility": "private", "owner_user_id": "u1"},
                view_mode="private",
                user_id="u1",
            )
        )


if __name__ == "__main__":
    unittest.main()
