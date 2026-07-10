"""
Tests for the cross-pillar launch gates in frontend/pipeline.py.

Offline + deterministic: safety artifacts are written to a temp dir and
_safety_result_paths is patched to point at them (no real safety/output, no
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


class ValidateSafetyGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _patch_paths(self, *pairs) -> None:
        # pairs: (profile, payload) where payload is a dict (written as JSON),
        # the string "bad" (unreadable artifact), or None to omit that profile.
        result = []
        for i, (profile, payload) in enumerate(pairs):
            if payload is None:
                continue
            p = self.tmp / f"{profile}_{i}.json"
            p.write_text("{ not json" if payload == "bad" else json.dumps(payload),
                         encoding="utf-8")
            result.append((profile, p))
        m = mock.patch.object(pipeline, "_safety_result_paths", return_value=result)
        m.start()
        self.addCleanup(m.stop)

    def test_complete_low_tier_clears(self) -> None:
        self._patch_paths(("base", {"status": "complete", "composite_tier": "low"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertTrue(gate["ok"])
        self.assertIsNone(gate["error"])

    def test_complete_medium_tier_clears(self) -> None:
        # Medium clears — the gate blocks only high/critical.
        self._patch_paths(("base", {"status": "complete", "composite_tier": "medium"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertTrue(gate["ok"])

    def test_non_base_profile_clears(self) -> None:
        # A run under ANY profile approves — this "connects" a prior scanning
        # done under a specialized red-team profile, not just "base".
        self._patch_paths(("education", {"status": "complete", "composite_tier": "low"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertTrue(gate["ok"])
        self.assertEqual(gate["profile"], "education")

    def test_any_cleared_profile_wins_over_a_high_one(self) -> None:
        # One high-risk profile + one medium profile -> approved (a profile
        # cleared it).
        self._patch_paths(
            ("base", {"status": "complete", "composite_tier": "high"}),
            ("finance", {"status": "complete", "composite_tier": "medium"}),
        )
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertTrue(gate["ok"])
        self.assertEqual(gate["profile"], "finance")

    def test_critical_tier_blocks(self) -> None:
        self._patch_paths(("base", {"status": "complete", "composite_tier": "critical"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertIn("high risk", gate["error"])

    def test_no_runs_blocks_with_none_status(self) -> None:
        self._patch_paths()  # no profiles at all
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertIsNone(gate["status"])
        self.assertIn("safety red-teaming required", gate["error"])

    def test_incomplete_status_blocks(self) -> None:
        self._patch_paths(("base", {"status": "running", "composite_tier": "low"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertIn("not complete", gate["error"])

    def test_present_but_missing_status_blocks(self) -> None:
        # No status key -> defaults to "unknown" -> not complete -> blocked.
        self._patch_paths(("base", {"composite_tier": "low"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertEqual(gate["status"], "unknown")
        self.assertIn("not complete", gate["error"])

    def test_high_tier_blocks(self) -> None:
        self._patch_paths(("base", {"status": "complete", "composite_tier": "high"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertIn("high risk", gate["error"])

    def test_unreadable_blocks(self) -> None:
        self._patch_paths(("base", "bad"))
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
