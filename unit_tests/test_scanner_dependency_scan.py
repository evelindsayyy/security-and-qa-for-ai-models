"""
Tests for scanner/dependency_scan.py vulnerability merge logic.

  uv run python -m unittest unit_tests.test_scanner_dependency_scan -v
"""

from __future__ import annotations

import unittest

from scanner.dependency_scan import _merge_vuln_records


class MergeVulnRecordsTest(unittest.TestCase):
    def test_pip_and_osv_same_cve_corroborated(self) -> None:
        pip_rows = [
            {
                "name": "requests",
                "version": "2.25.0",
                "id": "CVE-2024-1234",
                "aliases": ["GHSA-xxxx"],
                "manifest": "requirements.txt",
            }
        ]
        osv_hits = [
            {
                "package": "requests",
                "version": "2.25.0",
                "manifest": "requirements.txt",
                "ecosystem": "PyPI",
                "vuln": {
                    "id": "GHSA-xxxx",
                    "aliases": ["CVE-2024-1234"],
                    "summary": "OSV summary",
                },
            }
        ]
        merged = _merge_vuln_records(pip_rows, osv_hits, ["requirements.txt"])
        self.assertEqual(len(merged), 1)
        row = merged[0]
        self.assertEqual(row["source"], "pip_audit")
        self.assertIn("osv", row.get("corroborated_by") or [])

    def test_osv_only_row_preserved(self) -> None:
        osv_hits = [
            {
                "package": "lodash",
                "version": "4.17.20",
                "manifest": "package.json",
                "ecosystem": "npm",
                "vuln": {"id": "GHSA-yyyy", "aliases": [], "summary": "prototype pollution"},
            }
        ]
        merged = _merge_vuln_records([], osv_hits, ["package.json"])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source"], "osv")
        self.assertEqual(merged[0]["package"], "lodash")


if __name__ == "__main__":
    unittest.main()
