"""
Tests for benchmark launch + data layer (no subprocess, no API calls).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import benchmark_data, benchmark_launch  # noqa: E402


class BenchmarkLaunchValidateTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(
            benchmark_launch,
            "candidate_models",
            return_value=("GPT 4.1 Mini", "gpt-5-chat"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_valid_launch(self) -> None:
        self.assertIsNone(
            benchmark_launch.validate_launch("truthfulqa", "GPT 4.1 Mini")
        )

    def test_unknown_benchmark_rejected(self) -> None:
        err = benchmark_launch.validate_launch("not-a-benchmark", "GPT 4.1 Mini")
        self.assertIn("unknown benchmark", err)

    def test_unknown_model_rejected(self) -> None:
        err = benchmark_launch.validate_launch("truthfulqa", "evil-model")
        self.assertIn("not in allowlist", err)


class BenchmarkLaunchCommandTest(unittest.TestCase):
    def test_build_command_argv(self) -> None:
        cmd = benchmark_launch.build_command("ifeval", "GPT 4.1 Mini", "stem123")
        self.assertIsInstance(cmd, list)
        self.assertIn("--benchmark", cmd)
        self.assertIn("ifeval", cmd)
        self.assertIn("--output-stem", cmd)
        self.assertIn("stem123", cmd)


class BenchmarkDataTest(unittest.TestCase):
    def test_detect_truthfulqa_from_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.json"
            path.write_text(
                json.dumps(
                    {
                        "model": "GPT 4.1 Mini",
                        "timestamp": "20260611_120000",
                        "metrics": {"accuracy": 0.8, "total_evaluated": 10, "correct": 8},
                        "responses": [{"question": "q"}],
                    }
                ),
                encoding="utf-8",
            )
            row = benchmark_data._summarize_file(path)
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row["kind"], "truthfulqa")
            self.assertEqual(row["model"], "GPT 4.1 Mini")

    def test_get_benchmarks_data_includes_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            primary = Path(tmp)
            path = primary / "tqa_test.json"
            path.write_text(
                json.dumps(
                    {
                        "model": "gpt-5-chat",
                        "timestamp": "20260611_120000",
                        "metrics": {"accuracy": 0.5, "total_evaluated": 2, "correct": 1},
                        "responses": [{}, {}],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(benchmark_data, "PRIMARY_DIR", primary), mock.patch.object(
                benchmark_data, "_candidate_dirs", return_value=[primary]
            ):
                data = benchmark_data.get_benchmarks_data()
            self.assertTrue(data["has_runs"])
            self.assertIn("TruthfulQA", data["kinds"])
            self.assertIn("gpt-5-chat", data["models"])

    def test_detail_includes_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            primary = Path(tmp)
            path = primary / "tqa_test.json"
            path.write_text(
                json.dumps(
                    {
                        "model": "gpt-5-chat",
                        "timestamp": "20260611_120000",
                        "metrics": {"accuracy": 0.5, "total_evaluated": 1, "correct": 1},
                        "responses": [{"question": "Q?", "correct_letter": "A", "model_answer": "A"}],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(benchmark_data, "PRIMARY_DIR", primary), mock.patch.object(
                benchmark_data, "_candidate_dirs", return_value=[primary]
            ):
                detail = benchmark_data.get_benchmark_detail("tqa_test")
            self.assertIsNotNone(detail)
            assert detail is not None
            self.assertIn("about", detail["meta"])
            self.assertEqual(detail["meta"]["title"], "TruthfulQA")

    def test_consistency_detail_uses_bertscore_f1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            primary = Path(tmp)
            path = primary / "consistency_test.json"
            path.write_text(
                json.dumps(
                    {
                        "model": "gpt-5-chat",
                        "timestamp": "20260611_120000",
                        "summary": {"total_questions": 1, "mean_f1_overall": 0.85},
                        "questions": [
                            {
                                "id": "q1",
                                "topic": "AI",
                                "paraphrases": ["Q1?", "Q1 rephrased?"],
                                "responses": ["A1", "A2"],
                                "bertscore": {"mean_f1": 0.85, "min_f1": 0.8, "pairs": []},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(benchmark_data, "PRIMARY_DIR", primary), mock.patch.object(
                benchmark_data, "_candidate_dirs", return_value=[primary]
            ):
                detail = benchmark_data.get_benchmark_detail("consistency_test")
            self.assertIsNotNone(detail)
            assert detail is not None
            self.assertEqual(detail["questions"][0]["bertscore"]["mean_f1"], 0.85)


if __name__ == "__main__":
    unittest.main()
