"""
Tests for the /compare route (frontend/routes.py::compare_models) — mocks
frontend.model_rollup, no disk/DB access.

Run from repo root:
  uv run python -m unittest unit_tests.test_routes_compare -v
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import create_app  # noqa: E402
from frontend import model_rollup  # noqa: E402

_ROLLUPS = {
    "gpt-4.1-mini": {
        "slug": "gpt-4.1-mini", "display_name": "GPT 4.1 Mini",
        "scan": None,
        "safety": {"tier": "low", "pass_rate": 0.9, "slug": "gpt-4-1-mini", "profile": "base"},
        "eval": {"best_overall": 4.2, "mean_latency_ms": 900, "total_cost_usd": 0.01,
                 "n_runs": 1, "suites": ["it_support_v1"]},
        "benchmark": None,
    },
    "llama-3.3": {
        "slug": "llama-3.3", "display_name": "Llama 3.3",
        "scan": None, "safety": None, "eval": None,
        "benchmark": {"kinds": {"mmlu": {"headline_display": "60.0%"}}},
    },
}


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


def _fake_rollup(slug: str):
    return _ROLLUPS.get(slug)


class CompareRouteTest(unittest.TestCase):
    def test_two_known_models_render_side_by_side(self) -> None:
        with mock.patch.object(model_rollup, "get_model_rollup", side_effect=_fake_rollup):
            resp = _client().get("/compare?models=gpt-4.1-mini,llama-3.3")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        self.assertIn("GPT 4.1 Mini", html)
        self.assertIn("Llama 3.3", html)

    def test_unknown_slug_does_not_500_and_is_reported(self) -> None:
        with mock.patch.object(model_rollup, "get_model_rollup", side_effect=_fake_rollup):
            resp = _client().get("/compare?models=gpt-4.1-mini,nope")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        self.assertIn("GPT 4.1 Mini", html)
        self.assertIn("nope", html)

    def test_all_unknown_shows_empty_state(self) -> None:
        with mock.patch.object(model_rollup, "get_model_rollup", return_value=None):
            resp = _client().get("/compare?models=nope1,nope2")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("None of the selected models matched a known gateway model", resp.data.decode())

    def test_no_query_param_renders_gateway_dropdowns(self) -> None:
        with mock.patch.object(model_rollup, "get_model_rollup", side_effect=_fake_rollup), \
             mock.patch("frontend.routes._compare_gateway_options", return_value=[
                 {"id": "GPT 4.1 Mini", "slug": "gpt-4.1-mini"},
                 {"id": "Llama 3.3", "slug": "llama-3.3"},
             ]):
            resp = _client().get("/compare")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        self.assertIn("compare-model-select", html)
        self.assertIn("GPT 4.1 Mini", html)

    def test_caps_at_five_models(self) -> None:
        slugs = ",".join(f"m{i}" for i in range(8))
        with mock.patch.object(model_rollup, "get_model_rollup", return_value=None):
            resp = _client().get(f"/compare?models={slugs}")
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(resp.data.decode().count("Not found"), 6)


if __name__ == "__main__":
    unittest.main()
