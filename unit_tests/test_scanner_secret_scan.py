"""
Tests for scanner/secret_scan.py TruffleHog parsing helpers.

  uv run python -m unittest unit_tests.test_scanner_secret_scan -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scanner.secret_scan import _extract_secret_entry, _parse_trufflehog_line


class ParseTrufflehogLineTest(unittest.TestCase):
    def test_valid_ndjson(self) -> None:
        line = json.dumps({"DetectorName": "AWS", "Verified": True})
        row = _parse_trufflehog_line(line)
        self.assertEqual(row["DetectorName"], "AWS")

    def test_invalid_json_returns_none(self) -> None:
        self.assertIsNone(_parse_trufflehog_line("not json"))

    def test_blank_line_returns_none(self) -> None:
        self.assertIsNone(_parse_trufflehog_line("   "))


class ExtractSecretEntryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.model_dir = Path(self._tmp.name)

    def test_verified_flag_preserved(self) -> None:
        record = {
            "DetectorName": "GitHub",
            "Verified": True,
            "Redacted": "ghp_xxxx",
            "SourceMetadata": {
                "Data": {"Filesystem": {"file": str(self.model_dir / "config.env")}}
            },
        }
        entry = _extract_secret_entry(record, self.model_dir)
        self.assertTrue(entry["verified"])
        self.assertEqual(entry["detector"], "GitHub")
        self.assertEqual(entry["redacted"], "ghp_xxxx")


if __name__ == "__main__":
    unittest.main()
