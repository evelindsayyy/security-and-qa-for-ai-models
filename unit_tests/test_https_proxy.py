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
        for key in ("APP_PORT", "PORT", "CADDY_DOMAIN", "DUKE_OIDC_REDIRECT_URI"):
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

    def test_private_lan_ip_request_host_stays_on_plain_http(self):
        # Reaching the dev box directly on its LAN IP (bypassing an IDE's
        # port-forward entirely) must also stay on http:// — this dev server
        # never speaks TLS, so treating a private IP like a public host would
        # produce an unreachable https:// redirect_uri.
        os.environ["CADDY_DOMAIN"] = ""
        os.environ["DUKE_OIDC_REDIRECT_URI"] = ""
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})

        from auth.oidc import redirect_uri

        for host in ("10.236.144.14:5000", "192.168.1.20:5000", "172.20.0.5:5000"):
            with app.test_request_context("/auth/login", base_url=f"http://{host}"):
                self.assertEqual(redirect_uri(), f"http://{host}/login")

    def test_public_ip_request_host_is_upgraded_to_https(self):
        # A public IP (not RFC1918-private) is treated like any other public
        # host — this dev server should never be reachable that way anyway,
        # but the branch must not silently downgrade to http:// for it.
        os.environ["CADDY_DOMAIN"] = ""
        os.environ["DUKE_OIDC_REDIRECT_URI"] = ""
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})

        from auth.oidc import redirect_uri

        with app.test_request_context("/auth/login", base_url="http://8.8.8.8:5000"):
            self.assertEqual(redirect_uri(), "https://8.8.8.8:5000/login")

    def test_forwarded_loopback_port_is_preserved(self):
        # IDE port-forwards (VS Code Remote, JetBrains Gateway, …) assign an
        # arbitrary local port that changes on every reconnect — there is no
        # env var to pre-configure, so the app must always redirect back to
        # whatever port the browser actually used.
        os.environ["APP_PORT"] = "5000"
        os.environ["CADDY_DOMAIN"] = ""
        os.environ["DUKE_OIDC_REDIRECT_URI"] = ""
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})

        from auth.oidc import redirect_uri

        with app.test_request_context("/auth/login", base_url="http://localhost:59187"):
            self.assertEqual(redirect_uri(), "http://localhost:59187/login")

    def test_forwarded_loopback_port_survives_reconnect_with_a_new_port(self):
        # Same server, same env — only the forwarded port changed (as it does
        # on every IDE reconnect). No stale value should linger anywhere.
        os.environ["APP_PORT"] = "5000"
        os.environ["CADDY_DOMAIN"] = ""
        os.environ["DUKE_OIDC_REDIRECT_URI"] = ""
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})

        from auth.oidc import redirect_uri

        for port in ("59187", "61570", "61706", "48213"):
            with app.test_request_context("/auth/login", base_url=f"http://localhost:{port}"):
                self.assertEqual(redirect_uri(), f"http://localhost:{port}/login")

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


class TestOidcClientHasTimeout(unittest.TestCase):
    """No timeout on the Duke network calls means a slow/unreachable OIDC
    endpoint hangs the request instead of failing fast — regression guard
    for that gap."""

    def tearDown(self):
        for key in ("AUTH_ENABLED", "DUKE_OIDC_CLIENT_ID", "DUKE_OIDC_CLIENT_SECRET"):
            os.environ.pop(key, None)

    def test_duke_client_kwargs_set_a_default_timeout(self):
        os.environ["AUTH_ENABLED"] = "1"
        os.environ["DUKE_OIDC_CLIENT_ID"] = "test-client"
        os.environ["DUKE_OIDC_CLIENT_SECRET"] = "test-secret"
        create_app({"TESTING": True, "SECRET_KEY": "test"})

        from auth.oidc import DUKE_OIDC_TIMEOUT_S, oauth

        client = oauth.create_client("duke")
        self.assertIsNotNone(client)
        self.assertEqual(client.client_kwargs.get("default_timeout"), DUKE_OIDC_TIMEOUT_S)
        self.assertGreater(DUKE_OIDC_TIMEOUT_S, 0)


class TestLoginSurvivesOAuthNetworkFailure(unittest.TestCase):
    """A slow/unreachable Duke endpoint during /auth/login must fail cleanly
    (not hang, not 500) and must not take the rest of the app down with it —
    the signed-out public site has to keep working regardless of whether
    this specific login attempt succeeds."""

    def setUp(self):
        os.environ["AUTH_ENABLED"] = "1"
        os.environ["DUKE_OIDC_CLIENT_ID"] = "test-client"
        os.environ["DUKE_OIDC_CLIENT_SECRET"] = "test-secret"
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        self.client = self.app.test_client()

    def tearDown(self):
        for key in ("AUTH_ENABLED", "DUKE_OIDC_CLIENT_ID", "DUKE_OIDC_CLIENT_SECRET"):
            os.environ.pop(key, None)

    def test_login_returns_clean_error_on_network_failure(self):
        from unittest import mock

        from auth.routes import oauth

        fake_client = mock.Mock()
        fake_client.authorize_redirect.side_effect = TimeoutError("Duke unreachable")
        with mock.patch.object(oauth, "create_client", return_value=fake_client):
            rv = self.client.get("/auth/login")
        self.assertEqual(rv.status_code, 502)
        self.assertIn(b"Duke unreachable", rv.data)

    def test_public_pages_unaffected_by_a_failed_login_attempt(self):
        from unittest import mock

        from auth.routes import oauth

        fake_client = mock.Mock()
        fake_client.authorize_redirect.side_effect = TimeoutError("Duke unreachable")
        with mock.patch.object(oauth, "create_client", return_value=fake_client):
            rv = self.client.get("/auth/login")
        self.assertEqual(rv.status_code, 502)

        # The rest of the (signed-out, public) site must still work — a
        # failed or slow login attempt is not allowed to take it down.
        rv = self.client.get("/hello")
        self.assertEqual(rv.status_code, 200)

    def test_public_page_not_blocked_while_login_is_still_in_flight(self):
        """A *slow* (not failed) Duke round-trip must not serialize behind
        other requests either — regression guard for flask run's threading.
        Verified against a real running container too (see auth/README.md);
        this uses a controlled sleep instead of hitting Duke's live server."""
        import threading
        import time
        from unittest import mock

        from auth.routes import oauth
        from flask import redirect

        def slow_authorize_redirect(*_a, **_k):
            time.sleep(1)
            return redirect("https://oauth.oit.duke.edu/oidc/authorize?fake=1")

        fake_client = mock.Mock()
        fake_client.authorize_redirect.side_effect = slow_authorize_redirect

        results = {}

        def hit(name, path):
            t0 = time.monotonic()
            rv = self.app.test_client().get(path)
            results[name] = (time.monotonic() - t0, rv.status_code)

        with mock.patch.object(oauth, "create_client", return_value=fake_client):
            t_login = threading.Thread(target=hit, args=("login", "/auth/login"))
            t_public = threading.Thread(target=hit, args=("public", "/hello"))
            t_login.start()
            time.sleep(0.1)  # let the login thread start its 1s sleep first
            t_public.start()
            t_login.join()
            t_public.join()

        public_duration, public_status = results["public"]
        login_duration, login_status = results["login"]
        self.assertEqual(public_status, 200)
        self.assertEqual(login_status, 302)
        self.assertLess(public_duration, login_duration)


if __name__ == "__main__":
    unittest.main()
