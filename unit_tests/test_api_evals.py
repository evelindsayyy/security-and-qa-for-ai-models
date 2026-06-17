"""
Tests for the efficacy JSON API (api/evals.py) — Flask test client, no DB.

Verifies the envelope shape, filtering, and the 400/404 paths, with the data
layer mocked so neither Postgres nor result files are touched.

Run from repo root:
  uv run python -m unittest unit_tests.test_api_evals -v
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from api import evals as api_evals  # noqa: E402
from frontend import create_app  # noqa: E402


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


_RUN = {"slug": "r1", "suite": "it_support", "candidate_model": "gpt-5-chat",
        "overall": 4.3, "dims": ["accuracy"]}
_RUN2 = {"slug": "r2", "suite": "summarization", "candidate_model": "Llama 3.3",
         "overall": 3.9, "dims": ["faithfulness"]}


class ListEvalsTest(unittest.TestCase):
    def test_envelope_and_total(self) -> None:
        with mock.patch.object(api_evals.eval_run_data, "get_runs_data",
                               return_value={"runs": [_RUN, _RUN2]}):
            resp = _client().get("/api/evals")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["ok"])
        self.assertIsNone(body["error"])
        self.assertEqual(body["meta"]["total"], 2)
        self.assertEqual(len(body["data"]), 2)

    def test_filter_by_suite(self) -> None:
        with mock.patch.object(api_evals.eval_run_data, "get_runs_data",
                               return_value={"runs": [_RUN, _RUN2]}):
            resp = _client().get("/api/evals?suite=summarization")
        self.assertEqual([r["slug"] for r in resp.get_json()["data"]], ["r2"])

    def test_filter_by_model_slug(self) -> None:
        with mock.patch.object(api_evals.eval_run_data, "get_runs_data",
                               return_value={"runs": [_RUN, _RUN2]}), \
             mock.patch.object(api_evals.eval_run_data, "model_slug",
                               side_effect=lambda n: n.replace(" ", "-")):
            resp = _client().get("/api/evals?model=Llama-3.3")
        self.assertEqual([r["slug"] for r in resp.get_json()["data"]], ["r2"])


class GetEvalTest(unittest.TestCase):
    def test_found(self) -> None:
        with mock.patch.object(api_evals.eval_run_data, "get_run_detail",
                               return_value={"slug": "r1", "n": 12}):
            resp = _client().get("/api/evals/r1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["slug"], "r1")

    def test_not_found_404(self) -> None:
        with mock.patch.object(api_evals.eval_run_data, "get_run_detail",
                               return_value=None):
            resp = _client().get("/api/evals/nope")
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.get_json()["ok"])

    def test_invalid_slug_400(self) -> None:
        with mock.patch.object(api_evals, "is_safe_slug", return_value=False):
            resp = _client().get("/api/evals/whatever")
        self.assertEqual(resp.status_code, 400)


class GetModelTest(unittest.TestCase):
    def test_found(self) -> None:
        with mock.patch.object(api_evals.eval_run_data, "get_model_detail",
                               return_value={"slug": "gpt-5-chat", "n_runs": 3}):
            resp = _client().get("/api/models/gpt-5-chat")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["n_runs"], 3)

    def test_not_found_404(self) -> None:
        with mock.patch.object(api_evals.eval_run_data, "get_model_detail",
                               return_value=None):
            resp = _client().get("/api/models/nope")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
