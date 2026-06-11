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
from scanner.risk_scorer import _merge_findings, score
from scanner.schemas import Finding, Severity

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

    def test_modelaudit_pickle_family_high_raises_tier(self) -> None:
        ms = {"summary": {"total_issues": 0, "total_issues_by_severity": {}}, "issues": []}
        ma = {
            "actionable_issue_count": 1,
            "issues": [
                {
                    "severity": "high",
                    "location": "malicious_model.bin",
                    "message": "unsafe pickle operator detected",
                    "rule_code": "PKL001",
                }
            ],
        }
        result = score("poc/model", ms, None, None, modelaudit_summary=ma)
        self.assertEqual(result.severity_tier.value, "high")
        self.assertGreaterEqual(result.overall_risk_score, 70)

    def test_corroboration_dedupes_same_signal(self) -> None:
        ms = {"summary": {"total_issues": 0, "total_issues_by_severity": {}}, "issues": []}
        ma = {
            "actionable_issue_count": 1,
            "issues": [
                {
                    "severity": "critical",
                    "location": "evil.bin (pos 10)",
                    "message": "Found REDUCE opcode invoking dangerous global: os.system",
                    "rule_code": "S201",
                    "details": {"import_reference": "os.system"},
                }
            ],
        }
        fick = {
            "severity": "LIKELY_OVERTLY_MALICIOUS",
            "file": "/models/evil.bin",
            "pytorch_format": "raw_pickle",
            "per_file": [
                {
                    "severity": "LIKELY_OVERTLY_MALICIOUS",
                    "file": "/models/evil.bin",
                    "pytorch_format": "raw_pickle",
                }
            ],
        }
        result = score("poc", ms, fick, None, modelaudit_summary=ma)
        self.assertEqual(result.severity_tier.value, "critical")
        # Both tools flag evil.bin; dedupe may merge when signal keys align
        self.assertGreaterEqual(len(result.findings), 1)
        sources = {f.source for f in result.findings}
        self.assertTrue(sources & {"fickling", "modelaudit"})

    def test_merge_findings_corroborates_same_file_and_signal(self) -> None:
        a = Finding(
            id="a",
            source="modelaudit",
            title="Found REDUCE opcode invoking dangerous global: os.system",
            severity=Severity.critical,
            file_path="evil.bin (pos 1)",
            description="dangerous global: os.system",
            raw_tool_severity="critical",
        )
        b = Finding(
            id="b",
            source="fickling",
            title="pickle: os.system",
            severity=Severity.high,
            file_path="/data/evil.bin",
            description="dangerous global: os.system",
            raw_tool_severity="HIGH",
        )
        merged = _merge_findings([a, b])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].severity, Severity.critical)
        self.assertIn("fickling", merged[0].corroborated_by or [])

    def test_safetensors_only_no_fickling_inflation(self) -> None:
        ms = {"summary": {"total_issues": 0, "total_issues_by_severity": {}}, "issues": []}
        fick = {
            "severity": "LIKELY_UNSAFE",
            "file": "model.safetensors",
            "per_file": [{"severity": "LIKELY_UNSAFE", "file": "model.safetensors"}],
        }
        fmt = FileFormatSummary(
            by_category={"safetensors": ["model.safetensors"]},
            flags={"safetensors_only": True, "has_pickle_weights": False},
            file_count=1,
        )
        result = score("safe/st", ms, fick, fmt, modelaudit_summary={"actionable_issue_count": 0})
        self.assertEqual(result.severity_tier.value, "low")
        self.assertFalse(any(f.source == "fickling" for f in result.findings))

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

    def test_dependency_high_cve_raises_tier(self) -> None:
        ms = {"summary": {"total_issues": 0, "total_issues_by_severity": {}}, "issues": []}
        deps = {
            "vuln_count": 1,
            "vulnerabilities": [
                {
                    "package": "pillow",
                    "version": "8.1.0",
                    "id": "CVE-2021-XXXX",
                    "severity": "high",
                    "source": "pip_audit",
                    "manifest": "requirements.txt",
                    "summary": "buffer overflow",
                    "fix_versions": ["8.2.0"],
                }
            ],
        }
        result = score("test/model", ms, None, None, dependency_summary=deps)
        self.assertEqual(result.severity_tier.value, "high")
        self.assertGreaterEqual(result.overall_risk_score, 70)
        self.assertTrue(any(f.source == "pip_audit" for f in result.findings))

    def test_verified_secret_raises_critical(self) -> None:
        ms = {"summary": {"total_issues": 0, "total_issues_by_severity": {}}, "issues": []}
        secrets = {
            "available": True,
            "secret_count": 1,
            "verified_count": 1,
            "secrets": [
                {
                    "detector": "AWS",
                    "file": "config.py",
                    "verified": True,
                    "redacted": "AKIA…[redacted]",
                }
            ],
        }
        result = score("test/model", ms, None, None, secret_summary=secrets)
        self.assertEqual(result.severity_tier.value, "critical")
        self.assertGreaterEqual(result.overall_risk_score, 95)
        self.assertTrue(any(f.source == "trufflehog" for f in result.findings))

    def test_multiple_secrets_same_file_not_deduped(self) -> None:
        ms = {"summary": {"total_issues": 0, "total_issues_by_severity": {}}, "issues": []}
        secrets = {
            "available": True,
            "secret_count": 2,
            "verified_count": 0,
            "secrets": [
                {
                    "detector": "Github",
                    "file": "credentials.env",
                    "verified": False,
                    "redacted": "ghp_…[redacted]",
                },
                {
                    "detector": "SlackWebhook",
                    "file": "credentials.env",
                    "verified": False,
                    "redacted": "https://hooks.slack.com/…",
                },
            ],
        }
        result = score("test/model", ms, None, None, secret_summary=secrets)
        th = [f for f in result.findings if f.source == "trufflehog"]
        self.assertEqual(len(th), 2)
        detectors = {f.title for f in th}
        self.assertIn("secret detected: Github", detectors)
        self.assertIn("secret detected: SlackWebhook", detectors)

    def test_pip_audit_osv_corroboration(self) -> None:
        ms = {"summary": {"total_issues": 0, "total_issues_by_severity": {}}, "issues": []}
        deps = {
            "vuln_count": 1,
            "vulnerabilities": [
                {
                    "package": "pillow",
                    "version": "8.1.0",
                    "id": "CVE-2021-XXXX",
                    "severity": "high",
                    "source": "pip_audit",
                    "corroborated_by": ["osv"],
                    "manifest": "requirements.txt",
                    "summary": "known vuln",
                    "fix_versions": ["8.2.0"],
                }
            ],
        }
        result = score("test/model", ms, None, None, dependency_summary=deps)
        dep_findings = [f for f in result.findings if f.source == "pip_audit"]
        self.assertEqual(len(dep_findings), 1)
        self.assertIn("osv", dep_findings[0].corroborated_by or [])


if __name__ == "__main__":
    unittest.main()
