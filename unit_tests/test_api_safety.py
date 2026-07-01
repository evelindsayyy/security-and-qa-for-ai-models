"""
Tests for the safety JSON API (api/safety.py).

Run from repo root:
  uv run python -m unittest unit_tests.test_api_safety -v
"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from api import safety as api_safety  # noqa: E402
from frontend import create_app  # noqa: E402


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


_MODEL = {"slug": "gpt-4.1-mini", "profile": "base", "summary_pass_rate": 0.91}


class ListSafetyTest(unittest.TestCase):
    def test_list(self) -> None:
        with mock.patch.object(api_safety.safety_data, "get_safety_data",
                               return_value={"models": [_MODEL]}):
            resp = _client().get("/api/safety")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"][0]["slug"], "gpt-4.1-mini")

    def test_filter_profile(self) -> None:
        rows = [
            _MODEL,
            {"slug": "gpt-4.1-mini", "profile": "healthcare", "summary_pass_rate": 0.8},
        ]
        with mock.patch.object(api_safety.safety_data, "get_safety_data",
                               return_value={"models": rows}):
            resp = _client().get("/api/safety?profile=base")
        self.assertEqual(len(resp.get_json()["data"]), 1)


class GetSafetyTest(unittest.TestCase):
    def test_found(self) -> None:
        with mock.patch.object(api_safety.safety_data, "get_safety_detail",
                               return_value={"slug": "gpt-4.1-mini", "profile": "base"}):
            resp = _client().get("/api/safety/gpt-4.1-mini/base")
        self.assertEqual(resp.status_code, 200)

    def test_not_found(self) -> None:
        with mock.patch.object(api_safety.safety_data, "get_safety_detail",
                               return_value=None):
            resp = _client().get("/api/safety/missing/base")
        self.assertEqual(resp.status_code, 404)


class StartSafetyTest(unittest.TestCase):
    def test_accepted(self) -> None:
        with mock.patch.object(api_safety.safety_launch, "validate_launch",
                               return_value=None), \
             mock.patch.object(api_safety.safety_launch, "start_run",
                               return_value=("gpt-4.1-mini/base", False, "public")):
            resp = _client().post(
                "/api/safety",
                data=json.dumps({"model": "GPT 4.1 Mini", "run_garak": False}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 202)
        body = resp.get_json()
        self.assertEqual(body["data"]["job_id"], "gpt-4.1-mini/base")
        self.assertIn("/status", body["data"]["status_url"])


if __name__ == "__main__":
    unittest.main()
