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
        os.environ["TRUST_PROXY"] = ""
        os.environ["CADDY_DOMAIN"] = ""
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        self.assertFalse(app.config["SESSION_COOKIE_SECURE"])
        self.assertEqual(app.config["PREFERRED_URL_SCHEME"], "http")

    def test_trust_proxy_via_caddy_domain(self):
        os.environ["TRUST_PROXY"] = ""
        os.environ["CADDY_DOMAIN"] = "model-advisor.colab.duke.edu"
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        self.assertTrue(app.config["SESSION_COOKIE_SECURE"])


class TestOidcRedirectUri(unittest.TestCase):
    def tearDown(self):
        for key in ("APP_FORWARD_PORT", "APP_PORT", "PORT", "CADDY_DOMAIN", "DUKE_OIDC_REDIRECT_URI"):
            os.environ.pop(key, None)

    def test_caddy_domain_overrides_local_redirect_placeholder(self):
        os.environ["CADDY_DOMAIN"] = "model-advisor.colab.duke.edu"
        os.environ["DUKE_OIDC_REDIRECT_URI"] = "http://localhost:5000/login"

        from auth.oidc import redirect_uri

        self.assertEqual(
            redirect_uri(),
            "https://model-advisor.colab.duke.edu/login",
        )

    def test_caddy_domain_used_when_redirect_uri_is_blank(self):
        os.environ["CADDY_DOMAIN"] = "model-advisor.colab.duke.edu"
        os.environ["DUKE_OIDC_REDIRECT_URI"] = ""

        from auth.oidc import redirect_uri

        self.assertEqual(
            redirect_uri(),
            "https://model-advisor.colab.duke.edu/login",
        )

    def test_explicit_nonlocal_redirect_uri_wins(self):
        os.environ["CADDY_DOMAIN"] = "model-advisor.colab.duke.edu"
        os.environ["DUKE_OIDC_REDIRECT_URI"] = "https://custom.example.edu/login"

        from auth.oidc import redirect_uri

        self.assertEqual(redirect_uri(), "https://custom.example.edu/login")

    def test_public_request_host_overrides_local_redirect_placeholder(self):
        os.environ["CADDY_DOMAIN"] = ""
        os.environ["DUKE_OIDC_REDIRECT_URI"] = "http://localhost:5000/login"
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})

        from auth.oidc import redirect_uri

        with app.test_request_context(
            "/auth/login",
            base_url="http://model-advisor.colab.duke.edu",
            headers={"X-Forwarded-Proto": "https"},
        ):
            self.assertEqual(
                redirect_uri(),
                "https://model-advisor.colab.duke.edu/login",
            )

    def test_loopback_request_host_overrides_local_redirect_placeholder(self):
        os.environ["CADDY_DOMAIN"] = ""
        os.environ["DUKE_OIDC_REDIRECT_URI"] = "http://localhost:5000/login"
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})

        from auth.oidc import redirect_uri

        with app.test_request_context("/auth/login", base_url="http://127.0.0.1:5000"):
            self.assertEqual(redirect_uri(), "http://127.0.0.1:5000/login")

    def test_forwarded_loopback_port_uses_configured_app_port(self):
        os.environ["APP_FORWARD_PORT"] = ""
        os.environ["APP_PORT"] = "5000"
        os.environ["CADDY_DOMAIN"] = ""
        os.environ["DUKE_OIDC_REDIRECT_URI"] = ""
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})

        from auth.oidc import redirect_uri

        with app.test_request_context("/auth/login", base_url="http://localhost:59187"):
            self.assertEqual(redirect_uri(), "http://localhost:5000/login")

    def test_explicit_forwarded_loopback_port_is_preserved(self):
        os.environ["APP_FORWARD_PORT"] = "59187"
        os.environ["APP_PORT"] = "5000"
        os.environ["CADDY_DOMAIN"] = ""
        os.environ["DUKE_OIDC_REDIRECT_URI"] = ""
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})

        from auth.oidc import redirect_uri

        with app.test_request_context("/auth/login", base_url="http://localhost:59187"):
            self.assertEqual(redirect_uri(), "http://localhost:59187/login")

    def test_localhost_request_host_keeps_callback_on_localhost(self):
        os.environ["CADDY_DOMAIN"] = ""
        os.environ["DUKE_OIDC_REDIRECT_URI"] = ""
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})

        from auth.oidc import redirect_uri

        with app.test_request_context("/auth/login", base_url="http://localhost:5000"):
            self.assertEqual(redirect_uri(), "http://localhost:5000/login")

    def test_local_fallback_without_request_context_uses_ipv4_loopback(self):
        os.environ["CADDY_DOMAIN"] = ""
        os.environ["DUKE_OIDC_REDIRECT_URI"] = ""

        from auth.oidc import redirect_uri

        self.assertEqual(redirect_uri(), "http://localhost:5000/login")


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
