"""Tests for dbutils/staleness_spec.py — dynamic per-pillar staleness rules."""

from __future__ import annotations

import unittest
from unittest import mock

from dbutils import staleness_spec


class ScanStalenessSpecTest(unittest.TestCase):
    def test_current_run_with_all_tools_not_stale_by_date(self) -> None:
        import scanner

        row = {
            "scanned_file_count": 12,
            "scanned_at": "2026-05-01T12:00:00+00:00",
            "status": "complete",
            "scanner_version": scanner.__version__,
            "tool_status": {
                "modelscan": {},
                "fickling": {},
                "modelaudit": {},
                "dependencies": {},
                "secrets": {},
            },
        }
        self.assertEqual(staleness_spec.scan_staleness_reasons(row), [])

    def test_old_scanner_version_is_stale(self) -> None:
        import scanner

        row = {
            "scanned_file_count": 5,
            "status": "complete",
            "scanner_version": "0.1.0",
            "tool_status": {t: {} for t in ("modelscan", "fickling", "modelaudit", "dependencies", "secrets")},
        }
        reasons = staleness_spec.scan_staleness_reasons(row)
        self.assertTrue(any("scanner version" in r for r in reasons))
        self.assertIn(scanner.__version__, reasons[0])

    def test_missing_scanner_when_full_run_expected(self) -> None:
        row = {
            "scanned_file_count": 5,
            "status": "complete",
            "scanner_version": staleness_spec.current_scanner_version(),
            "tool_status": {"modelscan": {}, "fickling": {}},
            "config_json": {},
        }
        reasons = staleness_spec.scan_staleness_reasons(row)
        self.assertIn("missing scanner: modelaudit", reasons)

    def test_partial_scan_config_skips_disabled_tools(self) -> None:
        row = {
            "scanned_file_count": 5,
            "status": "complete",
            "scanner_version": staleness_spec.current_scanner_version(),
            "tool_status": {"modelscan": {}, "fickling": {}},
            "config_json": {
                "skip_modelaudit": True,
                "skip_deps": True,
                "skip_secrets": True,
            },
        }
        self.assertEqual(staleness_spec.scan_staleness_reasons(row), [])


class SafetyStalenessSpecTest(unittest.TestCase):
    def test_full_garak_before_probe_update_not_stale_by_date(self) -> None:
        expected = staleness_spec.expected_garak_module_count()
        row = {
            "completed_at": "2026-05-01T12:00:00+00:00",
            "missing_suites": [],
            "garak_probe_count": expected,
            "status": "complete",
            "garak_probe_spec_digest": staleness_spec.garak_probe_spec_digest(
                staleness_spec.current_safety_garak_probe_spec()
            ),
        }
        self.assertEqual(staleness_spec.safety_staleness_reasons(row), [])

    def test_low_garak_module_count_is_stale(self) -> None:
        row = {
            "completed_at": "2026-08-01T12:00:00+00:00",
            "missing_suites": [],
            "garak_probe_count": 10,
            "status": "complete",
        }
        reasons = staleness_spec.safety_staleness_reasons(row)
        self.assertTrue(any("garak modules" in r for r in reasons))

    def test_garak_probe_spec_change_is_stale(self) -> None:
        row = {
            "missing_suites": [],
            "garak_probe_count": staleness_spec.expected_garak_module_count(),
            "status": "complete",
            "garak_probe_spec_digest": "old-spec-digest",
        }
        reasons = staleness_spec.safety_staleness_reasons(row)
        self.assertIn("garak probe set changed since run", reasons)


class EvalStalenessSpecTest(unittest.TestCase):
    def test_matching_suite_versions_not_stale(self) -> None:
        current = staleness_spec.current_eval_suite_versions("it_support_v1")
        self.assertIsNotNone(current)
        row = {
            "timestamp": "2026-05-01T12:00:00Z",
            "suite": "it_support_v1",
            **current,
        }
        self.assertEqual(staleness_spec.eval_staleness_reasons(row), [])

    def test_unknown_suite_is_stale(self) -> None:
        row = {"suite": "legacy_suite_v0", "timestamp": "2026-08-01T12:00:00Z"}
        reasons = staleness_spec.eval_staleness_reasons(row)
        self.assertTrue(any("not a current curated suite" in r for r in reasons))

    def test_rubric_version_mismatch_is_stale(self) -> None:
        current = staleness_spec.current_eval_suite_versions("it_support_v1")
        row = {
            "suite": "it_support_v1",
            "rubric_version": "old_rubric",
            "system_prompt_version": current["system_prompt_version"],
        }
        reasons = staleness_spec.eval_staleness_reasons(row)
        self.assertTrue(any("rubric_version changed" in r for r in reasons))


class BenchmarkStalenessSpecTest(unittest.TestCase):
    def test_reference_slug_never_stale(self) -> None:
        with mock.patch(
            "frontend.benchmark_data.is_reference_slug",
            return_value=True,
        ):
            from frontend.staleness import staleness_for

            result = staleness_for(
                "benchmark",
                {"slug": "ref-mmlu", "kind": "mmlu", "timestamp_raw": "2020-01-01"},
            )
        self.assertFalse(result["stale"])

    def test_benchmark_definition_change_is_stale(self) -> None:
        current = staleness_spec.current_benchmark_spec_digest("mmlu")
        self.assertIsNotNone(current)
        row = {
            "slug": "20260101T000000Z_mmlu_test",
            "kind": "mmlu",
            "benchmark_spec_digest": "stale-digest",
        }
        reasons = staleness_spec.benchmark_staleness_reasons(row)
        self.assertTrue(any("definition changed" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
