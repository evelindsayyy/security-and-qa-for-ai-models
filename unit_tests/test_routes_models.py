"""
Tests for the /models catalog risk-column join (frontend/routes.py::
models_catalog) — mocks the gateway catalog and the cross-pillar rollup, no
network/DB/disk access.

Run from repo root:
  uv run python -m unittest unit_tests.test_routes_models -v
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import create_app, routes  # noqa: E402

_GATEWAY = {
    "models": [{"id": "GPT 4.1 Mini", "category": "chat", "notes": "", "owned_by": "openai",
                "price_in": 1.0, "price_out": 2.0}],
    "by_category": [{"label": "chat", "models": [
        {"id": "GPT 4.1 Mini", "category": "chat", "notes": "", "owned_by": "openai",
         "price_in": 1.0, "price_out": 2.0}
    ]}],
    "count": 1, "source": "live", "fetched_at": "t", "error": None, "deprecated": [],
}

_ROLLUP_ROW = {
    "slug": "gpt-4.1-mini",
    "display_name": "GPT 4.1 Mini",
    "scan": None,
    "safety": {"tier": "critical", "pass_rate": 0.42},
    "eval": None,
    "benchmark": None,
}


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


class ModelsCatalogRiskColumnTest(unittest.TestCase):
    def test_tier_badge_renders_for_matched_model(self) -> None:
        with mock.patch.object(routes, "get_gateway_catalog", return_value=_GATEWAY), \
             mock.patch("frontend.model_rollup.get_models_union", return_value=[_ROLLUP_ROW]):
            resp = _client().get("/models")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        self.assertIn('tier tier-critical', html)
        self.assertIn('row-warn', html)
        self.assertIn('data-href="/models/gpt-4.1-mini"', html)

    def test_no_rollup_data_renders_dash_and_no_link(self) -> None:
        with mock.patch.object(routes, "get_gateway_catalog", return_value=_GATEWAY), \
             mock.patch("frontend.model_rollup.get_models_union", return_value=[]):
            resp = _client().get("/models")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        self.assertNotIn("data-href=\"/models/gpt-4.1-mini\"", html)


if __name__ == "__main__":
    unittest.main()
