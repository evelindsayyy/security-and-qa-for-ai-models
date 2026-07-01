import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "frontend"))

from benchmark_data import (  # noqa: E402
    REFERENCE_DIR,
    _build_reference_section,
    _coverage_info,
    _load_reference_summaries,
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
        tqa = next(r for r in section["reference_rows"] if r["key"] == "truthfulqa")
        self.assertTrue(tqa["score_hint"])
        self.assertGreaterEqual(len(tqa["score_hint_sources"]), 1)
        self.assertIn("url", tqa["score_hint_sources"][0])

    def test_reference_page_data(self) -> None:
        data = get_benchmark_reference_data()
        self.assertTrue(data["has_reference"])
        self.assertIn("coverage_skip_explanation", data)
        self.assertEqual(len(data["guide_rows"]), 7)

    def test_benchmark_guide_rows(self) -> None:
        guide = get_benchmark_guide_data()
        self.assertEqual(len(guide["guide_rows"]), 7)
        tqa = next(r for r in guide["guide_rows"] if r["key"] == "truthfulqa")
        self.assertTrue(tqa["procedure"])
        self.assertTrue(tqa["scoring"])
        self.assertEqual(tqa["headline_metric"], "accuracy")
        self.assertEqual(tqa["default_sample"], 50)

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

    def test_reference_detail_includes_score_hint_sources(self) -> None:
        section = _build_reference_section()
        tqa_cell = next(
            row["cells"]["GPT 4.1 Mini"]
            for row in section["reference_rows"]
            if row["key"] == "truthfulqa"
        )
        detail = get_benchmark_detail(tqa_cell["slug"])
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertGreaterEqual(len(detail["meta"].get("score_hint_sources") or []), 1)


if __name__ == "__main__":
    unittest.main()
