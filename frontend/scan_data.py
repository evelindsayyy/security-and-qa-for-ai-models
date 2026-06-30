"""
Data source for /scans and /scans/<slug>.

Read-only — no subprocess here. Postgres when POSTGRES_DSN is set; artifact
fallback otherwise.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from frontend.path_safety import is_safe_slug

ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "scanner" / "output"

_SEVERITY_ORDER = ("critical", "high", "medium", "low", "unknown")


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


def _severity_rank(severity: str) -> int:
    try:
        return _SEVERITY_ORDER.index(severity.lower())
    except ValueError:
        return len(_SEVERITY_ORDER)


def _tool_snippet(data: dict) -> str:
    """one-line summary of the three scanners for the list table."""
    tool = data.get("tool_results") or {}
    ms = tool.get("modelscan") or {}
    fick = tool.get("fickling") or {}
    ma = tool.get("modelaudit") or {}
    deps = tool.get("dependencies") or {}
    sec = tool.get("secrets") or {}
    parts = []
    parts.append(f"modelscan={ms.get('total_issues', 0)}")
    fick_sev = fick.get("severity") or data.get("fickling_severity")
    if fick_sev:
        parts.append(f"fickling={fick_sev}")
    actionable = ma.get("actionable_issue_count")
    if actionable is not None:
        parts.append(f"modelaudit={actionable}")
    if deps.get("vuln_count") is not None or tool.get("dependencies") is not None:
        parts.append(f"deps={deps.get('vuln_count', 0)}")
    if sec.get("secret_count") is not None or tool.get("secrets") is not None:
        parts.append(f"secrets={sec.get('secret_count', 0)}")
    return " · ".join(parts)


def _severity_summary(findings: list[dict]) -> str:
    counts = Counter(f.get("severity", "unknown") for f in findings)
    parts = []
    for sev in _SEVERITY_ORDER:
        if counts.get(sev):
            parts.append(f"{counts[sev]} {sev}")
    return ", ".join(parts) if parts else "—"


def _summarize_from_data(data: dict, slug: str) -> dict:
    """Build a list-table row from an in-memory ScanResult-shaped dict."""
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
        "severity_summary": _severity_summary(
            [{"severity": (f.get("severity") or "unknown").lower()} for f in findings if isinstance(f, dict)]
        ),
        "scanned_at": scanned_at,
        "tool_snippet": _tool_snippet(data),
        "scanned_file_count": len(data.get("scanned_files") or []),
        "status": data.get("status") or "unknown",
        "fickling_severity": data.get("fickling_severity"),
    }


def _summarize_scan(path: Path, slug: str) -> dict | None:
    """load one scan_result.json into a table row. none if parse fails."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _summarize_from_data(data, slug)


def _parse_findings(findings_raw: list) -> list[dict]:
    findings = []
    for f in findings_raw:
        if not isinstance(f, dict):
            continue
        sev = (f.get("severity") or "unknown").lower()
        findings.append(
            {
                "id": f.get("id") or "—",
                "title": f.get("title") or "—",
                "severity": sev,
                "source": (f.get("source") or "—").lower(),
                "file_path": _basename(f.get("file_path")),
                "description": (f.get("description") or "").strip(),
                "remediation": (f.get("remediation") or "").strip(),
                "raw_tool_severity": f.get("raw_tool_severity"),
                "corroborated_by": f.get("corroborated_by") or [],
            }
        )
    findings.sort(key=lambda x: (_severity_rank(x["severity"]), x["source"], x["title"]))
    return findings


def _modelscan_panel(ms: dict) -> dict:
    by_sev = ms.get("total_issues_by_severity") or {}
    rows = [(sev, by_sev[sev]) for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW") if by_sev.get(sev)]
    scanned = ms.get("scanned_files") or []
    return {
        "total_issues": ms.get("total_issues", 0),
        "severity_rows": rows,
        "scanned_count": len(scanned),
        "skipped": ms.get("total_skipped", 0),
        "version": ms.get("modelscan_version"),
        "sample_files": [_basename(p) for p in scanned[:8]],
    }


def _fickling_panel(fick: dict | None, top_level: str | None) -> dict | None:
    if not fick and not top_level:
        return None
    entries = []
    if fick:
        per_file = fick.get("per_file") or [fick]
        for entry in per_file:
            if not isinstance(entry, dict):
                continue
            entries.append(
                {
                    "file": _basename(entry.get("file")),
                    "severity": entry.get("severity") or top_level or "—",
                    "pytorch_format": entry.get("pytorch_format") or "—",
                    "stack_count": entry.get("stack_count"),
                    "is_likely_safe": entry.get("is_likely_safe"),
                }
            )
    elif top_level:
        entries.append({"file": "—", "severity": top_level, "pytorch_format": "—", "stack_count": None, "is_likely_safe": None})
    return {"entries": entries, "headline": top_level or (entries[0]["severity"] if entries else "—")}


def _modelaudit_panel(ma: dict) -> dict:
    issues = []
    for issue in ma.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        issues.append(
            {
                "location": _basename(issue.get("location") or issue.get("file")),
                "message": (issue.get("message") or "—")[:300],
                "severity": (issue.get("severity") or "unknown").lower(),
                "rule_code": issue.get("rule_code") or issue.get("rule") or "—",
                "why": (issue.get("why") or "")[:400],
            }
        )
    return {
        "actionable_issue_count": ma.get("actionable_issue_count", 0),
        "issue_count": ma.get("issue_count", 0),
        "noise_filtered_count": ma.get("noise_filtered_count", 0),
        "path_count": ma.get("path_count", 0),
        "scan_mode": ma.get("scan_mode") or "—",
        "by_severity": ma.get("by_severity") or {},
        "issues": issues,
        "sample_paths": [_basename(p) for p in (ma.get("paths_scanned") or [])[:8]],
    }


def _dependency_panel(deps: dict) -> dict | None:
    if not deps:
        return None
    vulns = []
    for v in deps.get("vulnerabilities") or []:
        if not isinstance(v, dict):
            continue
        fix = v.get("fix_versions") or []
        vulns.append(
            {
                "package": v.get("package") or "—",
                "version": v.get("version") or "—",
                "severity": (v.get("severity") or "unknown").lower(),
                "id": v.get("id") or "—",
                "source": v.get("source") or "—",
                "manifest": v.get("manifest") or "—",
                "fix": ", ".join(fix) if fix else "—",
                "corroborated_by": v.get("corroborated_by") or [],
            }
        )
    return {
        "vuln_count": deps.get("vuln_count", 0),
        "manifests_found": deps.get("manifests_found") or [],
        "by_severity": deps.get("by_severity") or {},
        "scan_mode": deps.get("scan_mode") or "—",
        "pip_audit_available": deps.get("pip_audit_available", False),
        "vulnerabilities": vulns,
    }


def _secret_panel(sec: dict | None) -> dict | None:
    if not sec:
        return None
    secrets = []
    for s in sec.get("secrets") or []:
        if not isinstance(s, dict):
            continue
        secrets.append(
            {
                "detector": s.get("detector") or "—",
                "file": _basename(s.get("file")),
                "verified": bool(s.get("verified")),
                "redacted": (s.get("redacted") or "[redacted]")[:80],
            }
        )
    return {
        "available": sec.get("available", True),
        "secret_count": sec.get("secret_count", 0),
        "verified_count": sec.get("verified_count", 0),
        "by_detector": sec.get("by_detector") or {},
        "files_scanned": sec.get("files_scanned"),
        "scan_mode": sec.get("scan_mode") or "—",
        "note": sec.get("note") or sec.get("error"),
        "secrets": secrets,
    }


def _coverage_stats(coverage: dict, file_formats: dict) -> list[dict]:
    """human-readable label/value pairs for the coverage section."""
    stats: list[dict] = []
    if coverage.get("modelscan_scanned_files") is not None:
        stats.append({"label": "ModelScan files scanned", "value": coverage["modelscan_scanned_files"]})
    if coverage.get("modelscan_skipped") is not None:
        stats.append({"label": "ModelScan files skipped", "value": coverage["modelscan_skipped"]})
    if coverage.get("modelaudit_paths") is not None:
        n = len(coverage["modelaudit_paths"]) if isinstance(coverage["modelaudit_paths"], list) else coverage.get("modelaudit_paths")
        stats.append({"label": "ModelAudit paths", "value": n})
    if "fickling_applicable" in coverage:
        stats.append(
            {
                "label": "Fickling applicable",
                "value": "yes" if coverage["fickling_applicable"] else "no (e.g. safetensors-only)",
            }
        )
    if coverage.get("dependency_manifests") is not None:
        manifests = coverage["dependency_manifests"]
        stats.append(
            {
                "label": "Dependency manifests",
                "value": len(manifests) if isinstance(manifests, list) else manifests or 0,
            }
        )
    if "secret_scan_available" in coverage:
        stats.append(
            {
                "label": "TruffleHog available",
                "value": "yes" if coverage["secret_scan_available"] else "no",
            }
        )
    if coverage.get("secret_files_scanned") is not None:
        stats.append({"label": "Secret scan files", "value": coverage["secret_files_scanned"]})
    for key, val in (file_formats or {}).items():
        if isinstance(val, list) and val:
            stats.append({"label": f"Format: {key}", "value": len(val)})
    return stats


def _file_format_rows(file_formats: dict) -> list[dict]:
    rows = []
    for category, files in sorted((file_formats or {}).items()):
        if not isinstance(files, list):
            continue
        for name in files[:12]:
            rows.append({"category": category, "file": name})
        if len(files) > 12:
            rows.append({"category": category, "file": f"… +{len(files) - 12} more"})
    return rows


def _build_scan_detail(slug: str, data: dict) -> dict:
    """Structured scan payload from ScanResult-shaped ``data``."""
    findings = _parse_findings(data.get("findings") or [])
    tool = data.get("tool_results") or {}
    meta = data.get("scan_metadata") or {}
    coverage = meta.get("coverage") or {}
    file_formats = meta.get("file_formats") or {}

    ms = tool.get("modelscan") or {}
    fick = tool.get("fickling")
    ma = tool.get("modelaudit") or {}
    deps = tool.get("dependencies")
    sec = tool.get("secrets")

    tool_panels = {
        "modelscan": _modelscan_panel(ms) if ms else None,
        "fickling": _fickling_panel(fick, data.get("fickling_severity")),
        "modelaudit": _modelaudit_panel(ma) if ma else None,
        "dependencies": _dependency_panel(deps) if deps is not None else None,
        "secrets": _secret_panel(sec) if sec is not None else None,
    }

    scanned_files = [_basename(p) for p in (data.get("scanned_files") or [])]

    return {
        "slug": slug,
        "model_id": data.get("model_id") or _slug_to_model(slug),
        "severity_tier": (data.get("severity_tier") or "unknown").lower(),
        "overall_risk_score": data.get("overall_risk_score", 0),
        "status": data.get("status") or "unknown",
        "fickling_severity": data.get("fickling_severity"),
        "findings": findings,
        "n_findings": len(findings),
        "severity_summary": _severity_summary(findings),
        "tool_snippet": _tool_snippet(data),
        "tool_panels": tool_panels,
        "coverage_stats": _coverage_stats(coverage, file_formats),
        "file_format_rows": _file_format_rows(file_formats),
        "scanned_files": scanned_files,
        "scanned_file_count": len(scanned_files),
        "scanned_at": meta.get("scanned_at") or "—",
        "scanner_version": meta.get("scanner_version") or "—",
        "raw_summary": {
            "model_id": data.get("model_id"),
            "severity_tier": data.get("severity_tier"),
            "overall_risk_score": data.get("overall_risk_score"),
            "fickling_severity": data.get("fickling_severity"),
            "tool_results": {
                "modelscan": {k: ms.get(k) for k in ("total_issues", "total_skipped", "modelscan_version") if ms},
                "fickling": {"severity": (fick or {}).get("severity")} if fick else None,
                "modelaudit": {
                    k: ma.get(k)
                    for k in ("actionable_issue_count", "issue_count", "noise_filtered_count", "scan_mode")
                    if ma
                },
                "dependencies": {"vuln_count": (deps or {}).get("vuln_count")} if deps else None,
                "secrets": {
                    "secret_count": (sec or {}).get("secret_count"),
                    "verified_count": (sec or {}).get("verified_count"),
                }
                if sec
                else None,
            },
        },
    }


def _get_scans_data_files() -> dict:
    """
    list every scan_result.json under scanner/output/, sorted highest risk first.

    surfaces the malicious poc at the top for stakeholder demos when present.
    """
    from frontend.read_context import artifact_path_visible

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
        if not artifact_path_visible(path.parent):
            continue
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


def _get_scan_detail_files(slug: str) -> dict | None:
    """
    structured scan payload for one slug — findings, tool panels, coverage stats.

    returns none if the slug dir or scan_result.json is missing.
    """
    path = OUTPUT_DIR / slug / "scan_result.json"
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    return _build_scan_detail(slug, data)


# Public entry points — Postgres when configured, artifact fallback otherwise.


def get_scans_data() -> dict:
    try:
        from frontend import scan_db_data

        if scan_db_data.available():
            return scan_db_data.get_scans_data_db()
    except Exception:
        pass
    return _get_scans_data_files()


def get_scan_detail(slug: str) -> dict | None:
    try:
        from frontend import scan_db_data

        if scan_db_data.available():
            detail = scan_db_data.get_scan_detail_db(slug)
            if detail is not None:
                return detail
    except Exception:
        pass
    return _get_scan_detail_files(slug)


def delete_scan_paths(slug: str) -> list[str]:
    """Human-readable paths removed by ``delete_scan``."""
    if not is_safe_slug(slug):
        return []
    return [f"scanner/output/{slug}/"]


def delete_scan(slug: str) -> str | None:
    """Remove scan artifacts (and DB row when configured). Returns error or None."""
    from frontend.output_dirs import wipe_dir
    from frontend.scan_launch import inflight_scan_slugs

    if not is_safe_slug(slug):
        return f"invalid slug: {slug!r}"
    if slug in inflight_scan_slugs():
        return "cannot delete while the scan is still in progress"

    scan_dir = OUTPUT_DIR / slug
    result_path = scan_dir / "scan_result.json"
    db_keys: tuple[str, str] | None = None
    if result_path.is_file():
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
            meta = data.get("scan_metadata") or {}
            scanned_at = meta.get("scanned_at")
            hf_repo = data.get("model_id")
            if hf_repo and scanned_at:
                db_keys = (hf_repo, scanned_at)
        except (json.JSONDecodeError, OSError):
            pass

    removed_disk = scan_dir.is_dir()
    if removed_disk:
        wipe_dir(scan_dir)

    removed_db = False
    try:
        from frontend import scan_db_data

        if scan_db_data.available():
            if db_keys:
                removed_db = scan_db_data.delete_run(*db_keys)
            if not removed_db:
                removed_db = scan_db_data.delete_run_by_slug(slug)
    except Exception:
        pass

    if not removed_disk and not removed_db:
        return f"no scan result found for slug {slug!r}"
    return None
