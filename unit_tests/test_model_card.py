"""
Tests for the per-model report card (frontend/eval_run_data.get_model_card).

Offline: get_model_detail and the cross-pillar scan/safety lookups are mocked,
so no data dirs are needed. Covers the badge thresholds, the efficacy join, the
recommended-use derivation, and N/A-safety when a pillar has no data.

Run from repo root:
  uv run python -m unittest unit_tests.test_model_card -v
"""
from __future__ import annotations

import unittest
from unittest import mock

from frontend import eval_run_data as erd


class ScoreBadgeTest(unittest.TestCase):
    def test_thresholds(self) -> None:
        self.assertEqual(erd._score_badge(4.85), {"value": "4.85 / 5", "cls": "ok"})
        self.assertEqual(erd._score_badge(3.85), {"value": "3.85 / 5", "cls": "warn"})
        self.assertEqual(erd._score_badge(1.85), {"value": "1.85 / 5", "cls": "bad"})
        self.assertEqual(erd._score_badge(None), {"value": "—", "cls": "na"})

    def test_boundaries(self) -> None:
        self.assertEqual(erd._score_badge(4.0)["cls"], "ok")
        self.assertEqual(erd._score_badge(2.5)["cls"], "warn")
        self.assertEqual(erd._score_badge(2.49)["cls"], "bad")


class TierBadgeTest(unittest.TestCase):
    def test_known_tiers(self) -> None:
        self.assertEqual(erd._tier_badge("low"), {"value": "Low risk", "cls": "ok"})
        self.assertEqual(erd._tier_badge("MEDIUM"), {"value": "Medium risk", "cls": "warn"})
        self.assertEqual(erd._tier_badge("high"), {"value": "High risk", "cls": "bad"})
        self.assertEqual(erd._tier_badge("critical")["cls"], "bad")

    def test_none_and_unknown(self) -> None:
        self.assertEqual(erd._tier_badge(None), {"value": "—", "cls": "na"})
        self.assertEqual(erd._tier_badge("weird")["cls"], "na")


class RecommendTest(unittest.TestCase):
    def test_cost_sensitive_qa(self) -> None:
        # mockup case: IT 1.85, Q&A 3.85, cost green → "cost-sensitive Q&A"
        self.assertEqual(erd._recommend(1.85, 3.85, "ok"), "cost-sensitive Q&A")

    def test_best_task_without_cost_prefix(self) -> None:
        self.assertEqual(erd._recommend(4.2, 3.0, "warn"), "IT support")

    def test_all_weak(self) -> None:
        self.assertEqual(erd._recommend(1.0, 1.2, "ok"), "not recommended — low task scores")

    def test_no_scores(self) -> None:
        self.assertEqual(erd._recommend(None, None, "na"), "—")


class GetModelCardTest(unittest.TestCase):
    _DETAIL = {"model": "meta-llama/Llama-4-Scout", "runs": [
        {"suite": "it_support_v1", "overall": 1.85},
        {"suite": "policy_qa_v1.1", "overall": 3.85},
    ]}

    def test_full_card_matches_mockup(self) -> None:
        with mock.patch.object(erd, "get_model_detail", return_value=self._DETAIL), \
             mock.patch.object(erd, "_model_cost_effectiveness", return_value=4.85), \
             mock.patch.object(erd, "_lookup_scan_tier", return_value="low"), \
             mock.patch.object(erd, "_lookup_safety_tier", return_value="medium"):
            card = erd.get_model_card("meta-llama--Llama-4-Scout")
        self.assertEqual(card["model"], "meta-llama/Llama-4-Scout")
        self.assertEqual(card["security"][0], {"label": "File scan", "value": "Low risk", "cls": "ok"})
        self.assertEqual(card["security"][1]["value"], "Medium risk")
        self.assertEqual(card["efficacy"][0], {"label": "IT support tasks", "value": "1.85 / 5", "cls": "bad"})
        self.assertEqual(card["efficacy"][2], {"label": "Cost Effectiveness", "value": "4.85 / 5", "cls": "ok"})
        self.assertEqual(card["recommended_use"], "cost-sensitive Q&A")

    def test_na_safe_when_pillars_missing(self) -> None:
        detail = {"model": "M", "runs": [{"suite": "sql_duke_v2", "overall": 4.0}]}
        with mock.patch.object(erd, "get_model_detail", return_value=detail), \
             mock.patch.object(erd, "_model_cost_effectiveness", return_value=None), \
             mock.patch.object(erd, "_lookup_scan_tier", return_value=None), \
             mock.patch.object(erd, "_lookup_safety_tier", return_value=None):
            card = erd.get_model_card("m")
        self.assertTrue(all(row["cls"] == "na" for row in card["security"]))
        self.assertEqual(card["efficacy"][0]["value"], "—")   # no it_support run
        self.assertEqual(card["recommended_use"], "—")

    def test_none_when_no_runs(self) -> None:
        with mock.patch.object(erd, "get_model_detail", return_value=None):
            self.assertIsNone(erd.get_model_card("nope"))

    def test_detail_slug_is_gateway_form_for_links(self) -> None:
        # The card's link slug must match what /models/<slug> resolves (the
        # gateway-normalized, lowercase form) — not the case-preserving
        # model_slug, which would 404 on the detail page.
        detail = {"model": "GPT 4.1 Mini",
                  "runs": [{"suite": "it_support_v1", "overall": 4.2}]}
        with mock.patch.object(erd, "get_model_detail", return_value=detail), \
             mock.patch.object(erd, "_model_cost_effectiveness", return_value=None), \
             mock.patch.object(erd, "_lookup_scan_tier", return_value=None), \
             mock.patch.object(erd, "_lookup_safety_tier", return_value=None):
            card = erd.get_model_card("GPT-4.1-Mini")
        self.assertEqual(card["slug"], "GPT-4.1-Mini")       # eval-identity form
        self.assertEqual(card["detail_slug"], "gpt-4.1-mini")  # link form


class GetAllModelCardsTest(unittest.TestCase):
    def test_dedups_and_orders_most_recent_first(self) -> None:
        data = {"runs": [
            {"candidate_model": "GPT 4.1 Mini", "timestamp": "20260101T000000Z"},
            {"candidate_model": "GPT 4.1 Mini", "timestamp": "20260701T000000Z"},
            {"candidate_model": "Qwen/Qwen2.5-7B-Instruct", "timestamp": "20260705T000000Z"},
        ]}
        with mock.patch.object(erd, "get_runs_data", return_value=data), \
             mock.patch.object(erd, "get_model_card", side_effect=lambda s: {"slug": s}):
            cards = erd.get_all_model_cards()
        self.assertEqual(
            [c["slug"] for c in cards],
            [erd.model_slug("Qwen/Qwen2.5-7B-Instruct"), erd.model_slug("GPT 4.1 Mini")],
        )

    def test_filters_out_none_cards(self) -> None:
        data = {"runs": [{"candidate_model": "M", "timestamp": "t"}]}
        with mock.patch.object(erd, "get_runs_data", return_value=data), \
             mock.patch.object(erd, "get_model_card", return_value=None):
            self.assertEqual(erd.get_all_model_cards(), [])

    def test_empty_when_no_runs(self) -> None:
        with mock.patch.object(erd, "get_runs_data", return_value={"runs": []}):
            self.assertEqual(erd.get_all_model_cards(), [])


class FeaturedModelTest(unittest.TestCase):
    def test_picks_most_recent(self) -> None:
        data = {"runs": [
            {"candidate_model": "old-model", "timestamp": "20260101T000000Z"},
            {"candidate_model": "gpt-5-chat", "timestamp": "20260709T000000Z"},
        ]}
        with mock.patch.object(erd, "get_runs_data", return_value=data):
            self.assertEqual(erd.featured_model_slug(), erd.model_slug("gpt-5-chat"))

    def test_none_when_empty(self) -> None:
        with mock.patch.object(erd, "get_runs_data", return_value={"runs": []}):
            self.assertIsNone(erd.featured_model_slug())


if __name__ == "__main__":
    unittest.main()
