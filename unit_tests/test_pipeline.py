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

    def test_present_but_missing_status_blocks(self) -> None:
        # A low-tier artifact with no `status` key must fail closed (defaults to
        # "unknown" -> not complete -> blocked), never clear on the absent field.
        self._patch_path(_write_safety(self.tmp, {"composite_tier": "low"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertEqual(gate["status"], "unknown")
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
        # A corrupt-but-present artifact reads as "blocked" (non-None status),
        # not "missing", on the /pipeline badge.
        self.assertEqual(gate["status"], "unreadable")
        self.assertEqual(pipeline._gate_stage(gate)["state"], "blocked")


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


class StageStateTest(unittest.TestCase):
    def test_gateway_cleared_unlocks_eval(self) -> None:
        with mock.patch.object(
            pipeline, "validate_safety_gate",
            return_value={"ok": True, "error": None, "status": "complete"},
        ):
            st = pipeline.stage_state("Llama 4 Maverick", "gateway")
        self.assertEqual(st["scan"]["state"], "n/a")
        self.assertEqual(st["safety"]["state"], "cleared")
        self.assertTrue(st["eval_unlocked"])

    def test_gateway_missing_safety_is_missing_and_locked(self) -> None:
        with mock.patch.object(
            pipeline, "validate_safety_gate",
            return_value={"ok": False, "error": "run safety", "status": None},
        ):
            st = pipeline.stage_state("Llama 4 Maverick", "gateway")
        self.assertEqual(st["safety"]["state"], "missing")
        self.assertFalse(st["eval_unlocked"])

    def test_gateway_blocked_tier_is_blocked(self) -> None:
        with mock.patch.object(
            pipeline, "validate_safety_gate",
            return_value={"ok": False, "error": "tier high", "status": "complete"},
        ):
            st = pipeline.stage_state("Llama 4 Maverick", "gateway")
        self.assertEqual(st["safety"]["state"], "blocked")
        self.assertFalse(st["eval_unlocked"])

    def test_hf_scan_cleared_safety_unsupported(self) -> None:
        with mock.patch(
            "frontend.eval_launch.validate_hf_scan_gate",
            return_value={"ok": True, "error": None, "status": "complete"},
        ):
            st = pipeline.stage_state("Qwen/Qwen2.5-7B-Instruct", "hf")
        self.assertEqual(st["scan"]["state"], "cleared")
        self.assertEqual(st["safety"]["state"], "unsupported")
        self.assertTrue(st["eval_unlocked"])


class BuildOverviewTest(unittest.TestCase):
    def test_rows_from_gateway_and_scans(self) -> None:
        with mock.patch(
            "gateway.catalog.get_gateway_catalog",
            return_value={"models": [{"id": "Llama 4 Maverick", "category": "general_chat"}]},
        ), mock.patch(
            "frontend.scan_data.get_scans_data",
            return_value={"scans": [{"model_id": "Qwen/Qwen2.5-7B-Instruct", "slug": "Qwen--Qwen2.5-7B-Instruct"}]},
        ), mock.patch.object(
            pipeline, "validate_safety_gate",
            return_value={"ok": False, "error": "run safety", "status": None},
        ), mock.patch(
            "frontend.eval_launch.validate_hf_scan_gate",
            return_value={"ok": True, "error": None, "status": "complete"},
        ):
            ov = pipeline.build_overview()
        self.assertTrue(ov["has_rows"])
        self.assertEqual({r["source"] for r in ov["rows"]}, {"gateway", "hf"})


from frontend import create_app  # noqa: E402  (top-of-file group is fine too)


class PipelineRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = create_app({"TESTING": True}).test_client()

    def test_pipeline_page_renders_empty(self) -> None:
        with mock.patch("frontend.pipeline.build_overview",
                        return_value={"rows": [], "has_rows": False}):
            r = self.client.get("/pipeline")
        self.assertEqual(r.status_code, 200)

    def test_pipeline_page_lists_models(self) -> None:
        rows = [
            {"model": "Llama 4 Maverick", "source": "gateway",
             "scan": {"state": "n/a", "detail": ""},
             "safety": {"state": "missing", "detail": "run safety"},
             "eval_unlocked": False},
        ]
        with mock.patch("frontend.pipeline.build_overview",
                        return_value={"rows": rows, "has_rows": True}):
            r = self.client.get("/pipeline")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Llama 4 Maverick", r.data)
