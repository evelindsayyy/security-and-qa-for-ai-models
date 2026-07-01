"""Assert safety_schema.sql defines the expected safety_runs / safety_findings tables."""

from __future__ import annotations

import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SCHEMA = _REPO / "safety" / "db" / "safety_schema.sql"


_RUNS_COLUMNS = (
    "gateway_model_id",
    "redteam_profile",
    "display_name",
    "status",
    "deployment_context",
    "summary_pass_rate",
    "safety_tier",
    "adversarial_tier",
    "composite_tier",
    "composite_score",
    "missing_suites",
    "runs",
    "tool_results",
    "started_at",
    "completed_at",
    "created_at",
)

_FINDINGS_COLUMNS = (
    "run_id",
    "finding_key",
    "category",
    "source",
    "passed",
    "severity",
    "title",
    "description",
    "probe_id",
    "probe_suite",
    "corroborated_by",
)


class SafetySchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = _SCHEMA.read_text(encoding="utf-8")

    def test_defines_safety_runs_table(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS public.safety_runs", self.sql)

    def test_defines_safety_findings_table(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS public.safety_findings", self.sql)

    def test_safety_runs_unique_key_includes_profile(self) -> None:
        self.assertIn("UNIQUE (gateway_model_id, redteam_profile, completed_at)", self.sql)

    def test_safety_findings_unique_key(self) -> None:
        self.assertIn("UNIQUE (run_id, finding_key)", self.sql)

    def test_safety_runs_columns(self) -> None:
        for col in _RUNS_COLUMNS:
            with self.subTest(column=col):
                self.assertIn(col, self.sql)

    def test_safety_findings_columns(self) -> None:
        for col in _FINDINGS_COLUMNS:
            with self.subTest(column=col):
                self.assertIn(col, self.sql)

    def test_findings_references_runs_with_cascade(self) -> None:
        self.assertIn("REFERENCES public.safety_runs(id) ON DELETE CASCADE", self.sql)

    def test_no_draft_warning(self) -> None:
        self.assertNotIn("DO NOT run", self.sql)


if __name__ == "__main__":
    unittest.main()
