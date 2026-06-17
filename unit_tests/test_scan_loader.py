"""
Tests for scanner/db/load_scans.py — pure transforms only, no database.

Run from repo root:
  uv run python -m unittest unit_tests.test_scan_loader -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from scanner.db.load_scans import (  # noqa: E402
    finding_rows,
    load_file,
    load_into,
    scan_row,
)
from scanner.schemas import build_scan_result_from_combined


def _scan_payload(**overrides) -> dict:
    fixture = json.loads(
        (_REPO / "unit_tests" / "fixtures" / "gpt2_combined_scan.json").read_text(
            encoding="utf-8"
        )
    )
    result = build_scan_result_from_combined(fixture)
    data = result.model_dump(mode="json")
    data.setdefault("scan_metadata", {})
    data["scan_metadata"]["scanned_at"] = "2026-06-16T12:00:00+00:00"
    data["scan_metadata"]["scanner_version"] = "test"
    data.update(overrides)
    return data


class ScanRowTest(unittest.TestCase):
    def test_maps_scalar_fields(self) -> None:
        data = _scan_payload()
        row = scan_row(data, "gpt2")
        self.assertEqual(row["hf_repo"], "gpt2")
        self.assertEqual(row["severity_tier"], "low")
        self.assertEqual(row["overall_risk_score"], 0)
        self.assertEqual(row["completed_at"], "2026-06-16T12:00:00+00:00")
        self.assertEqual(row["scan_metadata"]["output_slug"], "gpt2")

    def test_preserves_fickling_severity_in_metadata(self) -> None:
        data = _scan_payload(fickling_severity="LIKELY_UNSAFE")
        row = scan_row(data, "gpt2")
        self.assertEqual(row["scan_metadata"]["fickling_severity"], "LIKELY_UNSAFE")


class FindingRowsTest(unittest.TestCase):
    def test_one_row_per_finding(self) -> None:
        data = _scan_payload(
            findings=[
                {
                    "id": "abc123",
                    "source": "fickling",
                    "title": "pickle signal",
                    "severity": "low",
                    "file_path": "pytorch_model.bin",
                    "description": "test",
                    "raw_tool_severity": "LIKELY_UNSAFE",
                    "remediation": None,
                    "corroborated_by": None,
                }
            ]
        )
        rows = finding_rows(data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["finding_key"], "abc123")
        self.assertEqual(rows[0]["source"], "fickling")


class _FakeCursor:
    def __init__(self, log: list) -> None:
        self._log = log

    def execute(self, sql: str, params: dict) -> None:
        self._log.append((sql, params))

    def fetchone(self):
        return ("fake-scan-uuid",)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConnection:
    def __init__(self) -> None:
        self.log: list = []
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self.log)

    def commit(self) -> None:
        self.commits += 1


class LoadIntoTest(unittest.TestCase):
    def setUp(self) -> None:
        import json as _json

        self._json = _json
        data = _scan_payload(
            findings=[
                {
                    "id": "deadbeef",
                    "source": "fickling",
                    "title": "t",
                    "severity": "low",
                    "file_path": "a.bin",
                    "description": "d",
                    "raw_tool_severity": "LIKELY_UNSAFE",
                    "remediation": None,
                    "corroborated_by": ["modelscan"],
                }
            ]
        )
        self.parsed = [(scan_row(data, "gpt2"), finding_rows(data))]
        self.conn = _FakeConnection()
        load_into(self.conn, self.parsed)

    def test_statement_sequence_and_single_commit(self) -> None:
        kinds = []
        for sql, _ in self.conn.log:
            if "INSERT INTO public.scans" in sql:
                kinds.append("scan_insert")
            elif "SELECT id FROM public.scans" in sql:
                kinds.append("scan_select")
            elif "INSERT INTO public.findings" in sql:
                kinds.append("finding_insert")
        self.assertEqual(kinds, ["scan_insert", "scan_select", "finding_insert"])
        self.assertEqual(self.conn.commits, 1)

    def test_every_insert_is_idempotent(self) -> None:
        inserts = [sql for sql, _ in self.conn.log if "INSERT" in sql]
        self.assertEqual(len(inserts), 2)
        for sql in inserts:
            self.assertIn("ON CONFLICT", sql)

    def test_jsonb_params_are_json_strings(self) -> None:
        _, scan_params = self.conn.log[0]
        self.assertIsInstance(scan_params["tool_results"], str)
        self._json.loads(scan_params["tool_results"])

    def test_finding_insert_receives_scan_id(self) -> None:
        _, finding_params = self.conn.log[2]
        self.assertEqual(finding_params["scan_id"], "fake-scan-uuid")


class LoadFileTest(unittest.TestCase):
    def test_valid_scan_result_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            slug_dir = Path(tmp) / "gpt2"
            slug_dir.mkdir()
            data = _scan_payload()
            (slug_dir / "scan_result.json").write_text(
                json.dumps(data), encoding="utf-8"
            )
            parsed = load_file(slug_dir / "scan_result.json")
        assert parsed is not None
        scan, findings = parsed
        self.assertEqual(scan["hf_repo"], "gpt2")

    def test_missing_scanned_at_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            slug_dir = Path(tmp) / "gpt2"
            slug_dir.mkdir()
            data = _scan_payload()
            data["scan_metadata"] = {"note": "no timestamp"}
            (slug_dir / "scan_result.json").write_text(
                json.dumps(data), encoding="utf-8"
            )
            self.assertIsNone(load_file(slug_dir / "scan_result.json"))


if __name__ == "__main__":
    unittest.main()
