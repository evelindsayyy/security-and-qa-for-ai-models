"""
Tests for safety/exporters/promptfoo.py grading helpers.

  uv run python -m unittest unit_tests.test_promptfoo_exporter -v
"""

from __future__ import annotations

import unittest

from safety.exporters import promptfoo as pf


class GatewayBlockPassTest(unittest.TestCase):
    def test_content_filter_error_counts_as_pass(self) -> None:
        row = {"response": {"error": "ContentPolicyViolation: blocked by Azure"}}
        self.assertTrue(pf._gateway_block_pass(row["response"], row))

    def test_cybersecurity_risk_block_counts_as_pass(self) -> None:
        row = {"response": {"error": "This content was flagged for possible cybersecurity risk."}}
        self.assertTrue(pf._gateway_block_pass(row["response"], row))

    def test_normal_failure_is_not_gateway_pass(self) -> None:
        row = {"response": {"error": "timeout connecting to upstream"}}
        self.assertFalse(pf._gateway_block_pass(row["response"], row))


class HarnessErrorTest(unittest.TestCase):
    def test_maxchars_dropped(self) -> None:
        row = {"response": {"error": "message exceeds maxcharspermessage limit"}}
        self.assertTrue(pf._is_harness_error(row))

    def test_model_error_not_harness(self) -> None:
        row = {"response": {"error": "rate limit exceeded"}}
        self.assertFalse(pf._is_harness_error(row))


class UngradedSetupRowTest(unittest.TestCase):
    def test_no_assertions_row_is_setup(self) -> None:
        row = {"gradingResult": {"pass": True, "reason": "No assertions"}}
        self.assertTrue(pf._is_ungraded_setup_row(row))

    def test_graded_row_is_not_setup(self) -> None:
        row = {"gradingResult": {"pass": True, "reason": "All assertions passed"}}
        self.assertFalse(pf._is_ungraded_setup_row(row))


class DetectSuiteTest(unittest.TestCase):
    def test_redteam_from_config_description(self) -> None:
        payload = {"config": {"description": "Duke redteam eval"}}
        self.assertEqual(pf.detect_promptfoo_suite(payload), pf.SUITE_REDTEAM)

    def test_policy_default(self) -> None:
        payload = {"config": {"description": "Duke policy"}, "results": {"results": []}}
        self.assertEqual(pf.detect_promptfoo_suite(payload), pf.SUITE_POLICY)


class ResultPassedTest(unittest.TestCase):
    def test_grading_pass(self) -> None:
        row = {"gradingResult": {"pass": True}, "response": {}}
        self.assertTrue(pf._result_passed(row, redteam=False))

    def test_gateway_block_counts_as_pass(self) -> None:
        row = {
            "gradingResult": {"pass": False},
            "response": {"error": 'Azure content_filter violation'},
        }
        self.assertTrue(pf._result_passed(row, redteam=True))


if __name__ == "__main__":
    unittest.main()
