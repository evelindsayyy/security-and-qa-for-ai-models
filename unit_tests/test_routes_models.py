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
    "subscores": {"safety": 42.0},
    "aggregate": 42.0,
    "inputs_hash": "test",
}


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


class ModelsCatalogRiskColumnTest(unittest.TestCase):
    def test_tier_badge_renders_for_matched_model(self) -> None:
        with mock.patch.object(routes, "get_gateway_catalog", return_value=_GATEWAY), \
             mock.patch(
                 "frontend.model_rollup.lookup_rollup_for_gateway",
                 return_value=_ROLLUP_ROW,
             ):
            resp = _client().get("/models")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        self.assertIn('tier tier-critical', html)
        self.assertIn('row-warn', html)
        self.assertIn('data-href="/models/gpt-4.1-mini"', html)

    def test_runless_gateway_row_still_links_to_detail(self) -> None:
        empty = {
            "slug": "gpt-4.1-mini",
            "display_name": "GPT 4.1 Mini",
            "scan": None,
            "safety": None,
            "eval": None,
            "benchmark": None,
            "subscores": {},
            "aggregate": None,
            "inputs_hash": "empty",
        }
        with mock.patch.object(routes, "get_gateway_catalog", return_value=_GATEWAY), \
             mock.patch(
                 "frontend.model_rollup.lookup_rollup_for_gateway",
                 return_value=empty,
             ):
            resp = _client().get("/models")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        self.assertIn('data-href="/models/gpt-4.1-mini"', html)
        self.assertIn('<span class="dim">—</span>', html)


if __name__ == "__main__":
    unittest.main()
