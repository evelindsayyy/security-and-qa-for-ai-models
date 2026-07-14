"""Tests for /models/<slug>/report — the printable PDF report (routes.py::model_report_print)."""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import create_app  # noqa: E402
from frontend import model_rollup, model_summary  # noqa: E402
from frontend import eval_run_data  # noqa: E402

_ROLLUP = {
    "slug": "gpt-4.1-mini", "display_name": "GPT 4.1 Mini",
    "scan": {"tier": "low", "overall_risk_score": 12},
    "safety": {"tier": "low", "pass_rate": 0.9},
    "benchmark": {"kinds": {"mmlu": {"headline_display": "60.0%"}}},
}
_DETAIL = {
    "model": "GPT 4.1 Mini",
    "runs": [{"suite_display": "IT Support", "judge_model": "Llama 4 Maverick", "overall": 4.2}],
}
_REC = {
    "sections": [{"label": "Recommended use", "text": "Good for chat."}],
    "summary": "Solid model.", "tradeoffs": ["Higher cost than open models."],
}


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


class ReportPrintTest(unittest.TestCase):
    def test_known_model_renders_all_pillars(self) -> None:
        with mock.patch.object(model_rollup, "get_model_rollup", return_value=_ROLLUP), \
             mock.patch.object(model_summary, "get_recommendation_summary", return_value=_REC), \
             mock.patch.object(eval_run_data, "get_model_detail", return_value=_DETAIL):
            resp = _client().get("/models/gpt-4.1-mini/report")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        for needle in ["GPT 4.1 Mini", "Recommended use", "IT Support", "60.0%",
                       "90%", "window.print"]:
            self.assertIn(needle, html)

    def test_unknown_model_is_printable_not_500(self) -> None:
        with mock.patch.object(model_rollup, "get_model_rollup", return_value=None):
            resp = _client().get("/models/nope/report")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Model not found", resp.data.decode())
