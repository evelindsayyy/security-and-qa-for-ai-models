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
            # Non-None status so the /pipeline badge reads "blocked" (a present
            # but corrupt artifact), not "missing" (no run at all). The gate
            # still fails closed either way.
            "status": "unreadable",
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


def _gate_stage(gate: dict) -> dict:
    """Map a gate verdict to a display stage. `status is None` means the
    artifact was absent (missing) vs. present-but-failing (blocked)."""
    if gate["ok"]:
        return {"state": "cleared", "detail": ""}
    if gate.get("status") is None:
        return {"state": "missing", "detail": gate["error"]}
    return {"state": "blocked", "detail": gate["error"]}


def stage_state(model: str, source: str) -> dict:
    """Per-model pipeline state for the /pipeline view (read-only)."""
    if source == "hf":
        # Lazy import breaks the pipeline <-> eval_launch cycle.
        from frontend.eval_launch import validate_hf_scan_gate

        scan_gate = validate_hf_scan_gate(model)
        return {
            "model": model,
            "source": source,
            "scan": _gate_stage(scan_gate),
            "safety": {
                "state": "unsupported",
                "detail": "safety red-teaming not yet supported for served HF models",
            },
            "eval_unlocked": scan_gate["ok"],
        }

    safety_gate = validate_safety_gate(model)
    return {
        "model": model,
        "source": source,
        "scan": {"state": "n/a", "detail": "nothing to scan (API endpoint)"},
        "safety": _gate_stage(safety_gate),
        "eval_unlocked": safety_gate["ok"],
    }


def build_overview() -> dict:
    """All gateway models + every HF repo that already has a scan, each with its
    pipeline stage state. Degrades gracefully if a data source is unavailable."""
    rows: list[dict] = []
    try:
        from gateway.catalog import get_gateway_catalog

        for m in get_gateway_catalog().get("models", []):
            rows.append(stage_state(m["id"], "gateway"))
    except Exception:  # noqa: BLE001 — a catalog hiccup must not 500 the page
        pass
    try:
        from frontend.scan_data import get_scans_data

        for s in get_scans_data().get("scans", []):
            repo = s.get("model_id")
            if repo:
                rows.append(stage_state(repo, "hf"))
    except Exception:  # noqa: BLE001
        pass
    return {"rows": rows, "has_rows": bool(rows)}
