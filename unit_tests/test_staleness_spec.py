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
            "dim_means": {
                "accuracy": 4.5,
                "completeness": 4.5,
                "policy_adherence": 4.5,
                "tone": 3.0,
            },
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
            "dim_means": {
                "accuracy": 4.0,
                "completeness": 4.0,
                "policy_adherence": 4.0,
                "tone": 3.0,
            },
        }
        reasons = staleness_spec.eval_staleness_reasons(row)
        self.assertTrue(any("rubric_version changed" in r for r in reasons))

    def test_it_support_rubric_version_uses_yaml_not_stem(self) -> None:
        current = staleness_spec.current_eval_suite_versions("it_support_v1")
        self.assertEqual(current["rubric_version"], "it_support_v1")

    def test_missing_rubric_dimensions_is_stale(self) -> None:
        current = staleness_spec.current_eval_suite_versions("policy_qa_v1.1")
        if current is None:
            self.skipTest("policy_qa_v1.1 suite not configured")
        row = {
            "suite": "policy_qa_v1.1",
            **current,
            "dim_means": {
                "accuracy": 4.0,
                "completeness": 4.0,
                # faithfulness, coverage, citation_precision intentionally missing
            },
        }
        reasons = staleness_spec.eval_staleness_reasons(row)
        self.assertTrue(any("missing rubric dimensions" in r for r in reasons))

    def test_execution_suite_not_stale_without_rubric(self) -> None:
        # Execution-scored suites (text-to-SQL/JSON/numeric/tool-use) are graded
        # by running the answer, not an LLM judge — they carry an inert
        # placeholder rubric and no judge dimensions. A current execution run
        # must NOT be flagged stale for "rubric_version changed" or "missing
        # rubric dimensions" (the bug that flagged every execution run).
        current = staleness_spec.current_eval_suite_versions("json_duke_v1")
        if current is None:
            self.skipTest("json_duke_v1 suite not configured")
        row = {
            "suite": "json_duke_v1",
            "system_prompt_version": current["system_prompt_version"],
            # no rubric_version, no dim_means — exactly what an execution run records
            "dim_means": {},
        }
        self.assertEqual(staleness_spec.eval_staleness_reasons(row), [])

    def test_execution_suite_with_inert_rubric_mismatch_not_stale(self) -> None:
        # sql_duke_v2's config points its (inert) rubric at sql_duke_v1.yaml.
        # Even if the run recorded some placeholder rubric_version, an execution
        # suite must not go stale on it.
        current = staleness_spec.current_eval_suite_versions("sql_duke_v2")
        if current is None:
            self.skipTest("sql_duke_v2 suite not configured")
        row = {
            "suite": "sql_duke_v2",
            "rubric_version": "(none)",
            "system_prompt_version": current["system_prompt_version"],
            "dim_means": {},
        }
        self.assertEqual(staleness_spec.eval_staleness_reasons(row), [])

    def test_execution_suite_still_flags_wrong_system_prompt(self) -> None:
        # The system prompt version IS meaningful for execution suites — a
        # changed system prompt should still flag stale.
        row = {
            "suite": "json_duke_v1",
            "system_prompt_version": "old_json_prompt",
            "dim_means": {},
        }
        reasons = staleness_spec.eval_staleness_reasons(row)
        self.assertTrue(
            any("system_prompt_version changed" in r for r in reasons), reasons
        )


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
