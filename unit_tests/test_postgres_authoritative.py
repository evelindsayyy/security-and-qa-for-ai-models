"""Regression: deleted runs must not resurrect from disk when Postgres is authoritative."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import scan_data, scan_db_data, safety_data, safety_db_data


def _fake_empty_connection():
    conn = mock.MagicMock()
    conn.__enter__.return_value = conn
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = []
    cur.fetchone.return_value = None
    return conn


class ScanNoResurrectionTest(unittest.TestCase):
    def test_list_ignores_disk_when_db_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            slug_dir = out / "stale-slug"
            slug_dir.mkdir()
            (slug_dir / "scan_result.json").write_text(
                json.dumps({
                    "model_id": "org/model",
                    "status": "complete",
                    "overall_risk_score": 1,
                    "severity_tier": "low",
                    "findings": [],
                    "scanned_files": ["a.bin"],
                    "scan_metadata": {"scanned_at": "2026-08-01T12:00:00+00:00", "output_slug": "stale-slug"},
                }),
                encoding="utf-8",
            )
            with mock.patch.object(scan_db_data, "OUTPUT_DIR", out), \
                 mock.patch.object(scan_db_data, "_connect", side_effect=_fake_empty_connection), \
                 mock.patch.object(scan_db_data, "available", return_value=True):
                data = scan_data.get_scans_data()
        self.assertFalse(data["has_scans"])

    def test_detail_none_when_db_misses_slug(self) -> None:
        with mock.patch.object(scan_db_data, "available", return_value=True), \
             mock.patch.object(scan_db_data, "get_scan_detail_db", return_value=None):
            detail = scan_data.get_scan_detail("ghost-slug")
        self.assertIsNone(detail)


class SafetyNoResurrectionTest(unittest.TestCase):
    def test_detail_none_when_db_misses_slug(self) -> None:
        with mock.patch.object(safety_db_data, "available", return_value=True), \
             mock.patch.object(safety_db_data, "get_safety_detail_db", return_value=None):
            detail = safety_data.get_safety_detail("ghost-model", "base")
        self.assertIsNone(detail)


class DeleteDbErrorTest(unittest.TestCase):
    def test_surfaces_db_delete_failure(self) -> None:
        from frontend.delete_db import db_delete_error

        err = db_delete_error(db_available=True, db_row_existed=True, removed_db=False)
        self.assertIsNotNone(err)
        self.assertIn("not removed", err)


if __name__ == "__main__":
    unittest.main()
