"""
Unit tests for scanner.risk_scorer — no Docker, no HF download, no ModelScan.

Run from repo root:
  uv run python -m unittest unit_tests.test_risk_scorer -v
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scanner.format_detector import FileFormatSummary
from scanner.risk_scorer import score

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "gpt2_combined_scan.json"


class RiskScorerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(_FIXTURE.read_text())

    def test_gpt2_low_tier_with_fickling_signal(self) -> None:
        ms = {
            "summary": {
                "total_issues": self.fixture["tool_results"]["modelscan"]["total_issues"],
                "total_issues_by_severity": {},
            },
            "issues": [],
        }
        fick = self.fixture["tool_results"]["fickling"]
        fmt = FileFormatSummary(
            by_category={"pickle": ["pytorch_model.bin"]},
            flags={"has_pickle_weights": True, "safetensors_only": False},
            file_count=2,
        )
        result = score("gpt2", ms, fick, fmt, modelaudit_summary={"actionable_issue_count": 0})

        self.assertEqual(result.severity_tier.value, "low")
        self.assertGreaterEqual(result.overall_risk_score, 10)
        self.assertLessEqual(result.overall_risk_score, 35)
        fick_findings = [f for f in result.findings if f.source == "fickling"]
        self.assertGreaterEqual(len(fick_findings), 1)
        self.assertEqual(fick_findings[0].raw_tool_severity, "LIKELY_UNSAFE")

    def test_modelaudit_safetensors_medium_raises_tier(self) -> None:
        ms = {"summary": {"total_issues": 0, "total_issues_by_severity": {}}, "issues": []}
        ma = {
            "actionable_issue_count": 1,
            "issues": [
                {
                    "severity": "medium",
                    "location": "model.safetensors",
                    "message": "suspicious header",
                    "rule_code": "ST001",
                }
            ],
        }
        result = score("test/model", ms, None, None, modelaudit_summary=ma)
        self.assertEqual(result.severity_tier.value, "medium")
        self.assertTrue(any(f.source == "modelaudit" for f in result.findings))


if __name__ == "__main__":
    unittest.main()
