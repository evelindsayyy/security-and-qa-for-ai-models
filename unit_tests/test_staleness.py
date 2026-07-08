"""Tests for frontend/staleness.py."""

from __future__ import annotations

import unittest

from frontend.staleness import (
    CURRENT_SPEC_CUTOFF,
    SAFETY_EXPECTED_GARAK_PROBES,
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
        row = {
            "completed_at": "2026-08-01T12:00:00+00:00",
            "missing_suites": [],
            "garak_probe_count": SAFETY_EXPECTED_GARAK_PROBES,
            "status": "complete",
        }
        result = staleness_for("safety", row)
        self.assertFalse(result["stale"])

    def test_stale_before_cutoff(self) -> None:
        row = {
            "completed_at": "2026-05-01T12:00:00+00:00",
            "missing_suites": [],
            "garak_probe_count": SAFETY_EXPECTED_GARAK_PROBES,
            "status": "complete",
        }
        result = staleness_for("safety", row)
        self.assertTrue(result["stale"])
        self.assertTrue(any(CURRENT_SPEC_CUTOFF.isoformat() in r for r in result["reasons"]))

    def test_stale_low_garak_count(self) -> None:
        row = {
            "completed_at": "2026-08-01T12:00:00+00:00",
            "missing_suites": [],
            "garak_probe_count": 10,
            "status": "complete",
        }
        result = staleness_for("safety", row)
        self.assertTrue(result["stale"])
        self.assertTrue(any("garak probe count" in r for r in result["reasons"]))


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


class EvalStalenessTest(unittest.TestCase):
    def test_stale_unknown_suite(self) -> None:
        row = {
            "timestamp": "2026-08-01T12:00:00Z",
            "suite": "legacy_suite_v0",
        }
        result = staleness_for("eval", row)
        self.assertTrue(result["stale"])


class AttachStalenessTest(unittest.TestCase):
    def test_mutates_rows(self) -> None:
        rows = [{"scanned_file_count": 5, "scanned_at": "2026-08-01T12:00:00+00:00", "status": "complete"}]
        attach_staleness(rows, "scan")
        self.assertIn("staleness", rows[0])
        self.assertFalse(rows[0]["staleness"]["stale"])


if __name__ == "__main__":
    unittest.main()
