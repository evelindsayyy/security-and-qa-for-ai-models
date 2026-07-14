"""Tests for /labels — the searchable model-report launcher (routes.py::model_labels)."""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import create_app  # noqa: E402
from frontend import eval_run_data  # noqa: E402

_CARDS = [
    {"slug": "GPT-4.1-Mini", "detail_slug": "gpt-4.1-mini", "model": "GPT 4.1 Mini"},
    {"slug": "Llama-3.3", "detail_slug": "llama-3.3", "model": "Llama 3.3"},
]


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


class LabelsLauncherTest(unittest.TestCase):
    def test_shows_picker_not_grid(self) -> None:
        with mock.patch.object(eval_run_data, "get_all_model_cards", return_value=_CARDS):
            resp = _client().get("/labels")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        self.assertIn("GPT 4.1 Mini", html)
        self.assertIn("<datalist", html)
        self.assertNotIn("mlabel-grid", html)  # the old all-cards grid is gone

    def test_redirects_by_slug(self) -> None:
        with mock.patch.object(eval_run_data, "get_all_model_cards", return_value=_CARDS):
            resp = _client().get("/labels?model=llama-3.3")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/models/llama-3.3", resp.headers["Location"])

    def test_redirects_by_display_name_case_insensitive(self) -> None:
        with mock.patch.object(eval_run_data, "get_all_model_cards", return_value=_CARDS):
            resp = _client().get("/labels?model=gpt 4.1 mini")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/models/gpt-4.1-mini", resp.headers["Location"])

    def test_unknown_model_rerenders_with_note(self) -> None:
        with mock.patch.object(eval_run_data, "get_all_model_cards", return_value=_CARDS):
            resp = _client().get("/labels?model=nope")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("nope", resp.data.decode())


class OverviewNoFeaturedCardTest(unittest.TestCase):
    def test_overview_has_no_featured_report_card(self) -> None:
        with mock.patch(
            "frontend.routes.get_gateway_catalog",
            return_value={"models": [], "count": 0, "error": None},
        ):
            resp = _client().get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("mlabel-featured", resp.data.decode())
