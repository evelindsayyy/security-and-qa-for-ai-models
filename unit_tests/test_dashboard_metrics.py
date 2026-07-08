"""
Tests for surfacing execution accuracy + robustness on the eval-run dashboard
(frontend/eval_run_data.py).

Offline: the execution_eval / robustness computations are mocked, so no SQL runs
and no suite files are needed. Covers the N/A-safe helpers (cache + fallback) and
that the comparison-row / detail view-models carry the new fields.

Run from repo root:
  uv run python -m unittest unit_tests.test_dashboard_metrics -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from frontend import eval_run_data as erd

# eval_run_data put evaluator/ on sys.path; import the schema + the modules we mock.
sys.path.insert(0, str(Path(erd.__file__).resolve().parent.parent / "evaluator"))
from schemas import (  # noqa: E402
    SCHEMA_VERSION,
    Adaptation,
    EvaluationResult,
    Operational,
)
import execution_eval  # noqa: E402
import robustness  # noqa: E402


def _mk_row(qid: str, overall, suite="sql_smoke_v1", cand="stub-model") -> EvaluationResult:
    return EvaluationResult(
        evaluation_run_id="run1", timestamp="2026-07-08T00:00:00Z",
        question_id=qid, suite=suite, schema_version=SCHEMA_VERSION,
        adaptation=Adaptation(
            candidate_model=cand, candidate_model_version="v",
            system_prompt_version="sp", user_prompt_template_version="raw",
            temperature=0.0, max_tokens=100, task_suite_version=suite,
            rubric_version="(none)", judge_model="(none)", judge_prompt_version="(none)"),
        candidate_response="SELECT 1;", scores={}, overall=overall,
        operational=Operational(latency_ms=10, prompt_tokens=5, completion_tokens=5,
                                estimated_cost_usd=0.0),
        candidate_failed=False, judge_failed=False, error=None)


def _write(dirpath: Path, rows, stem: str) -> Path:
    p = Path(dirpath) / f"{stem}.jsonl"
    p.write_text("\n".join(r.to_jsonl() for r in rows) + "\n", encoding="utf-8")
    return p


_SUMMARY = {"n": 3, "passed": 2, "pass_rate": 0.6667, "check": "sql",
            "rows": [{"question_id": "q1", "passed": True, "error": None, "judge_overall": 4.0},
                     {"question_id": "q2", "passed": False, "error": "wrong rows", "judge_overall": 4.5}]}


class ExecutionSummaryHelperTest(unittest.TestCase):
    def test_computes_caches_then_reads_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "run.jsonl"
            p.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(execution_eval, "score_results_file",
                                   return_value=dict(_SUMMARY)) as m:
                out = erd._execution_summary(p)
                self.assertEqual(out["pass_rate"], 0.6667)
                self.assertTrue((Path(td) / "run_execution.json").is_file())  # cached
                again = erd._execution_summary(p)          # served from sidecar
                self.assertEqual(again["pass_rate"], 0.6667)
            m.assert_called_once()                         # not recomputed

    def test_non_execution_suite_returns_none_and_caches_marker(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "run.jsonl"
            p.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(execution_eval, "score_results_file",
                                   side_effect=ValueError("judge suite")) as m:
                self.assertIsNone(erd._execution_summary(p))
                self.assertIsNone(erd._execution_summary(p))  # from the marker
            m.assert_called_once()


class RobustnessSummaryHelperTest(unittest.TestCase):
    def _rows(self):
        return [SimpleNamespace(question_id="a", overall=4.0),
                SimpleNamespace(question_id="a_typo", overall=3.0)]

    def test_none_when_no_perturbation_metadata(self) -> None:
        with mock.patch.object(robustness, "suite_id_meta", return_value={}):
            self.assertIsNone(erd._robustness_summary(self._rows(), "it_support_v1"))

    def test_returns_report_when_data(self) -> None:
        report = {"by_perturbation": {"typo": {"n": 5, "score_drop": -0.4}},
                  "overall": {"n": 5}, "pass_threshold": 3.0}
        with mock.patch.object(robustness, "suite_id_meta",
                               return_value={"a": {"base_id": "a", "perturbation": "original"}}), \
             mock.patch.object(robustness, "robustness_report", return_value=report):
            self.assertEqual(erd._robustness_summary(self._rows(), "robust_v1"), report)

    def test_none_when_report_empty(self) -> None:
        empty = {"by_perturbation": {"typo": {"n": 0}}, "overall": {"n": 0}}
        with mock.patch.object(robustness, "suite_id_meta",
                               return_value={"a": {"base_id": "a", "perturbation": "original"}}), \
             mock.patch.object(robustness, "robustness_report", return_value=empty):
            self.assertIsNone(erd._robustness_summary(self._rows(), "robust_v1"))


class ComparisonRowIntegrationTest(unittest.TestCase):
    def test_aggregate_file_adds_execution_pass_rate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), [_mk_row("q1", 4.0), _mk_row("q2", 4.5)],
                       "20260708T000000Z_sql_smoke_v1_stub-model")
            with mock.patch.object(erd, "_execution_summary", return_value=dict(_SUMMARY)):
                data = erd._aggregate_file(p)
            self.assertEqual(data["execution_pass_rate"], 0.6667)
            self.assertEqual(data["execution_n"], 3)

    def test_aggregate_file_no_execution_field_for_judge_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), [_mk_row("q1", 4.0)],
                       "20260708T000000Z_it_support_v1_stub-model")
            with mock.patch.object(erd, "_execution_summary", return_value=None):
                data = erd._aggregate_file(p)
            self.assertNotIn("execution_pass_rate", data)


class DetailIntegrationTest(unittest.TestCase):
    def test_detail_carries_execution_and_robustness(self) -> None:
        stem = "20260708T010101Z_sql_smoke_v1_stub-model"
        p = _write(erd.RESULTS_DIR, [_mk_row("q1", 4.0), _mk_row("q2", 4.5)], stem)
        self.addCleanup(lambda: p.unlink(missing_ok=True))
        report = {"by_perturbation": {"typo": {"n": 2, "score_drop": -0.5, "pass_rate_drop": 0.5}},
                  "overall": {"n": 2}, "pass_threshold": 3.0}
        with mock.patch.object(erd, "_execution_summary", return_value=dict(_SUMMARY)), \
             mock.patch.object(erd, "_robustness_summary", return_value=report):
            detail = erd._get_run_detail_files(stem)
        self.assertEqual(detail["execution"]["pass_rate"], 0.6667)
        self.assertEqual(detail["robustness"], report)
        by_qid = {q["question_id"]: q for q in detail["questions"]}
        self.assertTrue(by_qid["q1"]["exec_passed"])
        self.assertFalse(by_qid["q2"]["exec_passed"])


if __name__ == "__main__":
    unittest.main()
