"""
Cross-pillar launch gates: a model must clear the earlier pillars before it can
be evaluated or benchmarked.

Read-only over the scanner + safety artifacts. This module never runs, edits, or
imports the pillars' launch code at import time — every pillar import is lazy
(inside a function), matching frontend/routes.py. "Cleared" is defined once here
and mirrors the scanner gate in eval_launch.validate_hf_scan_gate: a completed
artifact whose headline tier is 'low'.

Source-aware:
  gateway model -> nothing to scan (N/A); must clear safety red-teaming.
  hf repo       -> must clear the artifact scan; safety red-teaming is not yet
                   supported for served HF models (out of scope), so it is not
                   required for HF.
"""

from __future__ import annotations

import json
from pathlib import Path

from markupsafe import escape

ROOT = Path(__file__).parent.parent
SAFETY_OUTPUT_DIR = ROOT / "safety" / "output"

CLEARED_TIER = "low"
COMPLETE_STATUSES = frozenset({"complete", "completed"})
DEFAULT_SAFETY_PROFILE = "base"


def _safety_result_path(model: str, profile: str = DEFAULT_SAFETY_PROFILE) -> Path:
    """Published safety artifact for a gateway model id (read-only)."""
    from safety.gateway_ids import normalize_gateway_model_id
    from safety.merged_paths import merged_result_path

    slug = normalize_gateway_model_id(model)
    return merged_result_path(SAFETY_OUTPUT_DIR, slug, profile)


def validate_safety_gate(model: str, *, profile: str = DEFAULT_SAFETY_PROFILE) -> dict:
    """Require a completed, low-tier safety run before eval/benchmark.

    Mirrors eval_launch.validate_hf_scan_gate: only a completed run whose
    composite_tier is 'low' clears the gate. Reflected values are HTML-escaped
    (errors render as HTML).
    """
    path = _safety_result_path(model, profile)
    base = {
        "model": model,
        "profile": profile,
        "path": str(path),
        "status": None,
        "tier": None,
    }
    if not path.is_file():
        return {
            **base,
            "ok": False,
            "error": (
                "safety red-teaming required before this step; run safety for "
                f"'{escape(model)}' first, then retry"
            ),
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — malformed artifact must never 500
        return {
            **base,
            "ok": False,
            "error": f"safety result is unreadable: {type(e).__name__}: {e}",
        }

    status = str(data.get("status") or "unknown").lower()
    tier = str(data.get("composite_tier") or "unknown").lower()
    out = {**base, "status": status, "tier": tier}
    if status not in COMPLETE_STATUSES:
        return {**out, "ok": False,
                "error": f"safety run is not complete yet (status={status})"}
    if tier != CLEARED_TIER:
        return {
            **out,
            "ok": False,
            "error": (
                "safety red-teaming did not clear this model "
                f"(tier={tier}); eval/benchmark is blocked"
            ),
        }
    return {**out, "ok": True, "error": None}


def require_ready_for_downstream(model: str, source: str) -> str | None:
    """Hard-block gate reused by eval + benchmark. Returns the blocking error
    message, or None when the model may proceed.

    gateway: safety must be cleared (scan is N/A).
    hf:      scan must be cleared (safety not yet supported for served HF models).
    """
    if source == "hf":
        # Lazy import breaks the pipeline <-> eval_launch cycle.
        from frontend.eval_launch import validate_hf_scan_gate

        gate = validate_hf_scan_gate(model)
        return None if gate["ok"] else gate["error"]

    gate = validate_safety_gate(model)
    return None if gate["ok"] else gate["error"]
