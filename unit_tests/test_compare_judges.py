"""
Tests for compare_judges.py's from-results analysis — pure functions only,
no API calls, no real results files.

Run from repo root:
  uv run python -m unittest unit_tests.test_compare_judges -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_EVALUATOR = Path(__file__).resolve().parent.parent / "evaluator"
sys.path.insert(0, str(_EVALUATOR))

from compare_judges import (  # noqa: E402
    judge_agreement,
    latest_per_combo,
    load_result_entries,
)


def _entry(suite="s1", candidate="cand", judge="judge", mean=4.0,
           ts="2026-06-11T00:00:00Z"):
    return {
        "file": "x.jsonl", "timestamp": ts, "suite": suite,
        "candidate": candidate, "judge": judge, "judge_prompt": "v2",
        "n": 12, "n_scored": 12, "mean_overall": mean,
    }


def _result_row(candidate="m1", judge="j1", overall=4.0, suite="s1"):
    return {
        "timestamp": "2026-06-11T00:00:00Z",
        "overall": overall,
        "adaptation": {
            "task_suite_version": suite,
            "candidate_model": candidate,
            "judge_model": judge,
            "judge_prompt_version": "reference_based_v2",
        },
    }


class LoadResultEntriesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_reads_results_and_skips_traces_and_garbage(self) -> None:
        rows = [_result_row(overall=4.0), _result_row(overall=5.0)]
        (self.dir / "run.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        (self.dir / "run_trace.jsonl").write_text("{}", encoding="utf-8")
        (self.dir / "broken.jsonl").write_text("not json", encoding="utf-8")

        entries = load_result_entries(self.dir)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["mean_overall"], 4.5)
        self.assertEqual(entries[0]["n_scored"], 2)

    def test_run_with_no_scored_rows_is_skipped(self) -> None:
        row = _result_row()
        row["overall"] = None
        (self.dir / "allfail.jsonl").write_text(json.dumps(row), encoding="utf-8")
        self.assertEqual(load_result_entries(self.dir), [])


class LatestPerComboTest(unittest.TestCase):
    def test_newest_run_wins_per_combo(self) -> None:
        old = _entry(mean=2.0, ts="2026-06-01T00:00:00Z")
        new = _entry(mean=4.0, ts="2026-06-11T00:00:00Z")
        other = _entry(candidate="cand2", mean=3.0)
        kept = latest_per_combo([new, old, other])  # order must not matter
        means = {(e["candidate"]): e["mean_overall"] for e in kept}
        self.assertEqual(means, {"cand": 4.0, "cand2": 3.0})


class JudgeAgreementTest(unittest.TestCase):
    def test_identical_ranking_gives_full_concordance(self) -> None:
        entries = [
            _entry(candidate="strong", judge="A", mean=5.0),
            _entry(candidate="weak", judge="A", mean=3.0),
            _entry(candidate="strong", judge="B", mean=4.5),
            _entry(candidate="weak", judge="B", mean=4.0),
        ]
        stats = judge_agreement(entries, "s1")
        self.assertEqual(stats["ranking"]["A"], ["strong", "weak"])
        self.assertEqual(stats["ranking"]["B"], ["strong", "weak"])
        pair = stats["pairwise"][0]
        self.assertEqual(pair["rank_concordance"], 1.0)
        # A is stricter on weak, lenient equally: mean delta (A-B) on shared
        self.assertAlmostEqual(pair["mean_delta"], (5.0 - 4.5 + 3.0 - 4.0) / 2)

    def test_inverted_ranking_gives_zero_concordance(self) -> None:
        entries = [
            _entry(candidate="x", judge="A", mean=5.0),
            _entry(candidate="y", judge="A", mean=3.0),
            _entry(candidate="x", judge="B", mean=3.0),
            _entry(candidate="y", judge="B", mean=5.0),
        ]
        stats = judge_agreement(entries, "s1")
        self.assertEqual(stats["pairwise"][0]["rank_concordance"], 0.0)

    def test_discrimination_is_strong_weak_gap(self) -> None:
        entries = [
            _entry(candidate="strong", judge="A", mean=4.9),
            _entry(candidate="weak", judge="A", mean=3.9),
        ]
        stats = judge_agreement(entries, "s1")
        self.assertAlmostEqual(stats["discrimination"]["A"], 1.0)

    def test_single_candidate_judge_has_no_discrimination(self) -> None:
        stats = judge_agreement([_entry(judge="A")], "s1")
        self.assertIsNone(stats["discrimination"]["A"])

    def test_other_suites_are_excluded(self) -> None:
        entries = [
            _entry(suite="s1", judge="A", mean=4.0),
            _entry(suite="OTHER", judge="B", mean=1.0),
        ]
        stats = judge_agreement(entries, "s1")
        self.assertEqual(stats["judges"], ["A"])

    def test_judges_without_shared_candidates_skip_pairwise(self) -> None:
        entries = [
            _entry(candidate="x", judge="A"),
            _entry(candidate="y", judge="B"),
        ]
        stats = judge_agreement(entries, "s1")
        self.assertEqual(stats["pairwise"], [])


if __name__ == "__main__":
    unittest.main()
