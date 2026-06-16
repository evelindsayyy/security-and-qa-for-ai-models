"""
Tests for scanner/modelaudit_scan.py issue filtering.

  uv run python -m unittest unit_tests.test_scanner_modelaudit -v
"""

from __future__ import annotations

import unittest

from scanner.modelaudit_scan import is_actionable_modelaudit_issue


class IsActionableModelauditIssueTest(unittest.TestCase):
    def test_install_missing_noise_filtered(self) -> None:
        issue = {"severity": "high", "message": "ONNX backend not installed — install with pip"}
        self.assertFalse(is_actionable_modelaudit_issue(issue, modelscan_total_issues=0))

    def test_pickle_noise_suppressed_when_modelscan_found_issues(self) -> None:
        issue = {
            "severity": "medium",
            "rule_code": "S901",
            "message": "pickle reduce opcode detected",
            "type": "pickle_check",
        }
        self.assertFalse(is_actionable_modelaudit_issue(issue, modelscan_total_issues=3))

    def test_pickle_medium_with_reduce_keyword_actionable(self) -> None:
        issue = {
            "severity": "medium",
            "rule_code": "S999",
            "message": "dangerous reduce opcode in pickle stream",
            "type": "pickle_check",
        }
        self.assertTrue(is_actionable_modelaudit_issue(issue, modelscan_total_issues=0))

    def test_non_pickle_medium_actionable(self) -> None:
        issue = {"severity": "medium", "message": "suspicious weight format", "type": "format"}
        self.assertTrue(is_actionable_modelaudit_issue(issue, modelscan_total_issues=0))


if __name__ == "__main__":
    unittest.main()
