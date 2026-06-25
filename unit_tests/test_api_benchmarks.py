"""
Tests for the benchmark JSON API (api/benchmarks.py).

Run from repo root:
  uv run python -m unittest unit_tests.test_api_benchmarks -v
"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from api import benchmarks as api_benchmarks  # noqa: E402
from frontend import create_app  # noqa: E402


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


_RUN = {"slug": "truthfulqa-gpt-4.1-mini", "benchmark": "truthfulqa", "model": "GPT 4.1 Mini"}


class ListBenchmarksTest(unittest.TestCase):
    def test_list(self) -> None:
        with mock.patch.object(api_benchmarks.benchmark_data, "get_benchmarks_data",
                               return_value={"runs": [_RUN]}):
            resp = _client().get("/api/benchmarks")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["meta"]["total"], 1)


class GetBenchmarkTest(unittest.TestCase):
    def test_not_found(self) -> None:
        with mock.patch.object(api_benchmarks.benchmark_data, "get_benchmark_detail",
                               return_value=None):
            resp = _client().get("/api/benchmarks/missing")
        self.assertEqual(resp.status_code, 404)


class StartBenchmarkTest(unittest.TestCase):
    def test_accepted(self) -> None:
        with mock.patch.object(api_benchmarks.benchmark_launch, "validate_launch",
                               return_value=None), \
             mock.patch.object(api_benchmarks.benchmark_launch, "start_run",
                               return_value=("truthfulqa-gpt-4.1-mini", True)):
            resp = _client().post(
                "/api/benchmarks",
                data=json.dumps({"benchmark": "truthfulqa", "model": "GPT 4.1 Mini"}),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 202)
        body = resp.get_json()
        self.assertTrue(body["data"]["already_running"])


if __name__ == "__main__":
    unittest.main()
