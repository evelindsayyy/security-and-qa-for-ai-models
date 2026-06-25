"""
Tests for the scan JSON API (api/scans.py).

Run from repo root:
  uv run python -m unittest unit_tests.test_api_scans -v
"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from api import scans as api_scans  # noqa: E402
from frontend import create_app  # noqa: E402


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


_SCAN = {"slug": "gpt2", "model_id": "gpt2", "overall_risk_score": 0.1}


class ListScansTest(unittest.TestCase):
    def test_envelope_and_paging(self) -> None:
        with mock.patch.object(api_scans.scan_data, "get_scans_data",
                               return_value={"scans": [_SCAN]}):
            resp = _client().get("/api/scans")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["slug"], "gpt2")


class GetScanTest(unittest.TestCase):
    def test_found(self) -> None:
        with mock.patch.object(api_scans.scan_data, "get_scan_detail",
                               return_value={"slug": "gpt2", "n_findings": 3}):
            resp = _client().get("/api/scans/gpt2")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["slug"], "gpt2")

    def test_not_found(self) -> None:
        with mock.patch.object(api_scans.scan_data, "get_scan_detail",
                               return_value=None):
            resp = _client().get("/api/scans/missing")
        self.assertEqual(resp.status_code, 404)


class ScanStatusTest(unittest.TestCase):
    def test_status(self) -> None:
        with mock.patch.object(api_scans.scan_launch, "get_status",
                               return_value={"status": "running", "message": ""}):
            resp = _client().get("/api/scans/gpt2/status")
        self.assertEqual(resp.get_json()["data"]["status"], "running")


class StartScanTest(unittest.TestCase):
    def test_validation_error(self) -> None:
        with mock.patch.object(api_scans.scan_launch, "validate_launch",
                               return_value="bad repo"):
            resp = _client().post(
                "/api/scans",
                data=json.dumps({"hf_repo": "bad"}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.get_json()["ok"])

    def test_missing_hf_repo(self) -> None:
        resp = _client().post(
            "/api/scans",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_accepted(self) -> None:
        with mock.patch.object(api_scans.scan_launch, "validate_launch",
                               return_value=None), \
             mock.patch.object(api_scans.scan_launch, "start_run",
                               return_value=("gpt2", False)):
            resp = _client().post(
                "/api/scans",
                data=json.dumps({"hf_repo": "gpt2"}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 202)
        body = resp.get_json()
        self.assertEqual(body["data"]["job_id"], "gpt2")
        self.assertIn("/api/scans/gpt2/status", body["data"]["status_url"])
        self.assertFalse(body["data"]["already_running"])

    def test_output_dir_error_at_validate_returns_503(self) -> None:
        with mock.patch.object(api_scans.scan_launch, "validate_launch",
                               return_value="cannot write to /tmp/x"):
            resp = _client().post(
                "/api/scans",
                data=json.dumps({"hf_repo": "gpt2"}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 503)


if __name__ == "__main__":
    unittest.main()
