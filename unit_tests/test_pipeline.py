"""
Tests for the cross-pillar launch gates in frontend/pipeline.py.

Offline + deterministic: safety artifacts are written to a temp dir and
_safety_result_path is patched to point at them (no real safety/output, no
dependency on normalize_gateway_model_id here).

Run from repo root:
  uv run python -m unittest unit_tests.test_pipeline -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frontend import pipeline


def _write_safety(tmp: Path, payload: dict) -> Path:
    p = tmp / "merged_safety_result.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


class ValidateSafetyGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _patch_path(self, path: Path) -> None:
        p = mock.patch.object(pipeline, "_safety_result_path", return_value=path)
        p.start()
        self.addCleanup(p.stop)

    def test_complete_low_tier_clears(self) -> None:
        self._patch_path(_write_safety(self.tmp, {"status": "complete", "composite_tier": "low"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertTrue(gate["ok"])
        self.assertIsNone(gate["error"])

    def test_missing_file_blocks_with_none_status(self) -> None:
        self._patch_path(self.tmp / "does_not_exist.json")
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertIsNone(gate["status"])
        self.assertIn("safety red-teaming required", gate["error"])

    def test_incomplete_status_blocks(self) -> None:
        self._patch_path(_write_safety(self.tmp, {"status": "running", "composite_tier": "low"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertIn("not complete", gate["error"])

    def test_high_tier_blocks(self) -> None:
        self._patch_path(_write_safety(self.tmp, {"status": "complete", "composite_tier": "high"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertIn("did not clear", gate["error"])

    def test_unreadable_blocks(self) -> None:
        path = self.tmp / "merged_safety_result.json"
        path.write_text("{ not json", encoding="utf-8")
        self._patch_path(path)
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertIn("unreadable", gate["error"])


class RequireReadyTest(unittest.TestCase):
    def test_gateway_cleared_returns_none(self) -> None:
        with mock.patch.object(pipeline, "validate_safety_gate",
                               return_value={"ok": True, "error": None}):
            self.assertIsNone(
                pipeline.require_ready_for_downstream("Llama 4 Maverick", "gateway")
            )

    def test_gateway_blocked_returns_error(self) -> None:
        with mock.patch.object(pipeline, "validate_safety_gate",
                               return_value={"ok": False, "error": "no safety run"}):
            self.assertEqual(
                pipeline.require_ready_for_downstream("Llama 4 Maverick", "gateway"),
                "no safety run",
            )

    def test_hf_scan_cleared_returns_none(self) -> None:
        with mock.patch("frontend.eval_launch.validate_hf_scan_gate",
                        return_value={"ok": True, "error": None}):
            self.assertIsNone(
                pipeline.require_ready_for_downstream("Qwen/Qwen2.5-7B-Instruct", "hf")
            )

    def test_hf_scan_blocked_returns_error(self) -> None:
        with mock.patch("frontend.eval_launch.validate_hf_scan_gate",
                        return_value={"ok": False, "error": "scan required"}):
            self.assertEqual(
                pipeline.require_ready_for_downstream("Qwen/Qwen2.5-7B-Instruct", "hf"),
                "scan required",
            )
