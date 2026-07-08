"""
Data source for /safety and /safety/<slug>.

Read-only — no subprocess here. Postgres when POSTGRES_DSN is set; artifact
fallback otherwise.
"""

from __future__ import annotations

import json
from pathlib import Path

from frontend import run_paths
from frontend.path_safety import is_safe_slug
from safety.merged_paths import iter_merged_result_paths, merged_result_path

ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "safety" / "output"

_SEVERITY_ORDER = ("critical", "high", "medium", "low", "unknown")

_SUITE_LABELS = {
    "promptfoo_duke_policy_v1": "Duke policy",
    "promptfoo_duke_redteam_v1": "Red-team",
    "garak_subset_v1": "Garak",
}


def _severity_rank(severity: str) -> int:
    try:
        return _SEVERITY_ORDER.index(severity.lower())
    except ValueError:
        return len(_SEVERITY_ORDER)


def _pass_rate_display(rate: float | None) -> str:
    if rate is None:
        return "—"
    return f"{rate * 100:.1f}%"


def _suite_label(probe_suite: str) -> str:
    return _SUITE_LABELS.get(probe_suite, probe_suite.replace("_", " "))


# Fixed suite order so columns line up across models.
_SUITE_ORDER = ("promptfoo_duke_policy_v1", "promptfoo_duke_redteam_v1", "garak_subset_v1")


def _rate_class(rate: float | None) -> str:
    if rate is None:
        return "rate-na"
    if rate >= 0.8:
        return "rate-strong"
    if rate >= 0.6:
        return "rate-mid"
    return "rate-weak"


def _category_breakdown(findings: list[dict]) -> dict[str, dict[str, int]]:
    """category -> {"passed": n, "failed": n} from parsed findings."""
    breakdown: dict[str, dict[str, int]] = {}
    for f in findings:
        bucket = breakdown.setdefault(f["category"], {"passed": 0, "failed": 0})
        bucket["passed" if f["passed"] else "failed"] += 1
    return breakdown


def _summarize_merged_data(data: dict, slug: str, profile: str = "base") -> dict:
    """Build a list-table row from an in-memory MergedSafetyResult-shaped dict."""
    findings = data.get("findings") or []
    runs = data.get("runs") or []
    n_failed = sum(
        1 for f in findings if isinstance(f, dict) and not f.get("passed")
    )
    pass_rate = data.get("summary_pass_rate") or 0
    by_suite = {
        r.get("probe_suite"): r.get("summary_pass_rate")
        for r in runs
        if isinstance(r, dict)
    }
    tier = (data.get("composite_tier") or "low").lower()
    profile = data.get("redteam_profile") or profile
    from frontend.staleness import garak_probe_count_from_data

    garak_probe_count = garak_probe_count_from_data(data)

    return {
        "slug": slug,
        "profile": profile,
        "run_key": f"{slug}/{profile}",
        "gateway_model_id": data.get("gateway_model_id") or slug,
        "display_name": data.get("display_name") or data.get("gateway_model_id") or slug,
        "tier": tier,
        "composite_score": data.get("composite_score") or 0,
        "summary_pass_rate": pass_rate,
        "pass_rate_display": _pass_rate_display(pass_rate),
        "pass_rate_class": _rate_class(pass_rate),
        "suite_columns": [
            {
                "display": _pass_rate_display(by_suite.get(suite)),
                "rate_class": _rate_class(by_suite.get(suite)),
            }
            for suite in _SUITE_ORDER
        ],
        "suite_rates": {suite: by_suite.get(suite) for suite in _SUITE_ORDER},
        "missing_suites": [_suite_label(s) for s in (data.get("missing_suites") or [])],
        "n_findings": len(findings),
        "n_failed": n_failed,
        "n_passed": len(findings) - n_failed,
        "category_breakdown": _category_breakdown(_parse_findings(findings)),
        "completed_at": data.get("completed_at") or "—",
        "status": data.get("status") or "unknown",
        "garak_probe_count": garak_probe_count,
    }


def _summarize_merged(path: Path, slug: str, profile: str = "base") -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _summarize_merged_data(data, slug, profile)


def _parse_findings(findings_raw: list) -> list[dict]:
    findings = []
    for f in findings_raw:
        if not isinstance(f, dict):
            continue
        sev = (f.get("severity") or "unknown").lower()
        source = (f.get("source") or "—").lower()
        category = (f.get("category") or "—").lower()
        findings.append(
            {
                "id": f.get("id") or "—",
                "title": f.get("title") or "—",
                "severity": sev,
                "source": source,
                "category": category,
                "passed": bool(f.get("passed")),
                "probe_id": f.get("probe_id") or "—",
                "probe_suite": f.get("probe_suite"),
                "description": (f.get("description") or "").strip(),
                "scoring_excluded": bool(f.get("scoring_excluded")),
                "corroborated_by": f.get("corroborated_by") or [],
            }
        )
    findings.sort(
        key=lambda x: (
            0 if not x["passed"] else 1,
            _severity_rank(x["severity"]),
            x["source"],
            x["probe_id"],
        )
    )
    return findings


def _deployment_rows(ctx: dict) -> list[dict]:
    if not ctx:
        return []
    labels = {
        "deployment_type": "Deployment type",
        "has_tools": "Has tools",
        "has_guardrails": "Has guardrails",
        "data_access": "Data access",
        "commercial_vs_oss": "Commercial vs OSS",
    }
    rows = []
    for key, label in labels.items():
        if key not in ctx:
            continue
        val = ctx[key]
        if isinstance(val, bool):
            val = "yes" if val else "no"
        rows.append({"label": label, "value": val})
    return rows


def _suite_panels(runs: list, tool_results: dict, findings: list[dict]) -> list[dict]:
    # Group parsed findings by suite so each panel can show per-probe detail
    # (failures first), not just a bare probe-id list.
    by_suite: dict[str, list[dict]] = {}
    for f in findings:
        by_suite.setdefault(f.get("probe_suite") or "—", []).append(f)

    panels = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        suite = run.get("probe_suite") or "—"
        tool = (tool_results or {}).get(suite) or {}
        promptfoo = tool.get("promptfoo") or {}
        garak = tool.get("garak") or {}
        panels.append(
            {
                "probe_suite": suite,
                "label": _suite_label(suite),
                "source": (run.get("source") or "—").lower(),
                "summary_pass_rate": run.get("summary_pass_rate", 0),
                "pass_rate_display": _pass_rate_display(run.get("summary_pass_rate")),
                "n_findings": run.get("n_findings", 0),
                "n_passed": run.get("n_passed", 0),
                "probes": by_suite.get(suite, []),
                "eval_id": promptfoo.get("evalId"),
                "source_file": promptfoo.get("source_file"),
                "description": promptfoo.get("description"),
                "plugins": promptfoo.get("plugins") or [],
                "garak_version": garak.get("garak_version"),
                "garak_report": garak.get("report_file"),
                "garak_run_id": garak.get("run_id"),
                "garak_expected_modules": garak.get("expected_modules"),
                "garak_completed_modules": garak.get("completed_modules"),
                "garak_report_complete": garak.get("report_complete"),
            }
        )
    return panels


def _garak_partial_note(data: dict) -> str | None:
    garak_tool = (data.get("tool_results") or {}).get("garak_subset_v1") or {}
    garak_meta = garak_tool.get("garak") or {}
    expected = garak_meta.get("expected_modules")
    completed = garak_meta.get("completed_modules")
    if garak_meta.get("report_complete") is False:
        if expected and completed is not None:
            return f"Garak partial ({completed}/{expected} modules) — tier reflects only completed probes."
        return "Garak partial (incomplete report) — tier reflects only completed probes."
    if expected and completed is not None and completed < expected:
        return f"Garak partial ({completed}/{expected} modules) — tier reflects only completed probes."
    return None


def _build_safety_detail(slug: str, data: dict, profile: str = "base") -> dict:
    """Structured safety payload from a MergedSafetyResult-shaped dict."""
    findings = _parse_findings(data.get("findings") or [])
    runs = data.get("runs") or []
    n_failed = sum(1 for f in findings if not f["passed"])
    profile = data.get("redteam_profile") or profile

    return {
        "slug": slug,
        "profile": profile,
        "run_key": f"{slug}/{profile}",
        "gateway_model_id": data.get("gateway_model_id") or slug,
        "display_name": data.get("display_name") or data.get("gateway_model_id") or slug,
        "tier": (data.get("composite_tier") or "low").lower(),
        "summary_pass_rate": data.get("summary_pass_rate") or 0,
        "pass_rate_display": _pass_rate_display(data.get("summary_pass_rate")),
        "pass_rate_class": _rate_class(data.get("summary_pass_rate")),
        "missing_suites": [_suite_label(s) for s in (data.get("missing_suites") or [])],
        "garak_partial_note": _garak_partial_note(data),
        "status": data.get("status") or "unknown",
        "findings": findings,
        "n_findings": len(findings),
        "n_failed": n_failed,
        "n_passed": len(findings) - n_failed,
        "suite_panels": _suite_panels(runs, data.get("tool_results") or {}, findings),
        "deployment_rows": _deployment_rows(data.get("deployment_context") or {}),
        "started_at": data.get("started_at") or "—",
        "completed_at": data.get("completed_at") or "—",
        "raw_summary": {
            "gateway_model_id": data.get("gateway_model_id"),
            "display_name": data.get("display_name"),
            "redteam_profile": profile,
            "summary_pass_rate": data.get("summary_pass_rate"),
            "runs": runs,
            "deployment_context": data.get("deployment_context"),
        },
    }


def _get_safety_data_files() -> dict:
    """List every merged_safety_result.json visible in the current view —
    the public catalog under safety/output/<slug>/<profile>/, plus this
    owner's own private runs when in private mode."""
    from frontend.read_context import artifact_path_visible, read_context

    if not OUTPUT_DIR.exists():
        return {
            "has_safety": False,
            "output_dir": str(OUTPUT_DIR),
            "models": [],
        }

    view_mode, user_id = read_context()
    seen: set[tuple[str, str]] = set()
    rows: list[dict] = []
    # Private first when in private mode: if this owner has both a public
    # and a private run for the same (slug, profile), the private-mode list
    # must show (and link to) their own private copy, not the public one.
    sources = []
    if view_mode == "private" and user_id:
        sources.append(iter_merged_result_paths(OUTPUT_DIR, owner_user_id=user_id))
    sources.append(iter_merged_result_paths(OUTPUT_DIR))
    for source in sources:
        for path, slug, profile in source:
            if (slug, profile) in seen:
                continue
            seen.add((slug, profile))
            if not artifact_path_visible(path.parent, pillar="safety"):
                continue
            row = _summarize_merged(path, slug, profile)
            if row:
                rows.append(row)

    rows.sort(key=lambda r: (r["composite_score"], r["summary_pass_rate"]))

    return {
        "has_safety": bool(rows),
        "output_dir": str(OUTPUT_DIR),
        "models": rows,
        "suite_labels": [_suite_label(s) for s in _SUITE_ORDER],
    }


def _get_safety_detail_files(
    slug: str,
    profile: str = "base",
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> dict | None:
    """Structured safety payload for one (slug, profile) pair, read from disk.

    ``visibility``/``owner_user_id`` pick the exact on-disk copy — the URL
    the caller resolved to, not the viewer's ambient session.
    """
    if visibility == "private" and not owner_user_id:
        return None

    path = merged_result_path(
        OUTPUT_DIR, slug, profile, owner_user_id=owner_user_id if visibility == "private" else None
    )
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _build_safety_detail(slug, data, profile)


# Public entry points — Postgres when configured, artifact fallback otherwise.


def get_safety_data() -> dict:
    from frontend import safety_db_data
    from frontend.db_fallback import get_data_with_db_fallback

    data = get_data_with_db_fallback(
        safety_db_data.available,
        safety_db_data.get_safety_data_db,
        _get_safety_data_files,
    )
    models = data.get("models") or []
    from frontend.staleness import attach_staleness

    attach_staleness(models, "safety")
    data["has_safety"] = bool(models)
    data.update(_build_safety_comparison_section(models))
    return data


_SUITE_BADGE = {
    "promptfoo_duke_policy_v1": "badge-policy",
    "promptfoo_duke_redteam_v1": "badge-redteam",
    "garak_subset_v1": "badge-garak",
}


def _safety_matrix_cell(model: dict, suite: str) -> dict | None:
    rate = (model.get("suite_rates") or {}).get(suite)
    if rate is None:
        return None
    return {
        "display": _pass_rate_display(rate),
        "score_class": _rate_class(rate),
        "slug": model.get("slug"),
        "profile": model.get("profile", "base"),
    }


def _build_safety_comparison_section(models: list[dict]) -> dict:
    """Pivot safety runs into suite×model pass-rate matrix."""
    from frontend.reference_constants import order_models

    if not models:
        return {"has_comparison": False, "comparison_models": [], "comparison_rows": []}

    by_model: dict[str, dict] = {}
    for m in models:
        name = m.get("gateway_model_id") or m.get("display_name")
        if not name:
            continue
        existing = by_model.get(name)
        if existing is None or (m.get("profile") == "base" and existing.get("profile") != "base"):
            by_model[name] = m

    comparison_models = order_models(by_model.keys())
    comparison_rows: list[dict] = []
    for suite in _SUITE_ORDER:
        cells: dict[str, dict] = {}
        for model_name in comparison_models:
            row = by_model.get(model_name)
            if not row:
                continue
            cell = _safety_matrix_cell(row, suite)
            if cell:
                cells[model_name] = cell
        comparison_rows.append({
            "key": suite,
            "label": _suite_label(suite),
            "badge_class": _SUITE_BADGE.get(suite, "badge-pilot"),
            "cells": cells,
        })

    return {
        "has_comparison": bool(comparison_models),
        "comparison_models": comparison_models,
        "comparison_rows": comparison_rows,
    }


def _build_safety_reference_scores(models: list[dict]) -> dict:
    """Preferred-model × suite pass-rate table from existing public runs."""
    from frontend.reference_constants import PREFERRED_REFERENCE_MODELS

    by_model: dict[str, dict] = {}
    for m in models:
        name = m.get("gateway_model_id") or m.get("display_name")
        if not name:
            continue
        if name not in by_model or m.get("profile") == "base":
            by_model[name] = m

    reference_models = list(PREFERRED_REFERENCE_MODELS)
    reference_rows: list[dict] = []
    for suite in _SUITE_ORDER:
        cells: dict[str, dict] = {}
        for model_name in reference_models:
            row = by_model.get(model_name)
            if not row:
                continue
            cell = _safety_matrix_cell(row, suite)
            if cell:
                cells[model_name] = cell
        reference_rows.append({
            "key": suite,
            "label": _suite_label(suite),
            "badge_class": _SUITE_BADGE.get(suite, "badge-pilot"),
            "cells": cells,
        })

    has_scores = any(c for row in reference_rows for c in row["cells"].values())
    return {
        "has_reference_scores": has_scores,
        "reference_models": reference_models,
        "reference_rows": reference_rows,
    }


def get_safety_rerun_params(
    slug: str,
    profile: str = "base",
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> dict | None:
    """Launch-form prefill from a completed safety run."""
    detail = get_safety_detail(
        slug, profile, visibility=visibility, owner_user_id=owner_user_id
    )
    if detail is None:
        return None
    return {
        "gateway_model": detail.get("gateway_model_id") or detail.get("model"),
        "redteam_profile": profile,
        "run_policy": True,
        "run_redteam": True,
        "run_garak": True,
    }


def get_safety_detail(
    slug: str,
    profile: str = "base",
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> dict | None:
    """Detail payload for one safety run. Defaults to the public catalog; pass
    ``visibility="private", owner_user_id=...`` for a signed-in user's own copy."""
    try:
        from frontend import safety_db_data

        if safety_db_data.available():
            return safety_db_data.get_safety_detail_db(
                slug, profile, visibility=visibility, owner_user_id=owner_user_id
            )
    except Exception:
        pass
    return _get_safety_detail_files(
        slug, profile, visibility=visibility, owner_user_id=owner_user_id
    )


def delete_safety_paths(
    slug: str, profile: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> list[str]:
    if not is_safe_slug(slug) or not is_safe_slug(profile):
        return []
    if visibility == "private" and owner_user_id:
        return [
            f"safety/output/{slug}/{run_paths.PRIVATE_SEGMENT}/{owner_user_id}/{profile}/",
            f"safety/promptfoo/output/{slug}/{run_paths.PRIVATE_SEGMENT}/{owner_user_id}/{profile}/",
        ]
    paths = [
        f"safety/output/{slug}/{profile}/",
        f"safety/promptfoo/output/{slug}/{profile}/",
    ]
    other_profiles = [
        prof for _path, s, prof in iter_merged_result_paths(OUTPUT_DIR)
        if s == slug and prof != profile
    ]
    if not other_profiles:
        paths.append(f"safety/garak/output/{slug}/")
    return paths


def delete_safety(
    slug: str,
    profile: str = "base",
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> str | None:
    """Remove one safety merge (and DB row when configured). Returns error or None."""
    from frontend.output_dirs import wipe_dir
    from frontend.safety_launch import inflight_safety_keys

    if not is_safe_slug(slug) or not is_safe_slug(profile):
        return f"invalid slug/profile: {slug!r}/{profile!r}"
    if visibility == "private" and not owner_user_id:
        return f"no safety result found for {slug!r}/{profile!r}"
    if f"{slug}/{profile}" in inflight_safety_keys():
        return "cannot delete while the run is still in progress"

    private = visibility == "private" and owner_user_id
    owner_scope = owner_user_id if private else None
    merged_dir = run_paths.scoped_dir(
        OUTPUT_DIR / slug / profile, visibility=visibility, owner_user_id=owner_user_id
    )
    promptfoo_dir = run_paths.scoped_dir(
        ROOT / "safety" / "promptfoo" / "output" / slug / profile,
        visibility=visibility,
        owner_user_id=owner_user_id,
    )
    merged_path = merged_result_path(OUTPUT_DIR, slug, profile, owner_user_id=owner_scope)
    db_keys: tuple[str, str] | None = None
    if merged_path.is_file():
        try:
            data = json.loads(merged_path.read_text(encoding="utf-8"))
            gateway_model_id = data.get("gateway_model_id")
            completed_at = data.get("completed_at")
            if gateway_model_id and completed_at:
                db_keys = (gateway_model_id, completed_at)
        except (json.JSONDecodeError, OSError):
            pass

    removed_disk = False
    # Legacy (pre-profile) layout: merged_path is a bare file directly under
    # OUTPUT_DIR/slug/, not inside merged_dir — remove it explicitly.
    if merged_path.is_file() and merged_path.parent != merged_dir:
        try:
            merged_path.unlink()
            removed_disk = True
        except OSError:
            pass

    for rel in (merged_dir, promptfoo_dir):
        if rel.is_dir():
            wipe_dir(rel)
            removed_disk = True

    if not private:
        remaining = any(
            prof != profile
            for _path, s, prof in iter_merged_result_paths(OUTPUT_DIR)
            if s == slug
        )
        garak_dir = ROOT / "safety" / "garak" / "output" / slug
        if not remaining and garak_dir.is_dir():
            wipe_dir(garak_dir)
            removed_disk = True
    else:
        garak_dir = run_paths.scoped_dir(
            ROOT / "safety" / "garak" / "output" / slug,
            visibility=visibility,
            owner_user_id=owner_user_id,
        )
        if garak_dir.is_dir():
            wipe_dir(garak_dir)
            removed_disk = True

    removed_db = False
    db_available = False
    db_row_existed = False
    db_exc: BaseException | None = None
    try:
        from frontend import safety_db_data
        from frontend.delete_db import db_delete_error

        db_available = safety_db_data.available()
        if db_available:
            try:
                db_row_existed = (
                    safety_db_data.resolve_delete_keys(
                        slug, profile, visibility=visibility, owner_user_id=owner_user_id
                    )
                    is not None
                )
            except Exception:
                pass
            try:
                if db_keys:
                    removed_db = safety_db_data.delete_run(*db_keys)
                if not removed_db:
                    removed_db = safety_db_data.delete_run_by_slug(
                        slug, profile, visibility=visibility, owner_user_id=owner_user_id
                    )
            except Exception as exc:
                db_exc = exc
    except Exception as exc:
        db_exc = exc

    err = db_delete_error(
        db_available=db_available,
        db_row_existed=db_row_existed,
        removed_db=removed_db,
        db_exc=db_exc,
    )
    if err:
        return err

    if not removed_disk and not removed_db:
        return f"no safety result found for {slug!r}/{profile!r}"
    return None


def get_safety_guide_data() -> dict:
    """Rows for the safety reference/guide pages."""
    models = get_safety_data().get("models") or []
    example = models[0] if models else None
    return {
        "guide_rows": [
            {
                "key": "policy",
                "label": "Policy",
                "badge_class": "badge-policy",
                "about": (
                    "Hand-written Duke IT policy probes — phishing, data handling, "
                    "acceptable use, and similar institutional rules."
                ),
                "procedure": (
                    "Promptfoo runs curated policy tests against the gateway model; "
                    "each probe is scored pass/fail."
                ),
                "scoring": (
                    "Per-probe pass rate; weighted 40% in the composite tier. "
                    "A single curated policy failure can escalate the tier."
                ),
            },
            {
                "key": "redteam",
                "label": "Red-team",
                "badge_class": "badge-redteam",
                "about": (
                    "Promptfoo adversarial plugins — jailbreaks, encoding tricks, "
                    "and plugin-driven attack patterns."
                ),
                "procedure": (
                    "Red-team profile selects attack plugins (base is the default). "
                    "Plugins generate adversarial prompts automatically."
                ),
                "scoring": "Per-probe pass rate; weighted 35% in the composite tier.",
            },
            {
                "key": "garak",
                "label": "Garak",
                "badge_class": "badge-garak",
                "about": (
                    "Garak automated attack modules — encoding, prompt injection, "
                    "and other probe families from the Garak toolkit."
                ),
                "procedure": (
                    "Garak runs a Duke-default probe set; optional comma-separated "
                    "subset on the launch form."
                ),
                "scoring": "Per-probe pass rate; weighted 25% in the composite tier.",
            },
        ],
        "has_example": example is not None,
        "example_slug": example["slug"] if example else None,
        "example_profile": example.get("profile", "base") if example else "base",
        "example_model": example["gateway_model_id"] if example else None,
    }


def get_safety_reference_data() -> dict:
    models = get_safety_data().get("models") or []
    data = get_safety_guide_data()
    data["has_reference"] = data["has_example"]
    data.update(_build_safety_reference_scores(models))
    return data
