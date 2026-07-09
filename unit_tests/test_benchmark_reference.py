import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "frontend"))

from benchmark_data import (  # noqa: E402
    REFERENCE_DIR,
    _attach_reference_comparison,
    _build_reference_section,
    _coverage_info,
    _format_reference_delta,
    _load_reference_summaries,
    _reference_by_kind_model,
    _score_class,
    get_benchmark_detail,
    get_benchmark_guide_data,
    get_benchmark_reference_data,
    is_reference_slug,
)


class TestBenchmarkReference(unittest.TestCase):
    def test_reference_dir_has_files(self) -> None:
        self.assertTrue(REFERENCE_DIR.is_dir(), f"missing {REFERENCE_DIR}")
        summaries = _load_reference_summaries()
        self.assertGreaterEqual(len(summaries), 10)

    def test_reference_section_matrix(self) -> None:
        section = _build_reference_section()
        self.assertTrue(section["has_reference"])
        self.assertIn("GPT 4.1 Mini", section["reference_models"])
        self.assertIn("Llama 3.3", section["reference_models"])
        keys = {row["key"] for row in section["reference_rows"]}
        self.assertIn("truthfulqa", keys)
        self.assertIn("mmlu", keys)
        self.assertIn("ifeval", keys)
        self.assertEqual(len(section["reference_rows"]), 7)

    def test_reference_page_data(self) -> None:
        data = get_benchmark_reference_data()
        self.assertTrue(data["has_reference"])
        self.assertIn("coverage_skip_explanation", data)
        self.assertEqual(len(data["guide_rows"]), 7)

    def test_benchmark_guide_rows(self) -> None:
        guide = get_benchmark_guide_data()
        self.assertEqual(len(guide["guide_rows"]), 7)
        self.assertIn("coverage_n_explanation", guide)
        self.assertTrue(guide["coverage_n_explanation"])
        tqa = next(r for r in guide["guide_rows"] if r["key"] == "truthfulqa")
        self.assertTrue(tqa["procedure"])
        self.assertTrue(tqa["scoring"])
        self.assertEqual(tqa["headline_metric"], "accuracy")
        self.assertEqual(tqa["default_sample"], 50)
        self.assertNotIn("score_hint", tqa)

    def test_mmlu_reference_shows_partial_coverage(self) -> None:
        section = _build_reference_section()
        mmlu_row = next(r for r in section["reference_rows"] if r["key"] == "mmlu")
        cell = mmlu_row["cells"].get("GPT 4.1 Mini")
        self.assertIsNotNone(cell)
        assert cell is not None
        self.assertTrue(cell["coverage"]["partial"])
        self.assertEqual(cell["coverage"]["n_display"], "99/100")

    def test_score_class_uses_per_benchmark_bands(self) -> None:
        self.assertEqual(_score_class("mmlu", 0.72), "score-weak")
        self.assertEqual(_score_class("mmlu", 0.85), "score-mid")
        self.assertEqual(_score_class("mmlu", 0.92), "score-strong")
        self.assertEqual(_score_class("consistency", 0.80), "score-mid")

    def test_coverage_info_complete_run(self) -> None:
        cov = _coverage_info({"n": 100, "extras": {}})
        self.assertFalse(cov["partial"])
        self.assertEqual(cov["n_display"], "100")

    def test_format_reference_delta(self) -> None:
        self.assertEqual(_format_reference_delta("mmlu", 0.055), "+5.5 pp")
        self.assertEqual(_format_reference_delta("consistency", 0.032), "+0.032")

    def test_reference_comparison_for_user_run(self) -> None:
        ref = _reference_by_kind_model()["mmlu"]["GPT 4.1 Mini"]
        user = {
            "kind": "mmlu",
            "model": "openai/GPT 4.1 Mini",
            "headline_value": ref["headline_value"] + 0.05,
            "headline_metric": "accuracy",
        }
        out = _attach_reference_comparison(user)
        comparisons = out["reference_comparisons"]
        self.assertEqual(len(comparisons), 1)
        cmp = comparisons[0]
        self.assertTrue(cmp["exact_match"])
        self.assertAlmostEqual(cmp["delta_value"], 0.05)
        self.assertEqual(cmp["delta_display"], "+5.0 pp")
        self.assertEqual(cmp["slug"], ref["slug"])
        self.assertEqual(cmp["delta_class"], "ref-delta-up")

    def test_reference_comparison_for_other_model(self) -> None:
        ref = _reference_by_kind_model()["consistency"]["GPT 4.1 Mini"]
        user = {
            "kind": "consistency",
            "model": "gpt-5-codex",
            "headline_value": 0.817,
            "headline_metric": "mean F1",
        }
        out = _attach_reference_comparison(user)
        comparisons = out["reference_comparisons"]
        self.assertGreaterEqual(len(comparisons), 1)
        cmp = comparisons[0]
        self.assertFalse(cmp["exact_match"])
        self.assertEqual(cmp["model"], "GPT 4.1 Mini")
        self.assertAlmostEqual(cmp["delta_value"], 0.817 - ref["headline_value"])

    def test_reference_comparison_omitted_for_reference_run(self) -> None:
        section = _build_reference_section()
        mmlu_cell = next(
            row["cells"]["GPT 4.1 Mini"]
            for row in section["reference_rows"]
            if row["key"] == "mmlu"
        )
        detail = get_benchmark_detail(mmlu_cell["slug"])
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertNotIn("reference_comparisons", detail)

    def test_reference_detail_loads_with_coverage(self) -> None:
        section = _build_reference_section()
        mmlu_cell = next(
            row["cells"]["GPT 4.1 Mini"]
            for row in section["reference_rows"]
            if row["key"] == "mmlu"
        )
        slug = mmlu_cell["slug"]
        self.assertTrue(is_reference_slug(slug))
        detail = get_benchmark_detail(slug)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertTrue(detail.get("is_reference"))
        self.assertIn("meta", detail)
        self.assertTrue(detail["coverage"]["partial"])
        self.assertEqual(detail["coverage"]["failed"], 1)
        skipped = [r for r in detail["results"] if not r.get("answered")]
        self.assertEqual(len(skipped), 1)

    def test_launch_options_include_benchmark_descriptions(self) -> None:
        from frontend.benchmark_launch import get_launch_options

        opts = get_launch_options()
        self.assertIn("coverage_n_explanation", opts)
        tqa = opts["benchmark_options"]["truthfulqa"]
        self.assertTrue(tqa.get("about"))
        self.assertEqual(tqa.get("headline_metric"), "accuracy")
        self.assertEqual(tqa.get("default_sample"), 50)


if __name__ == "__main__":
    unittest.main()
