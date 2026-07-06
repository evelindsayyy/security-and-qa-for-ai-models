"""
Tests for benchmark list deduplication (latest per model + benchmark).

Run from repo root:
  uv run python -m unittest unit_tests.test_benchmark_list -v
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend.benchmark_data import (  # noqa: E402
    _build_comparison_section,
    _postprocess_benchmark_runs,
    normalize_timestamp_raw,
)


def _row(
    slug: str,
    *,
    kind: str = "mmlu",
    kind_label: str = "MMLU",
    model: str = "GPT 4.1 Mini",
    headline_value: float = 0.8,
    timestamp_raw: str = "20260601T120000Z",
) -> dict:
    return {
        "slug": slug,
        "filename": f"{slug}.json",
        "kind": kind,
        "kind_label": kind_label,
        "model": model,
        "headline_metric": "accuracy",
        "headline_value": headline_value,
        "headline_display": f"{headline_value:.1%}",
        "n": 100,
        "timestamp_raw": timestamp_raw,
        "timestamp": timestamp_raw,
        "extras": {},
    }


class BenchmarkListDedupeTest(unittest.TestCase):
    def test_keeps_latest_run_per_model_and_benchmark(self) -> None:
        runs = [
            _row("old", headline_value=0.70, timestamp_raw="20260601T100000Z"),
            _row("new", headline_value=0.75, timestamp_raw="20260602T100000Z"),
        ]
        data = _postprocess_benchmark_runs(runs)
        self.assertEqual(data["run_count"], 1)
        self.assertEqual(data["all_run_count"], 2)
        self.assertEqual(data["runs"][0]["slug"], "new")
        self.assertTrue(data["runs"][0]["is_latest"])
        self.assertEqual(data["runs"][0]["older_run_count"], 1)

    def test_keeps_both_when_model_or_benchmark_differs(self) -> None:
        runs = [
            _row("mmlu-a", kind="mmlu", model="GPT 4.1 Mini"),
            _row("ifeval-a", kind="ifeval", kind_label="IFEval", model="GPT 4.1 Mini"),
            _row("mmlu-b", kind="mmlu", model="Llama 3.3"),
        ]
        data = _postprocess_benchmark_runs(runs)
        self.assertEqual(data["run_count"], 3)

    def test_sorts_deduped_runs_by_timestamp_desc(self) -> None:
        runs = [
            _row("old", model="Model A", timestamp_raw="20260601T100000Z"),
            _row("new", model="Model B", timestamp_raw="20260602T100000Z"),
            _row("mid", kind="ifeval", kind_label="IFEval", model="Model C", timestamp_raw="20260601T150000Z"),
        ]
        data = _postprocess_benchmark_runs(runs)
        slugs = [r["slug"] for r in data["runs"]]
        self.assertEqual(slugs, ["new", "mid", "old"])

    def test_marks_superseded_rows_in_all_runs(self) -> None:
        runs = [
            _row("old", timestamp_raw="20260601T100000Z"),
            _row("new", timestamp_raw="20260602T100000Z"),
        ]
        data = _postprocess_benchmark_runs(runs)
        by_slug = {r["slug"]: r for r in data["all_runs"]}
        self.assertFalse(by_slug["old"]["is_latest"])
        self.assertTrue(by_slug["new"]["is_latest"])


class BenchmarkTimestampNormalizeTest(unittest.TestCase):
    def test_normalizes_db_isoformat(self) -> None:
        self.assertEqual(
            normalize_timestamp_raw("2026-07-02T15:37:00+00:00", ""),
            "20260702T153700Z",
        )

    def test_normalizes_compact_json_timestamp(self) -> None:
        self.assertEqual(
            normalize_timestamp_raw("20260624T154900Z", ""),
            "20260624T154900Z",
        )

    def test_slug_fallback_when_body_timestamp_missing(self) -> None:
        self.assertEqual(
            normalize_timestamp_raw("", "20260702T153700Z_mbpp_gpt"),
            "20260702T153700Z",
        )

    def test_newest_sort_order_after_normalization(self) -> None:
        runs = [
            _row("old", model="A", timestamp_raw="2026-06-24T15:49:00+00:00"),
            _row("new", model="B", timestamp_raw="20260702T153700Z"),
        ]
        for r in runs:
            r["timestamp_raw"] = normalize_timestamp_raw(r["timestamp_raw"], r["slug"])
        runs.sort(key=lambda r: r["timestamp_raw"], reverse=True)
        self.assertEqual(runs[0]["slug"], "new")


class BenchmarkComparisonMatrixTest(unittest.TestCase):
    def test_builds_benchmark_by_model_matrix(self) -> None:
        runs = [
            _row("c1", kind="consistency", kind_label="Consistency", model="gpt-5-codex", headline_value=0.82),
            _row("m1", kind="mmlu", model="GPT 4.1 Mini", headline_value=0.80),
            _row("m2", kind="mmlu", model="Llama 3.3", headline_value=0.75),
        ]
        for r in runs:
            r["score_class"] = "score-mid"
            r["coverage"] = {"partial": False, "failed": 0, "n_display": "100"}
        data = _build_comparison_section(runs)
        self.assertTrue(data["has_comparison"])
        self.assertEqual(data["comparison_models"], ["GPT 4.1 Mini", "Llama 3.3", "gpt-5-codex"])
        mmlu = next(r for r in data["comparison_rows"] if r["key"] == "mmlu")
        self.assertIn("GPT 4.1 Mini", mmlu["cells"])
        self.assertIn("Llama 3.3", mmlu["cells"])
        self.assertNotIn("gpt-5-codex", mmlu["cells"])
        consistency = next(r for r in data["comparison_rows"] if r["key"] == "consistency")
        self.assertIn("gpt-5-codex", consistency["cells"])

    def test_empty_runs_yields_no_comparison(self) -> None:
        data = _build_comparison_section([])
        self.assertFalse(data["has_comparison"])
        self.assertEqual(data["comparison_models"], [])


if __name__ == "__main__":
    unittest.main()
