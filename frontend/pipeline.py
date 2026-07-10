"""
Cross-pillar launch gates: a model must clear the earlier pillars before it can
be evaluated or benchmarked.

Read-only over the scanner + safety artifacts. This module never runs, edits, or
imports the pillars' launch code at import time — every pillar import is lazy
(inside a function), matching frontend/routes.py. "Cleared" is defined once here
and mirrors the scanner gate in eval_launch.validate_hf_scan_gate: any completed
safety run (under any red-team profile) whose headline tier isn't high/critical.

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

# A completed safety run clears the gate unless it flagged the model as high
# risk. Blocking only high/critical (not medium) keeps the gate meaningful
# while letting normal models through — most gateway models score medium, so a
# low-only bar blocks nearly every eval in practice.
CLEARED_TIERS = frozenset({"low", "medium"})
COMPLETE_STATUSES = frozenset({"complete", "completed"})


def _safety_result_paths(model: str) -> list[tuple[str, Path]]:
    """(profile, merged-result path) for every red-team profile this gateway
    model has a run under — ``safety/output/<slug>/<profile>/…`` plus the legacy
    profile-less path. Read-only; private per-user copies (``.private/``) are
    ignored (the gate reads the public results)."""
    from safety.gateway_ids import normalize_gateway_model_id

    slug = normalize_gateway_model_id(model)
    model_dir = SAFETY_OUTPUT_DIR / slug
    out: list[tuple[str, Path]] = []
    if not model_dir.is_dir():
        return out
    legacy = model_dir / "merged_safety_result.json"
    if legacy.is_file():
        out.append(("base", legacy))
    for prof_dir in sorted(model_dir.iterdir()):
        if prof_dir.is_dir() and not prof_dir.name.startswith("."):
            mp = prof_dir / "merged_safety_result.json"
            if mp.is_file():
                out.append((prof_dir.name, mp))
    return out


def validate_safety_gate(model: str) -> dict:
    """Approve a model that has ANY completed, non-high-risk safety run in
    history — under any red-team profile (base, education, finance, …).

    This "connects" previous scannings: once red-teaming has run and did not flag
    the model high/critical, the eval is approved without re-running. A model
    whose only completed runs are high/critical is blocked; a model with no
    completed run at all still needs safety. Reflected values are HTML-escaped.
    """
    base = {"model": model, "profile": None, "status": None, "tier": None}
    paths = _safety_result_paths(model)
    if not paths:
        return {
            **base,
            "ok": False,
            "error": (
                "safety red-teaming required before this step; run safety for "
                f"'{escape(model)}' first, then retry"
            ),
        }

    # Approve on the first completed non-high-risk run; otherwise keep the most
    # informative block reason (a completed high-risk run beats an in-progress
    # or unreadable one).
    block: dict | None = None
    for profile, mp in paths:
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a corrupt artifact must never 500
            block = block or {
                **base, "profile": profile, "status": "unreadable", "ok": False,
                "error": f"safety result is unreadable ({escape(profile)} profile)",
            }
            continue
        status = str(data.get("status") or "unknown").lower()
        tier = str(data.get("composite_tier") or "unknown").lower()
        out = {**base, "profile": profile, "status": status, "tier": tier}
        if status not in COMPLETE_STATUSES:
            block = block or {**out, "ok": False,
                              "error": f"safety run is not complete yet (status={status})"}
            continue
        if tier not in CLEARED_TIERS:
            block = {**out, "ok": False,
                     "error": ("safety red-teaming flagged this model as high risk "
                               f"(tier={tier}); eval/benchmark is blocked")}
            continue
        return {**out, "ok": True, "error": None}

    return block  # non-None: a non-empty paths list always sets a block reason


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
