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
        garak = json.loads(
            (_ROOT / "safety/garak/output/safety_result.json").read_text()
        )
        self.assertAlmostEqual(garak["summary_pass_rate"], 1 / 3, places=3)


if __name__ == "__main__":
    unittest.main()
