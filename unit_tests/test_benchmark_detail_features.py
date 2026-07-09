"""
Detail pagination, MMLU subject sort, rerun prefill, and hub latest helpers.

Run from repo root:
  uv run python -m unittest unit_tests.test_benchmark_detail_features -v
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend.benchmark_data import (  # noqa: E402
    DETAIL_ITEMS_PAGE_SIZE,
    _attach_rerun,
    _build_reference_section,
    _load_stored_run_options,
    _paginate_detail_items,
    _per_subject_rows,
    get_benchmark_detail,
    get_benchmark_detail_items,
    get_benchmark_latest_for_hub,
    get_benchmark_rerun_params,
)


class BenchmarkDetailPaginationTest(unittest.TestCase):
    def test_paginate_first_and_second_page(self) -> None:
        items = [{"id": i, "answered": True, "passed": i % 2 == 0} for i in range(120)]
        detail = {"kind": "mmlu"}
        _paginate_detail_items(detail, items, offset=0)
        self.assertEqual(detail["raw_row_count"], 120)
        self.assertEqual(len(detail["results"]), DETAIL_ITEMS_PAGE_SIZE)
        self.assertTrue(detail["items_has_more"])
        self.assertEqual(detail["items_loaded"], DETAIL_ITEMS_PAGE_SIZE)

        page2 = dict(detail)
        _paginate_detail_items(page2, items, offset=DETAIL_ITEMS_PAGE_SIZE)
        self.assertEqual(len(page2["results"]), DETAIL_ITEMS_PAGE_SIZE)
        self.assertTrue(page2["items_has_more"])

    def test_mmlu_reference_detail_paginates(self) -> None:
        section = _build_reference_section()
        mmlu_row = next(r for r in section["reference_rows"] if r["key"] == "mmlu")
        slug = mmlu_row["cells"]["GPT 4.1 Mini"]["slug"]
        detail = get_benchmark_detail(slug)
        self.assertIsNotNone(detail)
        assert detail is not None
        if detail["raw_row_count"] <= DETAIL_ITEMS_PAGE_SIZE:
            self.skipTest("reference MMLU sample too small for pagination test")
        self.assertEqual(detail["items_loaded"], DETAIL_ITEMS_PAGE_SIZE)
        self.assertTrue(detail["items_has_more"])
        page2 = get_benchmark_detail_items(slug, DETAIL_ITEMS_PAGE_SIZE)
        self.assertIsNotNone(page2)
        assert page2 is not None
        self.assertGreater(len(page2["results"]), 0)


class MmluSubjectSortTest(unittest.TestCase):
    def test_weakest_subjects_first(self) -> None:
        rows = _per_subject_rows({
            "physics": {"accuracy": 0.9, "correct": 9, "total": 10},
            "history": {"accuracy": 0.2, "correct": 2, "total": 10},
            "math": {"accuracy": 0.5, "correct": 5, "total": 10},
        })
        self.assertEqual(rows[0]["subject"], "history")
        self.assertEqual(rows[-1]["subject"], "physics")

    def test_reference_detail_has_sorted_subjects(self) -> None:
        section = _build_reference_section()
        mmlu_row = next(r for r in section["reference_rows"] if r["key"] == "mmlu")
        slug = mmlu_row["cells"]["GPT 4.1 Mini"]["slug"]
        detail = get_benchmark_detail(slug)
        self.assertIsNotNone(detail)
        assert detail is not None
        rows = detail.get("per_subject_rows") or []
        self.assertGreater(len(rows), 1)
        accuracies = [r["accuracy"] for r in rows]
        self.assertEqual(accuracies, sorted(accuracies))


class BenchmarkRerunTest(unittest.TestCase):
    def test_rerun_params_from_reference_is_none(self) -> None:
        section = _build_reference_section()
        slug = section["reference_rows"][0]["cells"][section["reference_models"][0]]["slug"]
        self.assertIsNone(get_benchmark_rerun_params(slug))

    def test_attach_rerun_gateway_defaults(self) -> None:
        detail = {
            "kind": "mmlu",
            "model": "openai/GPT 4.1 Mini",
            "n": 100,
            "extras": {"attempted": 100},
        }
        _attach_rerun(detail)
        rerun = detail["rerun"]
        self.assertEqual(rerun["benchmark"], "mmlu")
        self.assertEqual(rerun["model_source"], "gateway")
        self.assertEqual(rerun["model"], "GPT 4.1 Mini")
        self.assertIsNone(rerun["sample"])
        self.assertIsNone(rerun["seed"])

    def test_attach_rerun_keeps_explicit_sample_and_seed(self) -> None:
        detail = {
            "slug": "20260706T120000Z_mmlu_test",
            "kind": "mmlu",
            "model": "gpt-5-nano",
            "run_params": {"sample": 100, "seed": 17},
        }
        _attach_rerun(detail)
        rerun = detail["rerun"]
        self.assertEqual(rerun["sample"], 100)
        self.assertEqual(rerun["seed"], 17)

    def test_parse_run_options_from_log(self) -> None:
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            slug = "20260706T181917Z_mmlu_gpt-5-nano"
            (base / f"{slug}.log").write_text(
                "=== command: python run_benchmark.py --benchmark mmlu "
                "--model gpt-5-nano --output-stem slug --sample 100 --seed 42 ===\n",
                encoding="utf-8",
            )
            with mock.patch("frontend.benchmark_data._candidate_dirs", return_value=[base]):
                opts = _load_stored_run_options(slug)
        self.assertEqual(opts["sample"], 100)
        self.assertEqual(opts["seed"], 42)

    def test_run_options_sidecar_takes_precedence_over_log(self) -> None:
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            slug = "20260706T181917Z_mmlu_gpt-5-nano"
            (base / f"{slug}.run_options.json").write_text(
                '{"sample": 50, "seed": 7}',
                encoding="utf-8",
            )
            (base / f"{slug}.log").write_text(
                "=== seed=99 ===\n",
                encoding="utf-8",
            )
            with mock.patch("frontend.benchmark_data._candidate_dirs", return_value=[base]):
                opts = _load_stored_run_options(slug)
        self.assertEqual(opts["sample"], 50)
        self.assertEqual(opts["seed"], 7)


class BenchmarkHubLatestTest(unittest.TestCase):
    def test_latest_from_runs_picks_newest_timestamp(self) -> None:
        runs = [
            {"timestamp_raw": "20260601T100000Z", "kind_label": "MMLU", "headline_display": "70%", "model": "A", "slug": "old"},
            {"timestamp_raw": "20260701T100000Z", "kind_label": "Consistency", "headline_display": "0.82", "model": "B", "slug": "new"},
        ]
        latest = get_benchmark_latest_for_hub(runs)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest["slug"], "new")
        self.assertEqual(latest["kind_label"], "Consistency")


if __name__ == "__main__":
    unittest.main()
