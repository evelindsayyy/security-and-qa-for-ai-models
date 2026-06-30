"""Tests for HTTPS proxy trust and OAuth callback routes."""

from __future__ import annotations

import os
import unittest

from frontend import create_app


class TestProxyTrust(unittest.TestCase):
    def tearDown(self):
        for key in ("TRUST_PROXY", "CADDY_DOMAIN"):
            os.environ.pop(key, None)

    def test_secure_cookies_when_trust_proxy(self):
        os.environ["TRUST_PROXY"] = "1"
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        self.assertTrue(app.config["SESSION_COOKIE_SECURE"])
        self.assertEqual(app.config["PREFERRED_URL_SCHEME"], "https")

    def test_insecure_cookies_by_default(self):
        os.environ.pop("TRUST_PROXY", None)
        os.environ.pop("CADDY_DOMAIN", None)
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        self.assertFalse(app.config["SESSION_COOKIE_SECURE"])
        self.assertEqual(app.config["PREFERRED_URL_SCHEME"], "http")

    def test_trust_proxy_via_caddy_domain(self):
        os.environ.pop("TRUST_PROXY", None)
        os.environ["CADDY_DOMAIN"] = "model-advisor.colab.duke.edu"
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        self.assertTrue(app.config["SESSION_COOKIE_SECURE"])


class TestOAuthCallbackRoutes(unittest.TestCase):
    def setUp(self):
        os.environ["AUTH_ENABLED"] = "0"
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        self.client = self.app.test_client()

    def test_login_route_registered(self):
        rule_paths = {rule.rule for rule in self.app.url_map.iter_rules()}
        self.assertIn("/login", rule_paths)
        self.assertIn("/auth/callback", rule_paths)

    def test_login_callback_redirects_when_auth_disabled(self):
        rv = self.client.get("/login")
        self.assertEqual(rv.status_code, 302)

    def test_auth_callback_redirects_when_auth_disabled(self):
        rv = self.client.get("/auth/callback")
        self.assertEqual(rv.status_code, 302)


if __name__ == "__main__":
    unittest.main()
