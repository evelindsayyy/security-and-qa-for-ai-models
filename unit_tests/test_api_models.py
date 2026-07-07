"""
Tests for the cross-pillar model JSON API (api/models.py) — Flask test
client, no DB, data layer mocked.

Run from repo root:
  uv run python -m unittest unit_tests.test_api_models -v
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from api import models as api_models  # noqa: E402
from api import paging as api_paging  # noqa: E402
from frontend import create_app  # noqa: E402


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


_ROW = {"slug": "gpt-5-chat", "display_name": "GPT 5 Chat",
        "scan": None, "safety": {"tier": "low"}, "eval": {"n_runs": 3}, "benchmark": None}
_ROW2 = {"slug": "llama-3.3", "display_name": "Llama 3.3",
         "scan": None, "safety": None, "eval": None, "benchmark": {"kinds": {}}}


class ListModelsTest(unittest.TestCase):
    def test_envelope_and_total(self) -> None:
        with mock.patch.object(api_models.model_rollup, "get_models_union",
                               return_value=[_ROW, _ROW2]):
            resp = _client().get("/api/models")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["ok"])
        self.assertIsNone(body["error"])
        self.assertEqual(body["meta"]["total"], 2)
        self.assertEqual(len(body["data"]), 2)


class GetModelTest(unittest.TestCase):
    def test_found(self) -> None:
        with mock.patch.object(api_models.model_rollup, "get_model_rollup",
                               return_value={"slug": "gpt-5-chat", "eval": {"n_runs": 3}}):
            resp = _client().get("/api/models/gpt-5-chat")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["eval"]["n_runs"], 3)

    def test_not_found_404(self) -> None:
        with mock.patch.object(api_models.model_rollup, "get_model_rollup",
                               return_value=None):
            resp = _client().get("/api/models/nope")
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.get_json()["ok"])

    def test_invalid_slug_400(self) -> None:
        with mock.patch.object(api_models, "is_safe_slug", return_value=False):
            resp = _client().get("/api/models/whatever")
        self.assertEqual(resp.status_code, 400)


# --- Pagination on the list endpoint --------------------------------------
_ROWS5 = [{"slug": f"m{i}", "display_name": f"m{i}",
           "scan": None, "safety": None, "eval": None, "benchmark": None} for i in range(5)]


class PaginationTest(unittest.TestCase):
    def _get(self, query: str):
        with mock.patch.object(api_models.model_rollup, "get_models_union",
                               return_value=list(_ROWS5)):
            return _client().get("/api/models" + query)

    def test_limit_slices_and_reports_meta(self) -> None:
        body = self._get("?limit=2").get_json()
        self.assertEqual([r["slug"] for r in body["data"]], ["m0", "m1"])
        self.assertEqual(body["meta"], {"total": 5, "limit": 2, "offset": 0})

    def test_offset(self) -> None:
        body = self._get("?limit=2&offset=2").get_json()
        self.assertEqual([r["slug"] for r in body["data"]], ["m2", "m3"])

    def test_limit_capped_at_max(self) -> None:
        body = self._get("?limit=100000").get_json()
        self.assertEqual(body["meta"]["limit"], api_paging.MAX_LIMIT)

    def test_non_integer_limit_400(self) -> None:
        self.assertEqual(self._get("?limit=abc").status_code, 400)

    def test_negative_offset_400(self) -> None:
        self.assertEqual(self._get("?offset=-1").status_code, 400)


class ErrorEnvelopeTest(unittest.TestCase):
    def test_internal_error_returns_json_500(self) -> None:
        with mock.patch.object(api_models.model_rollup, "get_models_union",
                               side_effect=RuntimeError("boom")):
            resp = _client().get("/api/models")
        self.assertEqual(resp.status_code, 500)
        body = resp.get_json()
        self.assertIsNotNone(body)
        self.assertFalse(body["ok"])
        self.assertIsNone(body["data"])
        self.assertTrue(body["error"])


if __name__ == "__main__":
    unittest.main()
