"""
Tests for the Postgres read path (frontend/safety_db_data.py) — no database.

Run from repo root:
  uv run python -m unittest unit_tests.test_safety_db_data -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import safety_data, safety_db_data


def _merged_data_dict(**overrides):
    base = {
        "gateway_model_id": "gpt-4.1",
        "redteam_profile": "base",
        "display_name": "GPT 4.1",
        "status": "complete",
        "deployment_context": {"deployment_type": "chatbot", "has_guardrails": True},
        "summary_pass_rate": 1.0,
        "safety_tier": "low",
        "adversarial_tier": "low",
        "composite_tier": "low",
        "composite_score": 1.0,
        "missing_suites": ["promptfoo_duke_policy_v1"],
        "runs": [
            {
                "probe_suite": "garak_subset_v1",
                "summary_pass_rate": 1.0,
                "n_findings": 1,
                "n_passed": 1,
                "source": "garak",
                "probe_ids": ["garak.apikey"],
            }
        ],
        "findings": [
            {
                "id": "abc123",
                "category": "leakage",
                "source": "garak",
                "passed": True,
                "severity": "medium",
                "title": "garak probe: apikey",
                "description": "20/20 passed",
                "probe_id": "garak.apikey",
                "probe_suite": "garak_subset_v1",
                "corroborated_by": None,
            }
        ],
        "tool_results": {"garak_subset_v1": {"garak": {"run_id": "abc"}}},
        "started_at": "2026-06-16T15:51:06.069743",
        "completed_at": "2026-06-16T15:52:44+00:00",
    }
    base.update(overrides)
    return base


def _db_run_tuple(data: dict):
    """Simulate a row returned by _LATEST_RUNS_SQL / _DETAIL_RUN_SQL."""
    return (
        "run-uuid",
        data["gateway_model_id"],
        data.get("redteam_profile") or "base",
        data.get("display_name"),
        data["status"],
        data.get("deployment_context") or {},
        data["summary_pass_rate"],
        data["safety_tier"],
        data["adversarial_tier"],
        data["composite_tier"],
        data["composite_score"],
        data.get("missing_suites") or [],
        data.get("runs") or [],
        data.get("tool_results") or {},
        data.get("started_at"),
        data.get("completed_at"),
    )


def _db_finding_rows(data: dict) -> list[tuple]:
    """Simulate rows from _FINDINGS_SQL / _FINDINGS_FOR_RUNS_SQL (without run_id prefix)."""
    rows = []
    for f in data.get("findings") or []:
        rows.append((
            f["id"],
            f.get("category", "unknown"),
            f.get("source", "unknown"),
            f.get("passed", False),
            f.get("severity", "unknown"),
            f.get("title", "—"),
            f.get("description", ""),
            f.get("probe_id", "—"),
            f.get("probe_suite"),
            f.get("corroborated_by"),
        ))
    return rows


class DbRowMatchesFileRowTest(unittest.TestCase):
    def test_same_keys_and_values(self) -> None:
        data = _merged_data_dict()
        slug = data["gateway_model_id"]

        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp) / slug
            model_dir.mkdir()
            path = model_dir / "merged_safety_result.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            file_row = safety_data._summarize_merged(path, slug)

        findings_json = safety_db_data._findings_to_json(_db_finding_rows(data))
        db_row = safety_db_data._summarize_db_run(_db_run_tuple(data), findings_json)

        assert file_row is not None
        assert db_row is not None
        self.assertEqual(set(file_row), set(db_row))
        for key in file_row:
            self.assertEqual(file_row[key], db_row[key], f"mismatch on {key!r}")

    def test_summarize_db_run_counts_findings(self) -> None:
        data = _merged_data_dict(
            findings=[
                {
                    "id": "f1",
                    "category": "jailbreak",
                    "source": "promptfoo",
                    "passed": False,
                    "severity": "high",
                    "title": "jailbreak",
                    "description": "",
                    "probe_id": "p.jailbreak",
                    "probe_suite": "promptfoo_duke_redteam_v1",
                    "corroborated_by": None,
                },
                {
                    "id": "f2",
                    "category": "leakage",
                    "source": "garak",
                    "passed": True,
                    "severity": "low",
                    "title": "apikey",
                    "description": "",
                    "probe_id": "garak.apikey",
                    "probe_suite": "garak_subset_v1",
                    "corroborated_by": None,
                },
            ]
        )
        findings_json = safety_db_data._findings_to_json(_db_finding_rows(data))
        row = safety_db_data._summarize_db_run(_db_run_tuple(data), findings_json)
        assert row is not None
        self.assertEqual(row["n_findings"], 2)
        self.assertEqual(row["n_failed"], 1)
        self.assertEqual(row["n_passed"], 1)


class FindingsToJsonTest(unittest.TestCase):
    def test_passed_bool_coerced(self) -> None:
        rows = [("key1", "leakage", "garak", True, "medium", "t", "d", "p.id", "suite", None)]
        out = safety_db_data._findings_to_json(rows)
        self.assertTrue(out[0]["passed"])

    def test_null_corroborated_by_becomes_empty_list(self) -> None:
        rows = [("key1", "leakage", "garak", False, "high", "t", "d", "p.id", None, None)]
        out = safety_db_data._findings_to_json(rows)
        self.assertEqual(out[0]["corroborated_by"], [])


class AvailabilityTest(unittest.TestCase):
    def test_no_dsn_means_unavailable(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("POSTGRES_DSN", None)
            os.environ.pop("DATABASE_URL", None)
            safety_db_data._avail_cache.update(checked_at=0.0, ok=False)
            self.assertFalse(safety_db_data.available())

    def test_dispatcher_serves_files_when_db_unavailable(self) -> None:
        with mock.patch.object(safety_db_data, "available", return_value=False):
            data = safety_data.get_safety_data()
        self.assertIn("has_safety", data)

    def test_detail_returns_none_when_slug_not_in_db(self) -> None:
        with mock.patch.object(safety_db_data, "available", return_value=True), \
             mock.patch.object(safety_db_data, "get_safety_detail_db", return_value=None), \
             mock.patch.object(safety_data, "_get_safety_detail_files", return_value={"slug": "from-files"}):
            detail = safety_data.get_safety_detail("some-slug")
        self.assertIsNone(detail)

    def test_dispatcher_survives_db_exceptions(self) -> None:
        with mock.patch.object(safety_db_data, "available", side_effect=RuntimeError("db down")):
            data = safety_data.get_safety_data()
        self.assertIn("has_safety", data)


if __name__ == "__main__":
    unittest.main()
