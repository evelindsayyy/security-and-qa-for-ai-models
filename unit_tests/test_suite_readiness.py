"""
Launch-readiness guard for every suite surfaced on the /eval-run/new form.

The freeze guard (test_contract_freeze) proves the suite files are *unchanged*.
This guard proves they are *correct and launchable*: a suite can be frozen and
still be broken (a wrong SQL gold, a judge row with no reference, a badge that
lies about how it's scored). These checks run offline and read the same
``eval_launch.SUITES`` the form does, so anything the user can pick is verified.

What's checked, per suite:
  - structural: metadata line parses; rows have unique ids and non-empty questions
  - count: file rows == suite_question_count() (what the form's cost/est. uses)
  - scoring consistency: the form badge (SUITES[k]['scoring']) matches the file's
    own ``scoring`` metadata — the runner routes on the file, so a mismatch means
    the badge lies about whether the LLM judge runs
  - execution suites: every row has ``expected``; json/numeric golds pass when fed
    back through their checker; sql ``setup`` executes cleanly
  - sql_duke_v2 specifically: a correct reference query passes every gold (proves
    no gold is unreachable — the failure mode that silently tanks a pass-rate)
  - judge suites: every row has a non-empty ``reference``; the rubric resolves and
    has dimensions

Run from repo root:
  uv run python -m unittest unit_tests.test_suite_readiness -v
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import unittest
from pathlib import Path

# Browser launches default to Docker; the readiness checks only read files.
os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import eval_launch  # noqa: E402

# eval_launch puts evaluator/ on sys.path; import the checkers + rubric resolver.
sys.path.insert(0, str(Path(eval_launch.__file__).resolve().parent.parent / "evaluator"))
import execution_eval as ee  # noqa: E402
from judge import resolve_rubric  # noqa: E402

# Correct reference SQL for every sql_duke_v2 gold (the gold-solver). If a future
# sql_duke_v* adds ids, register them here so the achievability check stays total.
_SQL_REFERENCE = {
    "v2-001": "SELECT COUNT(*) FROM course WHERE active=1;",
    "v2-002": "SELECT name FROM student WHERE dept='CS' ORDER BY name;",
    "v2-003": "SELECT SUM(budget) FROM dept;",
    "v2-004": "SELECT COUNT(DISTINCT dept) FROM student;",
    "v2-005": "SELECT COUNT(DISTINCT student_id) FROM enrollment WHERE course='CS101';",
    "v2-006": "SELECT dept, COUNT(*) FROM course GROUP BY dept ORDER BY dept;",
    "v2-007": "SELECT dept FROM course GROUP BY dept HAVING COUNT(*)>2;",
    "v2-008": "SELECT ROUND(AVG(hours),1) FROM ticket WHERE priority='high';",
    "v2-009": "SELECT name FROM student WHERE id NOT IN "
              "(SELECT student_id FROM enrollment) ORDER BY name;",
    "v2-010": "SELECT code FROM course WHERE students > "
              "(SELECT AVG(students) FROM course) ORDER BY code;",
    "v2-011": "SELECT name FROM student WHERE id NOT IN "
              "(SELECT student_id FROM enrollment WHERE course LIKE 'STA%') ORDER BY name;",
    "v2-012": "SELECT student FROM score s WHERE points = "
              "(SELECT MAX(points) FROM score s2 WHERE s2.dept=s.dept) ORDER BY dept;",
    "v2-013": "SELECT COUNT(DISTINCT course) FROM enrollment WHERE student_id=1;",
    "v2-014": "SELECT i.name, COUNT(r.student) FROM instructor i "
              "JOIN section se ON se.instructor_id=i.id "
              "LEFT JOIN roster r ON r.section_id=se.id "
              "GROUP BY i.id, i.name ORDER BY i.name;",
}


def _read_suite(path: Path):
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return json.loads(lines[0]), [json.loads(ln) for ln in lines[1:]]


class SuiteReadinessTest(unittest.TestCase):
    """One subTest per launchable suite — a failure names the exact suite."""

    def _suites(self):
        return eval_launch.SUITES.items()

    def test_structural_and_counts(self) -> None:
        for key, cfg in self._suites():
            with self.subTest(suite=key):
                _meta, rows = _read_suite(cfg["suite"])
                self.assertTrue(rows, "no question rows")
                ids = [r.get("id") for r in rows]
                self.assertTrue(all(ids), "row(s) missing id")
                self.assertEqual(len(ids), len(set(ids)), "duplicate ids")
                self.assertTrue(
                    all(str(r.get("question", "")).strip() for r in rows),
                    "row(s) with empty question")
                self.assertEqual(
                    len(rows), eval_launch.suite_question_count(key),
                    "row count disagrees with suite_question_count()")

    def test_badge_matches_file_scoring(self) -> None:
        # The runner routes on the file's `scoring`; the badge must not lie.
        for key, cfg in self._suites():
            with self.subTest(suite=key):
                meta, _rows = _read_suite(cfg["suite"])
                self.assertEqual(
                    cfg.get("scoring", "judge"), meta.get("scoring", "judge"),
                    "form badge disagrees with file metadata scoring")

    def test_execution_golds_are_wellformed_and_reachable(self) -> None:
        for key, cfg in self._suites():
            if cfg.get("scoring") != "execution":
                continue
            with self.subTest(suite=key):
                meta, rows = _read_suite(cfg["suite"])
                check = meta.get("check", "sql")
                for r in rows:
                    self.assertIn("expected", r, f"{r.get('id')} missing expected")
                    if check == "sql":
                        # setup must build a clean throwaway DB
                        conn = sqlite3.connect(":memory:")
                        try:
                            conn.executescript(r["setup"])
                        finally:
                            conn.close()
                    else:
                        # json/numeric: feeding the gold back must pass its checker
                        resp = (json.dumps(r["expected"]) if check == "json"
                                else str(r["expected"]))
                        ok, err = ee.CHECKERS[check](resp, r)
                        self.assertTrue(ok, f"{r['id']} gold fails its checker: {err}")

    def test_sql_duke_v2_every_gold_is_achievable(self) -> None:
        # The failure mode a structural check can't catch: a gold no correct
        # query can produce. Run the reference solver and require a pass.
        _meta, rows = _read_suite(eval_launch.SUITES["sql_duke_v2"]["suite"])
        for r in rows:
            with self.subTest(question=r["id"]):
                ref = _SQL_REFERENCE.get(r["id"])
                self.assertIsNotNone(ref, "no reference query registered for gold-check")
                ok, err = ee._check_sql(ref, r)
                self.assertTrue(ok, f"correct reference fails the gold: {err}")

    def test_judge_suites_have_references_and_resolvable_rubrics(self) -> None:
        for key, cfg in self._suites():
            if cfg.get("scoring") != "judge":
                continue
            with self.subTest(suite=key):
                _meta, rows = _read_suite(cfg["suite"])
                missing = [r.get("id") for r in rows
                           if not str(r.get("reference", "")).strip()]
                self.assertFalse(missing, f"rows missing a reference: {missing[:5]}")
                rubric, _text = resolve_rubric(cfg["rubric"])
                self.assertTrue(rubric.get("dimensions"),
                                f"rubric {cfg['rubric'].name} has no dimensions")


if __name__ == "__main__":
    unittest.main()
