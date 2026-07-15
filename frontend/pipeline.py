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
    try:
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
    except OSError:
        # Unreadable artifacts — e.g. a deploy-time file owned by another user
        # with restrictive perms (PermissionError from is_file()/iterdir()) —
        # must not abort the whole pipeline listing. Return whatever resolved so
        # far; the DB/UI catalog (tried first) still supplies cleared runs, and
        # the gate otherwise reports "missing".
        return out
    return out


def _safety_runs_from_ui_catalog(model: str) -> list[dict]:
    """Safety runs for *model* from the same source as ``/safety`` (DB or disk).

    Matches on normalized gateway id so ``Llama 4 Scout`` and ``llama-4-scout``
    resolve the same way the Safety list page does.
    """
    from safety.gateway_ids import normalize_gateway_model_id

    slug = normalize_gateway_model_id(model)
    try:
        from frontend.safety_data import get_safety_data

        rows = get_safety_data().get("models") or []
    except Exception:  # noqa: BLE001 — catalog hiccup must not block the gate
        return []
    matched: list[dict] = []
    for row in rows:
        gid = str(row.get("gateway_model_id") or row.get("slug") or "")
        if normalize_gateway_model_id(gid) != slug:
            continue
        matched.append(
            {
                "profile": row.get("profile") or "base",
                "status": str(row.get("status") or "unknown").lower(),
                "tier": str(row.get("tier") or row.get("composite_tier") or "unknown").lower(),
            }
        )
    return matched


def _safety_runs_from_disk(model: str) -> list[dict]:
    """Public on-disk merged results (also covers not-yet-ingested runs)."""
    out: list[dict] = []
    for profile, path in _safety_result_paths(model):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            out.append(
                {
                    "profile": profile,
                    "status": "unreadable",
                    "tier": "unknown",
                    "unreadable": True,
                }
            )
            continue
        out.append(
            {
                "profile": profile,
                "status": str(data.get("status") or "unknown").lower(),
                "tier": str(data.get("composite_tier") or "unknown").lower(),
            }
        )
    return out


def _collect_safety_runs(model: str) -> list[dict]:
    """UI catalog first (matches /safety), then any extra public disk artifacts."""
    by_profile: dict[str, dict] = {}
    for run in _safety_runs_from_ui_catalog(model) + _safety_runs_from_disk(model):
        profile = str(run.get("profile") or "base")
        # Prefer an already-cleared catalog row over a stale disk copy.
        existing = by_profile.get(profile)
        if existing is None:
            by_profile[profile] = run
            continue
        if existing.get("status") in COMPLETE_STATUSES and existing.get("tier") in CLEARED_TIERS:
            continue
        by_profile[profile] = run
    return list(by_profile.values())


def validate_safety_gate(model: str) -> dict:
    """Approve a model that has ANY completed, non-high-risk safety run in
    history — under any red-team profile (base, education, finance, …).

    Uses the same evidence the Safety UI shows (Postgres when configured,
    otherwise on-disk merged results), plus any public disk artifacts not yet
    ingested. A model whose only completed runs are high/critical is blocked;
    a model with no completed run at all still needs safety. Reflected values
    are HTML-escaped.
    """
    base = {"model": model, "profile": None, "status": None, "tier": None}
    runs = _collect_safety_runs(model)
    if not runs:
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
    for run in runs:
        profile = run.get("profile") or "base"
        if run.get("unreadable"):
            block = block or {
                **base,
                "profile": profile,
                "status": "unreadable",
                "ok": False,
                "error": f"safety result is unreadable ({escape(profile)} profile)",
            }
            continue
        status = str(run.get("status") or "unknown").lower()
        tier = str(run.get("tier") or "unknown").lower()
        out = {**base, "profile": profile, "status": status, "tier": tier}
        if status not in COMPLETE_STATUSES:
            block = block or {
                **out,
                "ok": False,
                "error": f"safety run is not complete yet (status={status})",
            }
            continue
        if tier not in CLEARED_TIERS:
            block = {
                **out,
                "ok": False,
                "error": (
                    "safety red-teaming flagged this model as high risk "
                    f"(tier={tier}); eval/benchmark is blocked"
                ),
            }
            continue
        return {**out, "ok": True, "error": None}

    return block  # non-None: a non-empty runs list always sets a block reason


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


def _pipeline_url(endpoint: str, **kwargs: str) -> str:
    """Flask url_for when in a request; path fallback for unit tests."""
    try:
        from flask import has_request_context, url_for

        if has_request_context():
            return url_for(endpoint, **kwargs)
    except Exception:  # noqa: BLE001
        pass
    slug = kwargs.get("slug", "")
    profile = kwargs.get("profile", "base")
    if endpoint == "scan_detail" and slug:
        return f"/scans/{slug}"
    if endpoint == "safety_detail" and slug:
        return f"/safety/{slug}/{profile or 'base'}"
    if endpoint == "scan_run_new":
        base = "/scans/new"
    elif endpoint == "safety_run_new":
        base = "/safety/new"
    elif endpoint == "eval_run_new":
        base = "/eval-run/new"
    else:
        return ""
    query = {k: v for k, v in kwargs.items() if v and k not in ("slug", "profile")}
    if not query:
        return base
    from urllib.parse import urlencode

    return f"{base}?{urlencode(query)}"


def _scan_stage_href(model: str, gate: dict, stage: dict) -> str:
    if stage["state"] in ("n/a", "unsupported"):
        return ""
    if gate.get("status") is not None:
        from frontend.model_identity import hf_slug

        return _pipeline_url("scan_detail", slug=hf_slug(model))
    return _pipeline_url("scan_run_new", model=model)


def _safety_stage_href(model: str, gate: dict, stage: dict) -> str:
    if stage["state"] in ("n/a", "unsupported"):
        return ""
    from safety.gateway_ids import normalize_gateway_model_id

    slug = normalize_gateway_model_id(model)
    if gate.get("status") is not None:
        profile = str(gate.get("profile") or "base")
        return _pipeline_url("safety_detail", slug=slug, profile=profile)
    try:
        from frontend.safety_data import _gateway_catalog_id_for_slug

        catalog_id = _gateway_catalog_id_for_slug(model) or model
    except Exception:  # noqa: BLE001
        catalog_id = model
    return _pipeline_url("safety_run_new", model=catalog_id)


def _eval_stage_href(model: str, source: str, *, unlocked: bool) -> str:
    if not unlocked:
        return ""
    if source == "gateway":
        return _pipeline_url("eval_run_new", candidate=model)
    return _pipeline_url("eval_run_new", hf_repo=model)


def _attach_stage_href(stage: dict, href: str) -> dict:
    if href:
        stage = {**stage, "href": href}
    return stage


def stage_state(model: str, source: str) -> dict:
    """Per-model pipeline state for the /pipeline view (read-only)."""
    if source == "hf":
        # Lazy import breaks the pipeline <-> eval_launch cycle.
        from frontend.eval_launch import validate_hf_scan_gate

        scan_gate = validate_hf_scan_gate(model)
        scan_stage = _gate_stage(scan_gate)
        scan_stage = _attach_stage_href(
            scan_stage, _scan_stage_href(model, scan_gate, scan_stage)
        )
        safety_stage = {
            "state": "unsupported",
            "detail": "safety red-teaming not yet supported for served HF models",
        }
        unlocked = scan_gate["ok"]
        return {
            "model": model,
            "source": source,
            "scan": scan_stage,
            "safety": safety_stage,
            "eval_unlocked": unlocked,
            "eval_href": _eval_stage_href(model, source, unlocked=unlocked),
        }

    safety_gate = validate_safety_gate(model)
    safety_stage = _gate_stage(safety_gate)
    safety_stage = _attach_stage_href(
        safety_stage, _safety_stage_href(model, safety_gate, safety_stage)
    )
    scan_stage = {"state": "n/a", "detail": "nothing to scan (API endpoint)"}
    unlocked = safety_gate["ok"]
    return {
        "model": model,
        "source": source,
        "scan": scan_stage,
        "safety": safety_stage,
        "eval_unlocked": unlocked,
        "eval_href": _eval_stage_href(model, source, unlocked=unlocked),
    }


def _row_or_placeholder(model: str | None, source: str) -> dict:
    """``stage_state`` for one model, but never propagate a per-model failure.

    A single model with an unreadable artifact used to raise inside the build
    loop, and the broad handler then dropped that model AND every model after it
    (the table showed 15 of 41). Each model is now isolated: on error it still
    gets a row, with its gate marked unknown, so the full catalog always renders.
    """
    try:
        return stage_state(model, source)
    except Exception as exc:  # noqa: BLE001 — keep the model visible, don't abort
        detail = f"pipeline state unavailable: {exc}"
        return {
            "model": model,
            "source": source,
            "scan": (
                {"state": "n/a", "detail": "nothing to scan (API endpoint)"}
                if source == "gateway"
                else {"state": "unknown", "detail": detail}
            ),
            "safety": {"state": "unknown", "detail": detail},
            "eval_unlocked": False,
            "eval_href": _eval_stage_href(model, source, unlocked=False),
        }


def build_overview() -> dict:
    """All gateway models + every HF repo that already has a scan, each with its
    pipeline stage state. Degrades gracefully if a data source is unavailable."""
    rows: list[dict] = []
    gateway_count = 0
    gateway_error: str | None = None
    try:
        from gateway.catalog import get_gateway_catalog

        catalog = get_gateway_catalog()
        gateway_error = catalog.get("error")
        models = catalog.get("models") or []
        gateway_count = len(models)
        for m in models:
            rows.append(_row_or_placeholder(m.get("id"), "gateway"))
    except Exception as exc:  # noqa: BLE001 — a catalog hiccup must not 500 the page
        gateway_error = str(exc)
    try:
        from frontend.scan_data import get_scans_data

        for s in get_scans_data().get("scans", []):
            repo = s.get("model_id")
            if repo:
                rows.append(_row_or_placeholder(repo, "hf"))
    except Exception:  # noqa: BLE001
        pass
    return {
        "rows": rows,
        "has_rows": bool(rows),
        "gateway_count": gateway_count,
        "gateway_error": gateway_error,
    }
