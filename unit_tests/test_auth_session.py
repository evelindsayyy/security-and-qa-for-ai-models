"""Tests for auth session helpers."""

from __future__ import annotations

import os
import unittest

from frontend import create_app


class TestAuthSession(unittest.TestCase):
    def setUp(self):
        os.environ["AUTH_ENABLED"] = "0"
        os.environ["AUTH_DEV_NETID"] = "testuser"
        os.environ["AUTH_ALLOWED_NETIDS"] = "testuser,other"
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
        self.client = self.app.test_client()

    def tearDown(self):
        os.environ.pop("AUTH_DEV_NETID", None)

    def test_public_view_default(self):
        with self.app.test_request_context("/"):
            from auth.session import effective_user, get_view_mode

            self.assertEqual(get_view_mode(), "public")
            self.assertIsNone(effective_user())

    def test_dev_user_in_private_mode(self):
        with self.client.session_transaction() as sess:
            sess["view_mode"] = "private"
        rv = self.client.get("/auth/me")
        data = rv.get_json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["view_mode"], "private")
        self.assertEqual(data["user"]["netid"], "testuser")

    def test_logout_clears_dev_user(self):
        with self.client.session_transaction() as sess:
            sess["view_mode"] = "private"
        rv = self.client.post("/auth/logout")
        self.assertEqual(rv.status_code, 302)
        rv = self.client.get("/auth/me")
        data = rv.get_json()
        self.assertEqual(data["view_mode"], "public")
        self.assertFalse(data["authenticated"])

    def test_private_view_after_logout_reactivates_dev_user(self):
        self.client.post("/auth/logout")
        self.client.post("/auth/view-mode", data={"mode": "private"})
        rv = self.client.get("/auth/me")
        data = rv.get_json()
        self.assertEqual(data["view_mode"], "private")
        self.assertTrue(data["authenticated"])

    def test_allowlist_when_auth_disabled(self):
        with self.app.test_request_context("/"):
            from auth.session import effective_user, is_allowlisted

            self.assertTrue(is_allowlisted(effective_user()))

    def test_allowlist_when_auth_enabled(self):
        os.environ["AUTH_ENABLED"] = "1"
        with self.app.test_request_context("/"):
            from auth.session import is_allowlisted

            self.assertTrue(is_allowlisted({"netid": "testuser"}))
            self.assertFalse(is_allowlisted({"netid": "blocked"}))
        os.environ["AUTH_ENABLED"] = "0"

    def test_auth_me_endpoint(self):
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": "u1", "netid": "testuser", "display_name": "Test"}
        rv = self.client.get("/auth/me")
        self.assertEqual(rv.status_code, 200)
        data = rv.get_json()
        self.assertTrue(data["authenticated"])

    def test_view_mode_public_without_login(self):
        rv = self.client.post("/auth/view-mode", data={"mode": "public"})
        self.assertEqual(rv.status_code, 302)


if __name__ == "__main__":
    unittest.main()
