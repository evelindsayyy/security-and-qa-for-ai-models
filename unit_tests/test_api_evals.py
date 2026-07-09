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
from api import paging as api_paging  # noqa: E402
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

    def test_status(self) -> None:
        with mock.patch.object(api_evals.eval_launch, "get_status",
                               return_value={"status": "running", "progress": 1, "total": 12}):
            resp = _client().get("/api/evals/r1/status")
        self.assertEqual(resp.get_json()["data"]["status"], "running")

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


class StartEvalTest(unittest.TestCase):
    def test_accepted(self) -> None:
        with mock.patch.object(api_evals.eval_launch, "validate_launch",
                               return_value=None), \
             mock.patch("frontend.pipeline.require_ready_for_downstream",
                        return_value=None), \
             mock.patch.object(api_evals.eval_launch, "start_run",
                               return_value=("run-slug", False)):
            resp = _client().post(
                "/api/evals",
                data='{"candidate":"gpt-5-chat","judge":"Llama 4 Maverick","suite":"it_support_v1"}',
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 202)
        body = resp.get_json()
        self.assertEqual(body["data"]["job_id"], "run-slug")

    def test_validation_error(self) -> None:
        with mock.patch.object(api_evals.eval_launch, "validate_launch",
                               return_value="bad combo"):
            resp = _client().post(
                "/api/evals",
                data='{"candidate":"x","judge":"y","suite":"z"}',
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 400)

    def test_blocked_when_safety_not_cleared(self) -> None:
        with mock.patch.object(api_evals.eval_launch, "validate_launch",
                               return_value=None), \
             mock.patch("frontend.pipeline.require_ready_for_downstream",
                        return_value="safety red-teaming required before this step"), \
             mock.patch.object(api_evals.eval_launch, "start_run") as sr:
            resp = _client().post(
                "/api/evals",
                data='{"candidate":"gpt-5-chat","judge":"Llama 4 Maverick","suite":"it_support_v1"}',
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 400)
        sr.assert_not_called()


# --- Pagination on the list endpoint --------------------------------------
_RUNS5 = [{"slug": f"r{i}", "suite": "it_support", "candidate_model": "m",
           "overall": 4.0} for i in range(5)]


class PaginationTest(unittest.TestCase):
    def _get(self, query: str):
        with mock.patch.object(api_evals.eval_run_data, "get_runs_data",
                               return_value={"runs": list(_RUNS5)}):
            return _client().get("/api/evals" + query)

    def test_limit_slices_and_reports_meta(self) -> None:
        body = self._get("?limit=2").get_json()
        self.assertEqual([r["slug"] for r in body["data"]], ["r0", "r1"])
        self.assertEqual(body["meta"], {"total": 5, "limit": 2, "offset": 0})

    def test_offset(self) -> None:
        body = self._get("?limit=2&offset=2").get_json()
        self.assertEqual([r["slug"] for r in body["data"]], ["r2", "r3"])
        self.assertEqual(body["meta"]["total"], 5)

    def test_limit_capped_at_max(self) -> None:
        body = self._get("?limit=100000").get_json()
        self.assertEqual(body["meta"]["limit"], api_paging.MAX_LIMIT)

    def test_default_meta_has_paging(self) -> None:
        body = self._get("").get_json()
        self.assertEqual(body["meta"]["total"], 5)
        self.assertEqual(body["meta"]["offset"], 0)
        self.assertEqual(body["meta"]["limit"], api_paging.DEFAULT_LIMIT)

    def test_non_integer_limit_400(self) -> None:
        self.assertEqual(self._get("?limit=abc").status_code, 400)

    def test_negative_offset_400(self) -> None:
        self.assertEqual(self._get("?offset=-1").status_code, 400)

    def test_paging_applies_after_filter(self) -> None:
        # filter to a subset, then page within it
        body = self._get("?suite=it_support&limit=3").get_json()
        self.assertEqual(body["meta"]["total"], 5)
        self.assertEqual(len(body["data"]), 3)


# --- Internal errors must stay JSON envelopes (never a raw HTML 500) -------
class ErrorEnvelopeTest(unittest.TestCase):
    def test_internal_error_returns_json_500(self) -> None:
        with mock.patch.object(api_evals.eval_run_data, "get_runs_data",
                               side_effect=RuntimeError("boom")):
            resp = _client().get("/api/evals")
        self.assertEqual(resp.status_code, 500)
        body = resp.get_json()
        self.assertIsNotNone(body)            # JSON, not Flask's HTML error page
        self.assertFalse(body["ok"])
        self.assertIsNone(body["data"])
        self.assertTrue(body["error"])


# --- Health endpoint -------------------------------------------------------
class HealthTest(unittest.TestCase):
    def test_health_reports_db_flag(self) -> None:
        from api import health as api_health
        with mock.patch.object(
            api_health,
            "_pillar_db_flags",
            return_value={"scan": False, "safety": False, "eval": True, "benchmark": False},
        ):
            resp = _client().get("/api/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["status"], "ok")
        self.assertTrue(body["data"]["db_available"])
        self.assertTrue(body["data"]["pillars"]["eval"])


if __name__ == "__main__":
    unittest.main()
