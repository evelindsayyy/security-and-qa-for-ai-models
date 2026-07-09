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
        None,
        None,
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

        db_row = scan_db_data._summarize_db_scan(_db_scan_tuple(data), data.get("findings") or [])
        assert db_row is not None
        self.assertEqual(set(file_row), set(db_row))
        for key in file_row:
            self.assertEqual(file_row[key], db_row[key], f"mismatch on {key!r}")

    def test_summarize_db_scan_counts_findings(self) -> None:
        findings = [
            {
                "id": "a1",
                "severity": "high",
                "source": "modelscan",
                "title": "Pickle",
            },
            {
                "id": "a2",
                "severity": "low",
                "source": "fickling",
                "title": "Benign pickle",
            },
        ]
        data = _scan_data_dict(findings=findings)
        row = scan_db_data._summarize_db_scan(_db_scan_tuple(data), findings)
        assert row is not None
        self.assertEqual(row["n_findings"], 2)
        self.assertEqual(row["severity_summary"], "1 high, 1 low")


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

    def test_detail_returns_none_when_slug_not_in_db(self) -> None:
        with mock.patch.object(scan_db_data, "available", return_value=True), \
             mock.patch.object(scan_db_data, "get_scan_detail_db", return_value=None), \
             mock.patch.object(scan_data, "_get_scan_detail_files", return_value={"slug": "from-files"}):
            detail = scan_data.get_scan_detail("some-slug")
        self.assertIsNone(detail)

    def test_dispatcher_survives_db_exceptions(self) -> None:
        with mock.patch.object(scan_db_data, "available", side_effect=RuntimeError("db down")):
            data = scan_data.get_scans_data()
        self.assertIn("has_scans", data)


def _fake_empty_connection():
    """A connection whose scans query always returns zero rows, so
    get_scans_data_db() falls all the way through to its file-merge branch."""
    conn = mock.MagicMock()
    conn.__enter__.return_value = conn
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = []
    return conn


class GetScansDataDbPostgresOnlyTest(unittest.TestCase):
    """When DSN is reachable, get_scans_data_db() must not merge disk artifacts."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out = Path(self._tmp.name)
        patcher = mock.patch.object(scan_db_data, "OUTPUT_DIR", self.out)
        patcher.start()
        self.addCleanup(patcher.stop)
        connect_patcher = mock.patch.object(
            scan_db_data, "_connect", side_effect=_fake_empty_connection
        )
        connect_patcher.start()
        self.addCleanup(connect_patcher.stop)

    def _write_disk_scan(self) -> None:
        scan_dir = self.out / "gpt2"
        scan_dir.mkdir(parents=True)
        (scan_dir / "scan_result.json").write_text(
            json.dumps(_scan_data_dict()), encoding="utf-8"
        )

    def test_disk_scan_not_merged_when_db_empty(self) -> None:
        self._write_disk_scan()
        data = scan_db_data.get_scans_data_db()
        self.assertFalse(data["has_scans"])
        self.assertEqual(data["scans"], [])


if __name__ == "__main__":
    unittest.main()
