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
_FIXTURES = _ROOT / "unit_tests" / "fixtures"


class SafetyScorerTest(unittest.TestCase):
    def test_normalize_gateway_ids(self) -> None:
        self.assertEqual(normalize_gateway_model_id("GPT 4.1 Mini"), "gpt-4.1-mini")
        self.assertEqual(normalize_gateway_model_id("duke-gpt-4.1-mini"), "gpt-4.1-mini")

    def test_merge_promptfoo_and_garak_samples(self) -> None:
        promptfoo = json.loads(
            (_FIXTURES / "promptfoo_gpt41mini_safety_result.json").read_text()
        )
        garak = json.loads(
            (_FIXTURES / "garak_gpt41mini_safety_result.json").read_text()
        )
        merged = merge_safety_runs([promptfoo, garak])

        self.assertEqual(merged.gateway_model_id, "gpt-4.1-mini")
        self.assertEqual(len(merged.runs), 2)
        self.assertTrue(all(r.probe_ids for r in merged.runs))

    def test_redteam_export_shape(self) -> None:
        from safety.exporters.promptfoo import export_from_promptfoo_eval

        payload = json.loads(
            (_FIXTURES / "promptfoo_gpt41mini_redteam_eval.json").read_text()
        )
        doc = export_from_promptfoo_eval(
            payload, source_file="redteam_eval.json", probe_suite="promptfoo_duke_redteam_v1"
        )
        self.assertEqual(doc["probe_suite"], "promptfoo_duke_redteam_v1")
        self.assertGreaterEqual(len(doc["findings"]), 10)
        self.assertTrue(doc["findings"][0]["probe_id"].startswith("promptfoo.redteam."))

    def test_garak_pass_rate_is_per_module(self) -> None:
        garak = json.loads(
            (_FIXTURES / "garak_gpt41mini_safety_result.json").read_text()
        )
        self.assertAlmostEqual(garak["summary_pass_rate"], 4 / 9, places=3)

    def test_garak_probe_categories(self) -> None:
        from safety.exporters.garak import PROBE_CATEGORY, PROBE_SEVERITY

        self.assertEqual(PROBE_CATEGORY["dan"], "jailbreak")
        self.assertEqual(PROBE_CATEGORY["encoding"], "jailbreak")
        self.assertEqual(PROBE_CATEGORY["web_injection"], "leakage")
        self.assertEqual(PROBE_CATEGORY["goodside"], "policy")
        self.assertEqual(PROBE_SEVERITY["dan"], "high")
        self.assertEqual(PROBE_SEVERITY["leakreplay"], "medium")
        self.assertEqual(PROBE_SEVERITY["goodside"], "medium")

    def test_redteam_plugin_categories(self) -> None:
        from safety.exporters.promptfoo import REDTEAM_PLUGIN_CATEGORY

        self.assertEqual(REDTEAM_PLUGIN_CATEGORY["pii"], "leakage")
        self.assertEqual(REDTEAM_PLUGIN_CATEGORY["pii:direct"], "leakage")
        self.assertEqual(REDTEAM_PLUGIN_CATEGORY["imitation"], "policy")
        self.assertEqual(REDTEAM_PLUGIN_CATEGORY["harmful:privacy"], "leakage")
        self.assertEqual(REDTEAM_PLUGIN_CATEGORY["rbac"], "policy")
        self.assertEqual(REDTEAM_PLUGIN_CATEGORY["contracts"], "policy")

    def test_slug_second_model(self) -> None:
        self.assertEqual(normalize_gateway_model_id("gpt-5-chat"), "gpt-5-chat")

    def test_policy_vs_adversarial_tier_split(self) -> None:
        """Policy tier ignores garak failures; adversarial tier ignores Duke policy."""
        def _finding(**kw: object) -> dict:
            base = {
                "title": "t",
                "description": "d",
                "passed": True,
                "severity": "low",
                "category": "policy",
                "source": "promptfoo",
                "probe_id": "x",
            }
            base.update(kw)
            return base

        policy_fail = {
            "gateway_model_id": "gpt-test",
            "probe_suite": "promptfoo_duke_policy_v1",
            "summary_pass_rate": 0.9,
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T01:00:00Z",
            "findings": [
                _finding(
                    id="p1",
                    probe_suite="promptfoo_duke_policy_v1",
                    severity="high",
                    passed=False,
                ),
                _finding(
                    id="g1",
                    source="garak",
                    probe_suite="garak_subset_v1",
                    category="jailbreak",
                    severity="critical",
                    passed=False,
                    probe_id="garak.dan",
                ),
            ],
            "tool_results": {},
        }
        garak_only = {
            "gateway_model_id": "gpt-test",
            "probe_suite": "garak_subset_v1",
            "summary_pass_rate": 0.5,
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T01:00:00Z",
            "findings": [policy_fail["findings"][1]],
            "tool_results": {},
        }
        merged = merge_safety_runs([policy_fail, garak_only])
        self.assertEqual(merged.safety_tier, SafetySeverity.high)
        self.assertEqual(merged.adversarial_tier, SafetySeverity.critical)

        policy_pass = dict(policy_fail)
        policy_pass["findings"] = [dict(policy_fail["findings"][0], passed=True)]
        merged2 = merge_safety_runs([policy_pass, garak_only])
        self.assertEqual(merged2.safety_tier, SafetySeverity.low)
        self.assertEqual(merged2.adversarial_tier, SafetySeverity.critical)

    def test_composite_tier_calibration(self) -> None:
        """A safe model with weak garak still reads low; a policy breach escalates."""

        def _suite(suite: str, rate: float, *, fail_policy_high: bool = False) -> dict:
            findings = [
                {
                    "id": f"{suite}-pass",
                    "title": "t",
                    "description": "d",
                    "passed": True,
                    "severity": "low",
                    "category": "policy",
                    "source": "promptfoo",
                    "probe_id": "ok",
                    "probe_suite": suite,
                }
            ]
            if fail_policy_high:
                findings.append({
                    "id": f"{suite}-fail",
                    "title": "t",
                    "description": "d",
                    "passed": False,
                    "severity": "high",
                    "category": "policy",
                    "source": "promptfoo",
                    "probe_id": "bad",
                    "probe_suite": suite,
                })
            return {
                "gateway_model_id": "gpt-test",
                "probe_suite": suite,
                "summary_pass_rate": rate,
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T01:00:00Z",
                "findings": findings,
                "tool_results": {},
            }

        # Safe profile: perfect policy + red-team, weak garak (aggressive) → low.
        safe = merge_safety_runs([
            _suite("promptfoo_duke_policy_v1", 1.0),
            _suite("promptfoo_duke_redteam_v1", 1.0),
            _suite("garak_subset_v1", 0.33),
        ])
        self.assertEqual(safe.composite_tier, SafetySeverity.low)

        # A high-severity Duke policy failure floors the tier at medium even
        # with otherwise strong suites.
        breach = merge_safety_runs([
            _suite("promptfoo_duke_policy_v1", 0.95, fail_policy_high=True),
            _suite("promptfoo_duke_redteam_v1", 1.0),
            _suite("garak_subset_v1", 1.0),
        ])
        self.assertEqual(breach.composite_tier, SafetySeverity.medium)

    def test_missing_suite_is_reported(self) -> None:
        """Skipped suites are surfaced and don't sink the score."""
        run = {
            "gateway_model_id": "gpt-test",
            "probe_suite": "promptfoo_duke_policy_v1",
            "summary_pass_rate": 1.0,
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T01:00:00Z",
            "findings": [{
                "id": "p", "title": "t", "description": "d", "passed": True,
                "severity": "low", "category": "policy", "source": "promptfoo",
                "probe_id": "ok", "probe_suite": "promptfoo_duke_policy_v1",
            }],
            "tool_results": {},
        }
        merged = merge_safety_runs([run])
        self.assertIn("garak_subset_v1", merged.missing_suites)
        self.assertIn("promptfoo_duke_redteam_v1", merged.missing_suites)
        self.assertEqual(merged.composite_tier, SafetySeverity.low)


if __name__ == "__main__":
    unittest.main()
