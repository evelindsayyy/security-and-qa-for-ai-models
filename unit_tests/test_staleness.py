"""Tests for frontend/staleness.py."""

from __future__ import annotations

import unittest

from frontend.staleness import (
    attach_staleness,
    garak_probe_count_from_data,
    staleness_for,
)


class GarakProbeCountTest(unittest.TestCase):
    def test_counts_distinct_garak_probe_ids(self) -> None:
        data = {
            "findings": [
                {"probe_suite": "garak_subset_v1", "probe_id": "p1"},
                {"probe_suite": "garak_subset_v1", "probe_id": "p1"},
                {"probe_suite": "garak_subset_v1", "probe_id": "p2"},
                {"probe_suite": "promptfoo_duke_policy_v1", "probe_id": "x"},
            ]
        }
        self.assertEqual(garak_probe_count_from_data(data), 2)


class SafetyStalenessTest(unittest.TestCase):
    def test_fresh_when_current(self) -> None:
        from dbutils.staleness_spec import (
            current_safety_garak_probe_spec,
            expected_garak_module_count,
            garak_probe_spec_digest,
        )

        row = {
            "completed_at": "2026-08-01T12:00:00+00:00",
            "missing_suites": [],
            "garak_probe_count": expected_garak_module_count(),
            "status": "complete",
            "garak_probe_spec_digest": garak_probe_spec_digest(
                current_safety_garak_probe_spec()
            ),
        }
        result = staleness_for("safety", row)
        self.assertFalse(result["stale"])

    def test_not_stale_purely_by_old_date_when_spec_matches(self) -> None:
        from dbutils.staleness_spec import (
            current_safety_garak_probe_spec,
            expected_garak_module_count,
            garak_probe_spec_digest,
        )

        row = {
            "completed_at": "2026-05-01T12:00:00+00:00",
            "missing_suites": [],
            "garak_probe_count": expected_garak_module_count(),
            "status": "complete",
            "garak_probe_spec_digest": garak_probe_spec_digest(
                current_safety_garak_probe_spec()
            ),
        }
        result = staleness_for("safety", row)
        self.assertFalse(result["stale"])

    def test_stale_low_garak_count(self) -> None:
        row = {
            "completed_at": "2026-08-01T12:00:00+00:00",
            "missing_suites": [],
            "garak_probe_count": 10,
            "status": "complete",
        }
        result = staleness_for("safety", row)
        self.assertTrue(result["stale"])
        self.assertTrue(any("garak modules" in r for r in result["reasons"]))


class ScanStalenessTest(unittest.TestCase):
    def test_stale_zero_files_scanned(self) -> None:
        row = {
            "scanned_file_count": 0,
            "scanned_at": "2026-08-01T12:00:00+00:00",
            "status": "complete",
        }
        result = staleness_for("scan", row)
        self.assertTrue(result["stale"])
        self.assertIn("0 files scanned", result["reasons"])

    def test_not_stale_by_date_when_scanner_current(self) -> None:
        import scanner

        row = {
            "scanned_file_count": 8,
            "scanned_at": "2026-05-01T12:00:00+00:00",
            "status": "complete",
            "scanner_version": scanner.__version__,
            "tool_status": {
                "modelscan": {},
                "modelaudit": {},
                "secrets": {},
            },
            "tool_applicability": {
                "modelscan": True,
                "modelaudit": True,
                "secrets": True,
                "fickling": False,
                "dependencies": False,
            },
        }
        result = staleness_for("scan", row)
        self.assertFalse(result["stale"])

    def test_not_stale_safetensors_only_without_fickling(self) -> None:
        """Safetensors-only repos should not flag missing fickling."""
        import scanner
        from dbutils.staleness_spec import scan_tool_applicability

        applicability = scan_tool_applicability(["model.safetensors", "config.json"])
        self.assertFalse(applicability["fickling"])
        self.assertFalse(applicability["dependencies"])

        row = {
            "scanned_file_count": 2,
            "scanned_at": "2026-08-01T12:00:00+00:00",
            "status": "complete",
            "scanner_version": scanner.__version__,
            "config_json": {},
            "tool_status": {
                "modelscan": {},
                "modelaudit": {},
                "secrets": {},
            },
            "tool_applicability": applicability,
        }
        result = staleness_for("scan", row)
        self.assertFalse(result["stale"])
        self.assertFalse(any("fickling" in r for r in result["reasons"]))


class EvalStalenessTest(unittest.TestCase):
    def test_stale_unknown_suite(self) -> None:
        row = {
            "timestamp": "2026-08-01T12:00:00Z",
            "suite": "legacy_suite_v0",
        }
        result = staleness_for("eval", row)
        self.assertTrue(result["stale"])

    def test_not_stale_by_date_when_suite_versions_match(self) -> None:
        from dbutils.staleness_spec import current_eval_suite_versions

        current = current_eval_suite_versions("it_support_v1")
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
        result = staleness_for("eval", row)
        self.assertFalse(result["stale"])


class AttachStalenessTest(unittest.TestCase):
    def test_mutates_rows(self) -> None:
        import scanner

        rows = [{
            "scanned_file_count": 5,
            "scanned_at": "2026-08-01T12:00:00+00:00",
            "status": "complete",
            "scanner_version": scanner.__version__,
            "tool_status": {
                "modelscan": {},
                "modelaudit": {},
                "secrets": {},
            },
            "tool_applicability": {
                "modelscan": True,
                "modelaudit": True,
                "secrets": True,
                "fickling": False,
                "dependencies": False,
            },
        }]
        attach_staleness(rows, "scan")
        self.assertIn("staleness", rows[0])
        self.assertFalse(rows[0]["staleness"]["stale"])


if __name__ == "__main__":
    unittest.main()
