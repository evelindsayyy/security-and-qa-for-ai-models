"""
Data source for /safety and /safety/<slug>.

Read-only — no subprocess here. Postgres when POSTGRES_DSN is set; artifact
fallback otherwise.
"""

from __future__ import annotations

import json
from pathlib import Path

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
        "missing_suites": [_suite_label(s) for s in (data.get("missing_suites") or [])],
        "n_findings": len(findings),
        "n_failed": n_failed,
        "n_passed": len(findings) - n_failed,
        "completed_at": data.get("completed_at") or "—",
        "status": data.get("status") or "unknown",
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
    """List every merged_safety_result.json under safety/output/<slug>/<profile>/."""
    from frontend.read_context import artifact_path_visible

    if not OUTPUT_DIR.exists():
        return {
            "has_safety": False,
            "output_dir": str(OUTPUT_DIR),
            "models": [],
        }

    rows: list[dict] = []
    for path, slug, profile in iter_merged_result_paths(OUTPUT_DIR):
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


def _get_safety_detail_files(slug: str, profile: str = "base") -> dict | None:
    """Structured safety payload for one (slug, profile) pair, read from disk."""
    from frontend.read_context import artifact_path_visible

    path = merged_result_path(OUTPUT_DIR, slug, profile)
    if not path.is_file():
        return None
    if not artifact_path_visible(path.parent, pillar="safety"):
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _build_safety_detail(slug, data, profile)


# Public entry points — Postgres when configured, artifact fallback otherwise.


def get_safety_data() -> dict:
    try:
        from frontend import safety_db_data

        if safety_db_data.available():
            return safety_db_data.get_safety_data_db()
    except Exception:
        pass
    return _get_safety_data_files()


def get_safety_detail(slug: str, profile: str = "base") -> dict | None:
    try:
        from frontend import safety_db_data

        if safety_db_data.available():
            detail = safety_db_data.get_safety_detail_db(slug, profile)
            if detail is not None:
                return detail
    except Exception:
        pass
    return _get_safety_detail_files(slug, profile)


def delete_safety_paths(slug: str, profile: str) -> list[str]:
    if not is_safe_slug(slug) or not is_safe_slug(profile):
        return []
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


def delete_safety(slug: str, profile: str = "base") -> str | None:
    """Remove one safety merge (and DB row when configured). Returns error or None."""
    from frontend.output_dirs import wipe_dir
    from frontend.safety_launch import inflight_safety_keys

    if not is_safe_slug(slug) or not is_safe_slug(profile):
        return f"invalid slug/profile: {slug!r}/{profile!r}"
    if f"{slug}/{profile}" in inflight_safety_keys():
        return "cannot delete while the run is still in progress"

    merged_path = merged_result_path(OUTPUT_DIR, slug, profile)
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
    if merged_path.is_file():
        try:
            merged_path.unlink()
            removed_disk = True
        except OSError:
            pass

    for rel in (
        OUTPUT_DIR / slug / profile,
        ROOT / "safety" / "promptfoo" / "output" / slug / profile,
    ):
        if rel.is_dir():
            wipe_dir(rel)
            removed_disk = True

    remaining = any(
        prof != profile
        for _path, s, prof in iter_merged_result_paths(OUTPUT_DIR)
        if s == slug
    )
    garak_dir = ROOT / "safety" / "garak" / "output" / slug
    if not remaining and garak_dir.is_dir():
        wipe_dir(garak_dir)
        removed_disk = True

    removed_db = False
    try:
        from frontend import safety_db_data

        if safety_db_data.available():
            if db_keys:
                removed_db = safety_db_data.delete_run(*db_keys)
            if not removed_db:
                removed_db = safety_db_data.delete_run_by_slug(slug)
    except Exception:
        pass

    if not removed_disk and not removed_db:
        return f"no safety result found for {slug!r}/{profile!r}"
    return None
