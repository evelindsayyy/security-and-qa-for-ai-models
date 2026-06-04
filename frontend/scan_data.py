"""
data source for /scans and /scans/<slug>.

reads scanner/output/<slug>/scan_result.json (gitignored; produced by
`python -m scanner scan <hf_repo>` on dgx). read-only — no subprocess here.

mirrors eval_run_data.py shape: get_*_data() + has_* empty state + row list.

week 5: replace file glob with GET /api/scans and GET /api/scans/{id}.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "scanner" / "output"


def _slug_to_model(slug: str) -> str:
    """turn output dir slug back into hf repo id for display (BAAI--bge -> BAAI/bge)."""
    return slug.replace("--", "/", 1) if "--" in slug else slug


def _basename(file_path: str | None) -> str:
    """strip machine-specific prefixes from finding paths; keep modelaudit (pos N) suffix."""
    if not file_path:
        return ""
    loc = file_path.strip()
    if " (pos " in loc:
        base, pos = loc.split(" (pos ", 1)
        name = Path(base).name
        return f"{name} (pos {pos.rstrip(')')})" if pos else name
    return Path(loc).name


def _tool_snippet(data: dict) -> str:
    """one-line summary of the three scanners for the list table."""
    tool = data.get("tool_results") or {}
    ms = tool.get("modelscan") or {}
    fick = tool.get("fickling") or {}
    ma = tool.get("modelaudit") or {}
    parts = []
    parts.append(f"modelscan={ms.get('total_issues', 0)}")
    fick_sev = fick.get("severity") or data.get("fickling_severity")
    if fick_sev:
        parts.append(f"fickling={fick_sev}")
    actionable = ma.get("actionable_issue_count")
    if actionable is not None:
        parts.append(f"modelaudit={actionable}")
    return " · ".join(parts)


def _summarize_scan(path: Path, slug: str) -> dict | None:
    """load one scan_result.json into a table row. none if parse fails."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    findings = data.get("findings") or []
    sev_counts = Counter(
        (f.get("severity") or "unknown").lower() for f in findings if isinstance(f, dict)
    )
    meta = data.get("scan_metadata") or {}
    scanned_at = meta.get("scanned_at") or "—"

    return {
        "slug": slug,
        "model_id": data.get("model_id") or _slug_to_model(slug),
        "severity_tier": (data.get("severity_tier") or "unknown").lower(),
        "overall_risk_score": data.get("overall_risk_score", 0),
        "n_findings": len(findings),
        "findings_by_severity": dict(sev_counts),
        "scanned_at": scanned_at,
        "tool_snippet": _tool_snippet(data),
        "scanned_file_count": len(data.get("scanned_files") or []),
        "status": data.get("status") or "unknown",
    }


def get_scans_data() -> dict:
    """
    list every scan_result.json under scanner/output/, sorted highest risk first.

    surfaces the malicious poc at the top for stakeholder demos when present.
    """
    if not OUTPUT_DIR.exists():
        return {
            "has_scans": False,
            "output_dir": str(OUTPUT_DIR),
            "scans": [],
            "tier_summary": "",
        }

    rows: list[dict] = []
    for path in sorted(OUTPUT_DIR.glob("*/scan_result.json")):
        slug = path.parent.name
        row = _summarize_scan(path, slug)
        if row:
            rows.append(row)

    rows.sort(key=lambda r: r["overall_risk_score"], reverse=True)

    tiers = sorted({r["severity_tier"] for r in rows})
    tier_summary = ", ".join(tiers) if tiers else ""

    return {
        "has_scans": bool(rows),
        "output_dir": str(OUTPUT_DIR),
        "scans": rows,
        "tier_summary": tier_summary,
    }


def get_scan_detail(slug: str) -> dict | None:
    """
    full scan payload for one slug — findings table + trimmed tool_results.

    returns none if the slug dir or scan_result.json is missing.
    """
    path = OUTPUT_DIR / slug / "scan_result.json"
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    findings_raw = data.get("findings") or []
    findings = []
    for f in findings_raw:
        if not isinstance(f, dict):
            continue
        findings.append(
            {
                "title": f.get("title") or "—",
                "severity": (f.get("severity") or "unknown").lower(),
                "source": f.get("source") or "—",
                "file_path": _basename(f.get("file_path")),
                "description": (f.get("description") or "")[:500],
                "corroborated_by": f.get("corroborated_by"),
            }
        )

    tool = data.get("tool_results") or {}
    # keep json small on the page — drop huge issue arrays if present
    tool_trimmed = {
        "modelscan": {
            k: tool.get("modelscan", {}).get(k)
            for k in (
                "total_issues",
                "total_issues_by_severity",
                "total_skipped",
                "scanned_files",
                "modelscan_version",
            )
            if tool.get("modelscan")
        },
        "fickling": tool.get("fickling"),
        "modelaudit": {
            k: tool.get("modelaudit", {}).get(k)
            for k in (
                "actionable_issue_count",
                "issue_count",
                "noise_filtered_count",
                "path_count",
                "scan_mode",
            )
            if tool.get("modelaudit")
        },
    }

    meta = data.get("scan_metadata") or {}

    return {
        "slug": slug,
        "model_id": data.get("model_id") or _slug_to_model(slug),
        "severity_tier": (data.get("severity_tier") or "unknown").lower(),
        "overall_risk_score": data.get("overall_risk_score", 0),
        "status": data.get("status") or "unknown",
        "scanned_files": data.get("scanned_files") or [],
        "findings": findings,
        "tool_results": tool_trimmed,
        "coverage": meta.get("coverage") or {},
        "file_formats": meta.get("file_formats") or {},
        "scanned_at": meta.get("scanned_at") or "—",
        "scanner_version": meta.get("scanner_version") or "—",
    }
