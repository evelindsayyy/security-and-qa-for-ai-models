"""
Tests for pillar result deletion (scan, safety, eval).

  uv run python -m unittest unit_tests.test_result_delete -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from frontend.eval_run_data import delete_eval_run  # noqa: E402
from frontend.safety_data import delete_safety  # noqa: E402
from frontend.scan_data import delete_scan  # noqa: E402


class DeleteScanTest(unittest.TestCase):
    def test_blocks_while_running(self) -> None:
        with mock.patch("frontend.scan_launch.inflight_scan_slugs", return_value={"my-slug"}):
            err = delete_scan("my-slug")
        self.assertIn("in progress", err or "")

    def test_deletes_scan_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            slug = "test-model"
            scan_dir = out / slug
            scan_dir.mkdir()
            (scan_dir / "scan_result.json").write_text(
                json.dumps({"model_id": "org/model", "scan_metadata": {"scanned_at": "2026-01-01T00:00:00Z"}}),
                encoding="utf-8",
            )
            with mock.patch("frontend.scan_data.OUTPUT_DIR", out), mock.patch(
                "frontend.scan_launch.inflight_scan_slugs", return_value=set()
            ), mock.patch("frontend.scan_db_data.available", return_value=False):
                self.assertIsNone(delete_scan(slug))
                self.assertFalse(scan_dir.exists())


class DeleteSafetyTest(unittest.TestCase):
    def test_blocks_while_running(self) -> None:
        with mock.patch(
            "frontend.safety_launch.inflight_safety_keys", return_value={"slug/base"}
        ):
            err = delete_safety("slug", "base")
        self.assertIn("in progress", err or "")

    def test_deletes_profile_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            slug, profile = "gpt-4", "base"
            prof_dir = out / slug / profile
            prof_dir.mkdir(parents=True)
            (prof_dir / "merged_safety_result.json").write_text(
                json.dumps({"gateway_model_id": "GPT 4", "completed_at": "2026-01-01T00:00:00Z"}),
                encoding="utf-8",
            )
            with mock.patch("frontend.safety_data.OUTPUT_DIR", out), mock.patch(
                "frontend.safety_data.ROOT", out
            ), mock.patch("frontend.safety_launch.inflight_safety_keys", return_value=set()), mock.patch(
                "frontend.safety_db_data.available", return_value=False
            ):
                self.assertIsNone(delete_safety(slug, profile))
                self.assertFalse(prof_dir.exists())


class DeleteEvalRunTest(unittest.TestCase):
    def test_blocks_while_running(self) -> None:
        with mock.patch("frontend.eval_launch.is_eval_run_in_progress", return_value=True):
            err = delete_eval_run("my-slug")
        self.assertIn("in progress", err or "")

    def test_deletes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            slug = "20260101T120000Z_test"
            for suffix in (".jsonl", ".log", "_trace.jsonl"):
                (results / f"{slug}{suffix}").write_text("x", encoding="utf-8")
            with mock.patch("frontend.eval_run_data.RESULTS_DIR", results), mock.patch(
                "frontend.eval_launch.is_eval_run_in_progress", return_value=False
            ), mock.patch("frontend.eval_db_data.available", return_value=False):
                self.assertIsNone(delete_eval_run(slug))
                self.assertEqual(list(results.glob(f"{slug}*")), [])


if __name__ == "__main__":
    unittest.main()
