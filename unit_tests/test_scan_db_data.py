"""
Tests for the Postgres read path (frontend/scan_db_data.py) — no database.

Run from repo root:
  uv run python -m unittest unit_tests.test_scan_db_data -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import scan_data, scan_db_data


def _scan_data_dict(**overrides):
    base = {
        "model_id": "gpt2",
        "status": "complete",
        "overall_risk_score": 18,
        "severity_tier": "low",
        "findings": [],
        "scanned_files": ["pytorch_model.bin"],
        "tool_results": {
            "modelscan": {"total_issues": 0, "total_skipped": 212},
            "fickling": {"severity": "LIKELY_UNSAFE"},
        },
        "scan_metadata": {
            "scanned_at": "2026-06-16T12:00:00+00:00",
            "scanner_version": "1.0.0",
            "output_slug": "gpt2",
        },
        "fickling_severity": "LIKELY_UNSAFE",
    }
    base.update(overrides)
    return base


def _db_scan_tuple(data: dict):
    meta = data["scan_metadata"]
    return (
        "scan-uuid",
        data["model_id"],
        data["status"],
        data["overall_risk_score"],
        data["severity_tier"],
        data["scanned_files"],
        data["tool_results"],
        meta,
        None,
        meta.get("scanned_at"),
    )


class DbRowMatchesFileRowTest(unittest.TestCase):
    def test_same_keys_and_values(self) -> None:
        data = _scan_data_dict()
        slug = "gpt2"
        with tempfile.TemporaryDirectory() as tmp:
            slug_dir = Path(tmp) / slug
            slug_dir.mkdir()
            path = slug_dir / "scan_result.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            file_row = scan_data._summarize_scan(path, slug)

        db_row = scan_db_data._summarize_db_scan(_db_scan_tuple(data))
        assert db_row is not None
        self.assertEqual(set(file_row), set(db_row))
        for key in file_row:
            self.assertEqual(file_row[key], db_row[key], f"mismatch on {key!r}")


class AvailabilityTest(unittest.TestCase):
    def test_no_dsn_means_unavailable(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("POSTGRES_DSN", None)
            os.environ.pop("DATABASE_URL", None)
            scan_db_data._avail_cache.update(checked_at=0.0, ok=False)
            self.assertFalse(scan_db_data.available())

    def test_dispatcher_serves_files_when_db_unavailable(self) -> None:
        with mock.patch.object(scan_db_data, "available", return_value=False):
            data = scan_data.get_scans_data()
        self.assertIn("has_scans", data)

    def test_detail_dispatcher_falls_back_when_slug_not_in_db(self) -> None:
        sentinel = {"slug": "from-files"}
        with mock.patch.object(scan_db_data, "available", return_value=True), \
             mock.patch.object(scan_db_data, "get_scan_detail_db", return_value=None), \
             mock.patch.object(scan_data, "_get_scan_detail_files", return_value=sentinel):
            detail = scan_data.get_scan_detail("some-slug")
        self.assertIs(detail, sentinel)

    def test_dispatcher_survives_db_exceptions(self) -> None:
        with mock.patch.object(scan_db_data, "available", side_effect=RuntimeError("db down")):
            data = scan_data.get_scans_data()
        self.assertIn("has_scans", data)


if __name__ == "__main__":
    unittest.main()
