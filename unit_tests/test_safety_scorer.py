"""
Unit tests for safety merge — no Docker, no gateway calls.

  uv run python -m unittest unit_tests.test_safety_scorer -v
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from safety.gateway_ids import normalize_gateway_model_id
from safety.safety_scorer import merge_safety_runs
from safety.schemas import SafetySeverity

_ROOT = Path(__file__).resolve().parent.parent


class SafetyScorerTest(unittest.TestCase):
    def test_normalize_gateway_ids(self) -> None:
        self.assertEqual(normalize_gateway_model_id("GPT 4.1 Mini"), "gpt-4.1-mini")
        self.assertEqual(normalize_gateway_model_id("duke-gpt-4.1-mini"), "gpt-4.1-mini")

    def test_merge_promptfoo_and_garak_samples(self) -> None:
        promptfoo = json.loads(
            (_ROOT / "safety/promptfoo/output/safety_result.json").read_text()
        )
        garak = json.loads(
            (_ROOT / "safety/garak/output/safety_result.json").read_text()
        )
        merged = merge_safety_runs([promptfoo, garak])

        self.assertEqual(merged.gateway_model_id, "gpt-4.1-mini")
        self.assertEqual(len(merged.runs), 2)
        self.assertTrue(all(r.probe_ids for r in merged.runs))

    def test_redteam_export_shape(self) -> None:
        from safety.exporters.promptfoo import export_from_promptfoo_eval

        payload = json.loads(
            (_ROOT / "safety/promptfoo/output/redteam_eval.json").read_text()
        )
        doc = export_from_promptfoo_eval(
            payload, source_file="redteam_eval.json", probe_suite="promptfoo_duke_redteam_v1"
        )
        self.assertEqual(doc["probe_suite"], "promptfoo_duke_redteam_v1")
        self.assertGreaterEqual(len(doc["findings"]), 10)
        self.assertTrue(doc["findings"][0]["probe_id"].startswith("promptfoo.redteam."))

    def test_garak_pass_rate_is_per_module(self) -> None:
        garak_path = _ROOT / "safety/garak/output/safety_result.json"
        if not garak_path.is_file():
            garak_path = _ROOT / "safety/garak/output/gpt-4.1-mini/safety_result.json"
        garak = json.loads(garak_path.read_text())
        self.assertAlmostEqual(garak["summary_pass_rate"], 1 / 3, places=3)

    def test_garak_probe_categories(self) -> None:
        from safety.exporters.garak import PROBE_CATEGORY

        self.assertEqual(PROBE_CATEGORY["dan"], "jailbreak")
        self.assertEqual(PROBE_CATEGORY["encoding"], "jailbreak")
        self.assertEqual(PROBE_CATEGORY["web_injection"], "leakage")
        self.assertEqual(PROBE_CATEGORY["goodside"], "policy")

    def test_redteam_plugin_categories(self) -> None:
        from safety.exporters.promptfoo import REDTEAM_PLUGIN_CATEGORY

        self.assertEqual(REDTEAM_PLUGIN_CATEGORY["pii"], "leakage")
        self.assertEqual(REDTEAM_PLUGIN_CATEGORY["pii:direct"], "leakage")
        self.assertEqual(REDTEAM_PLUGIN_CATEGORY["imitation"], "policy")

    def test_slug_second_model(self) -> None:
        self.assertEqual(normalize_gateway_model_id("gpt-5-chat"), "gpt-5-chat")


if __name__ == "__main__":
    unittest.main()
