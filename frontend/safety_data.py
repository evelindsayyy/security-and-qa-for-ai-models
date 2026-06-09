"""
data source for /safety and /safety/<slug>.

reads safety/output/<slug>/merged_safety_result.json (gitignored; produced by
`safety.merge` after promptfoo + garak exports). read-only — no subprocess here.

mirrors scan_data.py: get_*_data() + structured detail rows instead of raw json.

week 5: replace file glob with GET /api/safety and GET /api/safety/{id}.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

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


def _tier_rank(tier: str) -> int:
    return _severity_rank(tier)


def _pass_rate_display(rate: float | None) -> str:
    if rate is None:
        return "—"
    return f"{rate * 100:.1f}%"


def _suite_label(probe_suite: str) -> str:
    return _SUITE_LABELS.get(probe_suite, probe_suite.replace("_", " "))


def _failed_summary(findings: list[dict]) -> str:
    failed = [f for f in findings if not f.get("passed")]
    if not failed:
        return "none"
    counts = Counter((f.get("severity") or "unknown").lower() for f in failed)
    parts = []
    for sev in _SEVERITY_ORDER:
        if counts.get(sev):
            parts.append(f"{counts[sev]} {sev}")
    return ", ".join(parts) if parts else f"{len(failed)} failed"


def _suite_snippet(runs: list[dict]) -> str:
    parts = []
    for r in runs:
        if not isinstance(r, dict):
            continue
        suite = r.get("probe_suite") or "—"
        label = _suite_label(suite)
        rate = r.get("summary_pass_rate")
        parts.append(f"{label}={_pass_rate_display(rate)}")
    return " · ".join(parts) if parts else "—"


def _summarize_merged(path: Path, slug: str) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    findings = data.get("findings") or []
    runs = data.get("runs") or []
    n_failed = sum(1 for f in findings if isinstance(f, dict) and not f.get("passed"))

    return {
        "slug": slug,
        "gateway_model_id": data.get("gateway_model_id") or slug,
        "display_name": data.get("display_name") or data.get("gateway_model_id") or slug,
        "safety_tier": (data.get("safety_tier") or "unknown").lower(),
        "summary_pass_rate": data.get("summary_pass_rate", 0),
        "pass_rate_display": _pass_rate_display(data.get("summary_pass_rate")),
        "n_findings": len(findings),
        "n_failed": n_failed,
        "n_passed": len(findings) - n_failed,
        "failed_summary": _failed_summary([f for f in findings if isinstance(f, dict)]),
        "n_suites": len(runs),
        "suite_snippet": _suite_snippet(runs),
        "completed_at": data.get("completed_at") or "—",
        "status": data.get("status") or "unknown",
    }


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


def _suite_panels(runs: list, tool_results: dict) -> list[dict]:
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
                "probe_ids": run.get("probe_ids") or [],
                "eval_id": promptfoo.get("evalId"),
                "source_file": promptfoo.get("source_file"),
                "description": promptfoo.get("description"),
                "plugins": promptfoo.get("plugins") or [],
                "garak_version": garak.get("garak_version"),
                "garak_report": garak.get("report_file"),
                "garak_run_id": garak.get("run_id"),
            }
        )
    return panels


def get_safety_data() -> dict:
    """list every merged_safety_result.json under safety/output/."""
    if not OUTPUT_DIR.exists():
        return {
            "has_safety": False,
            "output_dir": str(OUTPUT_DIR),
            "models": [],
            "tier_summary": "",
        }

    rows: list[dict] = []
    for path in sorted(OUTPUT_DIR.glob("*/merged_safety_result.json")):
        slug = path.parent.name
        row = _summarize_merged(path, slug)
        if row:
            rows.append(row)

    rows.sort(key=lambda r: (_tier_rank(r["safety_tier"]), r["summary_pass_rate"]))

    tiers = sorted({r["safety_tier"] for r in rows}, key=_tier_rank)
    tier_summary = ", ".join(tiers) if tiers else ""

    return {
        "has_safety": bool(rows),
        "output_dir": str(OUTPUT_DIR),
        "models": rows,
        "tier_summary": tier_summary,
    }


def get_safety_detail(slug: str) -> dict | None:
    """structured safety payload for one gateway model slug."""
    path = OUTPUT_DIR / slug / "merged_safety_result.json"
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    findings = _parse_findings(data.get("findings") or [])
    runs = data.get("runs") or []
    n_failed = sum(1 for f in findings if not f["passed"])

    return {
        "slug": slug,
        "gateway_model_id": data.get("gateway_model_id") or slug,
        "display_name": data.get("display_name") or data.get("gateway_model_id") or slug,
        "safety_tier": (data.get("safety_tier") or "unknown").lower(),
        "summary_pass_rate": data.get("summary_pass_rate", 0),
        "pass_rate_display": _pass_rate_display(data.get("summary_pass_rate")),
        "status": data.get("status") or "unknown",
        "findings": findings,
        "n_findings": len(findings),
        "n_failed": n_failed,
        "n_passed": len(findings) - n_failed,
        "failed_summary": _failed_summary(findings),
        "suite_snippet": _suite_snippet(runs),
        "suite_panels": _suite_panels(runs, data.get("tool_results") or {}),
        "deployment_rows": _deployment_rows(data.get("deployment_context") or {}),
        "started_at": data.get("started_at") or "—",
        "completed_at": data.get("completed_at") or "—",
        "raw_summary": {
            "gateway_model_id": data.get("gateway_model_id"),
            "display_name": data.get("display_name"),
            "safety_tier": data.get("safety_tier"),
            "summary_pass_rate": data.get("summary_pass_rate"),
            "runs": runs,
            "deployment_context": data.get("deployment_context"),
        },
    }
