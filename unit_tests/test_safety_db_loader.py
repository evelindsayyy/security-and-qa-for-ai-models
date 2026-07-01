"""
Tests for safety/db/load_safety.py — pure transforms only, no database.

Run from repo root:
  uv run python -m unittest unit_tests.test_safety_db_loader -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from safety.db.load_safety import (  # noqa: E402
    finding_rows,
    load_file,
    load_into,
    safety_run_row,
)


def _merged_payload(**overrides) -> dict:
    base = {
        "gateway_model_id": "gpt-4.1",
        "redteam_profile": "base",
        "display_name": "GPT 4.1",
        "status": "complete",
        "deployment_context": {"deployment_type": "chatbot", "has_guardrails": True},
        "summary_pass_rate": 0.9,
        "safety_tier": "low",
        "adversarial_tier": "medium",
        "composite_tier": "low",
        "composite_score": 0.9,
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
        "completed_at": "2026-06-16T15:52:44Z",
    }
    base.update(overrides)
    return base


class SafetyRunRowTest(unittest.TestCase):
    def test_maps_scalar_fields(self) -> None:
        row = safety_run_row(_merged_payload())
        self.assertEqual(row["gateway_model_id"], "gpt-4.1")
        self.assertEqual(row["redteam_profile"], "base")
        self.assertEqual(row["composite_tier"], "low")
        self.assertAlmostEqual(row["composite_score"], 0.9)
        self.assertEqual(row["completed_at"], "2026-06-16T15:52:44+00:00")

    def test_non_base_profile_preserved(self) -> None:
        row = safety_run_row(_merged_payload(redteam_profile="healthcare"))
        self.assertEqual(row["redteam_profile"], "healthcare")

    def test_missing_profile_defaults_to_base(self) -> None:
        payload = _merged_payload()
        del payload["redteam_profile"]
        row = safety_run_row(payload)
        self.assertEqual(row["redteam_profile"], "base")

    def test_z_suffix_normalized(self) -> None:
        row = safety_run_row(_merged_payload(completed_at="2026-01-01T00:00:00Z"))
        self.assertEqual(row["completed_at"], "2026-01-01T00:00:00+00:00")

    def test_missing_completed_at_returns_none(self) -> None:
        row = safety_run_row(_merged_payload(completed_at=None))
        self.assertIsNone(row["completed_at"])

    def test_tiers_are_lowercase_strings(self) -> None:
        row = safety_run_row(_merged_payload(safety_tier="HIGH", adversarial_tier="CRITICAL"))
        self.assertEqual(row["safety_tier"], "high")
        self.assertEqual(row["adversarial_tier"], "critical")


class FindingRowsTest(unittest.TestCase):
    def test_one_row_per_finding(self) -> None:
        rows = finding_rows(_merged_payload())
        self.assertEqual(len(rows), 1)
        f = rows[0]
        self.assertEqual(f["finding_key"], "abc123")
        self.assertEqual(f["source"], "garak")
        self.assertEqual(f["category"], "leakage")
        self.assertTrue(f["passed"])
        self.assertEqual(f["severity"], "medium")

    def test_corroborated_by_preserved(self) -> None:
        data = _merged_payload()
        data["findings"][0]["corroborated_by"] = ["promptfoo"]
        rows = finding_rows(data)
        self.assertEqual(rows[0]["corroborated_by"], ["promptfoo"])

    def test_empty_findings_returns_empty_list(self) -> None:
        self.assertEqual(finding_rows(_merged_payload(findings=[])), [])

    def test_non_dict_findings_skipped(self) -> None:
        data = _merged_payload(findings=["not a dict"])
        self.assertEqual(finding_rows(data), [])


class _FakeCursor:
    def __init__(self, log: list) -> None:
        self._log = log

    def execute(self, sql: str, params: dict) -> None:
        self._log.append((sql, params))

    def fetchone(self):
        return ("fake-run-uuid",)

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
        self._json = json
        data = _merged_payload(
            findings=[
                {
                    "id": "deadbeef",
                    "category": "jailbreak",
                    "source": "promptfoo",
                    "passed": False,
                    "severity": "high",
                    "title": "jailbreak attempt",
                    "description": "model complied",
                    "probe_id": "promptfoo.jailbreak.basic",
                    "probe_suite": "promptfoo_duke_redteam_v1",
                    "corroborated_by": ["garak"],
                }
            ]
        )
        run = safety_run_row(data)
        findings = finding_rows(data)
        self.parsed = [(run, findings)]
        self.conn = _FakeConnection()
        load_into(self.conn, self.parsed)

    def test_statement_sequence_and_single_commit(self) -> None:
        kinds = []
        for sql, _ in self.conn.log:
            if "INSERT INTO public.safety_runs" in sql:
                kinds.append("run_insert")
            elif "SELECT id FROM public.safety_runs" in sql:
                kinds.append("run_select")
            elif "INSERT INTO public.safety_findings" in sql:
                kinds.append("finding_insert")
        self.assertEqual(kinds, ["run_insert", "run_select", "finding_insert"])
        self.assertEqual(self.conn.commits, 1)

    def test_every_insert_is_idempotent(self) -> None:
        inserts = [sql for sql, _ in self.conn.log if "INSERT" in sql]
        self.assertEqual(len(inserts), 2)
        for sql in inserts:
            self.assertIn("ON CONFLICT", sql)

    def test_jsonb_params_are_json_strings(self) -> None:
        _, run_params = self.conn.log[0]
        self.assertIsInstance(run_params["tool_results"], str)
        self._json.loads(run_params["tool_results"])
        self.assertIsInstance(run_params["deployment_context"], str)

    def test_finding_insert_receives_run_id(self) -> None:
        _, finding_params = self.conn.log[2]
        self.assertEqual(finding_params["run_id"], "fake-run-uuid")

    def test_corroborated_by_serialized_as_jsonb(self) -> None:
        _, finding_params = self.conn.log[2]
        self.assertIsInstance(finding_params["corroborated_by"], str)
        self.assertEqual(self._json.loads(finding_params["corroborated_by"]), ["garak"])

    def test_run_insert_includes_redteam_profile(self) -> None:
        _, run_params = self.conn.log[0]
        self.assertIn("redteam_profile", run_params)
        self.assertEqual(run_params["redteam_profile"], "base")


class LoadFileTest(unittest.TestCase):
    def test_valid_result_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp) / "gpt-4.1" / "base"
            model_dir.mkdir(parents=True)
            data = _merged_payload()
            (model_dir / "merged_safety_result.json").write_text(
                json.dumps(data), encoding="utf-8"
            )
            parsed = load_file(model_dir / "merged_safety_result.json")
        assert parsed is not None
        run, findings = parsed
        self.assertEqual(run["gateway_model_id"], "gpt-4.1")
        self.assertEqual(run["redteam_profile"], "base")
        self.assertEqual(len(findings), 1)

    def test_profile_scoped_glob_finds_nested_files(self) -> None:
        """run_ingest uses */*/merged_safety_result.json — verify two profiles are found."""
        from safety.db.load_safety import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for profile in ("base", "healthcare"):
                d = root / "gpt-4.1" / profile
                d.mkdir(parents=True)
                (d / "merged_safety_result.json").write_text(
                    json.dumps(_merged_payload(redteam_profile=profile)), encoding="utf-8"
                )
            result = run_ingest(apply=False, dsn=None, output_dir=root)
        self.assertEqual(result.count, 2)

    def test_flat_file_outside_profile_dir_treated_as_base_profile(self) -> None:
        """Files at <slug>/merged_safety_result.json (legacy layout) load as profile 'base'."""
        from safety.db.load_safety import run_ingest

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slug_dir = root / "gpt-4.1"
            slug_dir.mkdir()
            (slug_dir / "merged_safety_result.json").write_text(
                json.dumps(_merged_payload()), encoding="utf-8"
            )
            result = run_ingest(apply=False, dsn=None, output_dir=root)
        self.assertEqual(result.count, 1)

    def test_missing_completed_at_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp) / "gpt-4.1" / "base"
            model_dir.mkdir(parents=True)
            data = _merged_payload(completed_at=None)
            (model_dir / "merged_safety_result.json").write_text(
                json.dumps(data), encoding="utf-8"
            )
            self.assertIsNone(load_file(model_dir / "merged_safety_result.json"))

    def test_unparsable_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "merged_safety_result.json"
            bad.write_text("not json", encoding="utf-8")
            self.assertIsNone(load_file(bad))


if __name__ == "__main__":
    unittest.main()
