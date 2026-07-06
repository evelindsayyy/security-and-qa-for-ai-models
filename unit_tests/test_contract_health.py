"""
Eval-contract health check — a self-validating guard over EVERY rubric and
suite, run against the real files. This is the safety net for the Week-7 freeze:
once the contract is frozen, any future rubric/suite that breaks these
invariants fails here instead of silently corrupting comparability.

Invariants:
  - every rubric (except the shared-dimension library) resolves through the real
    resolve_rubric, has >=1 dimension, weights that sum to 1.0, and
    evaluation_steps;
  - every judge suite row has a question AND a reference;
  - every execution suite declares a REGISTERED check type and every row has an
    `expected`.

Run from repo root:
  uv run python -m unittest unit_tests.test_contract_health -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_EVALUATOR = Path(__file__).resolve().parent.parent / "evaluator"
sys.path.insert(0, str(_EVALUATOR))

import judge  # noqa: E402
from evaluator import execution_eval as ex  # noqa: E402

RUBRICS = _EVALUATOR / "tasks" / "rubrics"
TASKS = _EVALUATOR / "tasks"


def _rows(path: Path) -> tuple[dict, list[dict]]:
    """(metadata, task_rows) for a suite JSONL. Metadata = the line without id."""
    parsed = [json.loads(line) for line in
              path.read_text(encoding="utf-8").splitlines() if line.strip()]
    meta = next((r for r in parsed if "id" not in r), {})
    tasks = [r for r in parsed if "id" in r]
    return meta, tasks


class RubricHealthTest(unittest.TestCase):
    def test_every_rubric_resolves_and_is_well_formed(self) -> None:
        rubrics = [y for y in RUBRICS.glob("*.yaml") if not y.name.startswith("_")]
        self.assertTrue(rubrics, "no rubrics found")
        for y in rubrics:
            with self.subTest(rubric=y.name):
                resolved, _ = judge.resolve_rubric(y)
                dims = resolved.get("dimensions") or {}
                self.assertTrue(dims, f"{y.name}: no dimensions")
                self.assertTrue(resolved.get("rubric_version"), f"{y.name}: no version")
                self.assertTrue(resolved.get("evaluation_steps"), f"{y.name}: no steps")
                wsum = sum(d.get("weight", 0) for d in dims.values())
                self.assertAlmostEqual(wsum, 1.0, places=2,
                                       msg=f"{y.name}: weights sum to {wsum}, not 1.0")
                # each resolved dimension has an anchored scale
                for name, body in dims.items():
                    self.assertIn("anchors", body, f"{y.name}:{name} has no anchors")


class SuiteHealthTest(unittest.TestCase):
    def _suites(self) -> list[Path]:
        return [p for p in TASKS.glob("*.jsonl")]

    def test_every_suite_is_well_formed(self) -> None:
        suites = self._suites()
        self.assertTrue(suites, "no suites found")
        for path in suites:
            with self.subTest(suite=path.name):
                meta, tasks = _rows(path)
                self.assertTrue(tasks, f"{path.name}: no task rows")
                scoring = meta.get("scoring", "judge")
                if scoring == "execution":
                    check = meta.get("check", "sql")
                    self.assertIn(check, ex.CHECKERS,
                                  f"{path.name}: unregistered check {check!r}")
                    for t in tasks:
                        self.assertIn("expected", t, f"{path.name}:{t['id']} no expected")
                else:  # judge suite
                    for t in tasks:
                        self.assertTrue(t.get("question"),
                                        f"{path.name}:{t['id']} no question")
                        self.assertTrue(t.get("reference"),
                                        f"{path.name}:{t['id']} no reference")


if __name__ == "__main__":
    unittest.main()
