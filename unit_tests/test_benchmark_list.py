"""
Tests for benchmark list deduplication (latest per model + benchmark).

Run from repo root:
  uv run python -m unittest unit_tests.test_benchmark_list -v
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend.benchmark_data import _postprocess_benchmark_runs  # noqa: E402


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

    def test_sorts_deduped_runs_by_score_desc(self) -> None:
        runs = [
            _row("low", kind="mmlu", model="Model A", headline_value=0.60),
            _row("high", kind="ifeval", kind_label="IFEval", model="Model B", headline_value=0.95),
            _row("mid", kind="tomi", kind_label="ToMi", model="Model C", headline_value=0.80),
        ]
        data = _postprocess_benchmark_runs(runs)
        slugs = [r["slug"] for r in data["runs"]]
        self.assertEqual(slugs, ["high", "mid", "low"])

    def test_marks_superseded_rows_in_all_runs(self) -> None:
        runs = [
            _row("old", timestamp_raw="20260601T100000Z"),
            _row("new", timestamp_raw="20260602T100000Z"),
        ]
        data = _postprocess_benchmark_runs(runs)
        by_slug = {r["slug"]: r for r in data["all_runs"]}
        self.assertFalse(by_slug["old"]["is_latest"])
        self.assertTrue(by_slug["new"]["is_latest"])


if __name__ == "__main__":
    unittest.main()
